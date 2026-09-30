"""agentd — Agent Supervisor: plan, tools, budget, timeline, skills."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from aios_common.errors import AiosError, ErrorCode
from aios_common.ipc import RpcServer, call as rpc_call
from aios_common.paths import skills_dir, state_dir

log = logging.getLogger("agentd")


@dataclass
class Budget:
    max_steps: int = 32
    max_seconds: float = 120.0
    max_tokens: int = 8000
    steps: int = 0
    tokens: int = 0
    started: float = field(default_factory=time.time)

    def tick_step(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise AiosError(ErrorCode.BUDGET_EXCEEDED, "step budget exceeded")
        if time.time() - self.started > self.max_seconds:
            raise AiosError(ErrorCode.BUDGET_EXCEEDED, "time budget exceeded")

    def add_tokens(self, n: int) -> None:
        self.tokens += n
        if self.tokens > self.max_tokens:
            raise AiosError(ErrorCode.BUDGET_EXCEEDED, "token budget exceeded")


@dataclass
class Task:
    id: str
    goal: str
    status: str = "running"  # running|done|aborted|failed
    plan: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    budget: Budget = field(default_factory=Budget)
    result: Any = None


class Planner:
    """Offline rule planner + optional ai-engined assist."""

    async def plan(self, goal: str, context: Optional[dict] = None) -> list[dict]:
        g = goal.strip()
        # Try AI engine for structured plan; fall back to rules
        try:
            resp = await rpc_call(
                "ai-engined",
                "plan",
                {"goal": g, "context": context or {}},
                timeout=10.0,
            )
            if resp.get("steps"):
                return resp["steps"]
        except Exception as e:  # noqa: BLE001
            log.debug("ai plan unavailable: %s", e)

        steps: list[dict] = []
        # Hello DCP patterns
        m = re.search(r"(填写|输入|写入|type|set)\s*[「\"]?(.*?)[」\"]?\s*(到|至|in)?", g, re.I)
        text = None
        if m:
            text = m.group(2)
        m2 = re.search(r"[「\"]([^」\"]+)[」\"]", g)
        if m2 and not text:
            text = m2.group(1)
        if re.search(r"hello|夹具|fixture|演示", g, re.I) or text or re.search(r"点(击)?\s*OK|点击确定", g, re.I):
            target = "fixture:hello"
            if text:
                steps.append(
                    {
                        "tool": "dcp.act",
                        "args": {"target": target, "action": "ime_commit", "args": {"node": "w_entry", "text": text}},
                        "risk": 1,
                        "assert": {"text_equals": text, "node": "w_entry"},
                    }
                )
            if re.search(r"OK|确定|确认", g, re.I) or not steps:
                steps.append(
                    {
                        "tool": "dcp.act",
                        "args": {"target": target, "action": "click", "args": {"node": "w_btn_ok"}},
                        "risk": 1,
                        "assert": {"exists": {"id": "w_label"}},
                    }
                )
            return steps

        if re.search(r"列出窗口|list.?window|窗口列表", g, re.I):
            return [{"tool": "dcp.list_targets", "args": {}, "risk": 0}]

        if re.search(r"发送", g):
            steps.append(
                {
                    "tool": "dcp.act",
                    "args": {"target": "fixture:hello", "action": "click", "args": {"node": "w_btn_send"}},
                    "risk": 1,
                    "assert": {"text_equals": "SENT", "node": "w_label"},
                }
            )
            return steps

        # Generic: ask AI or list + snapshot
        return [
            {"tool": "dcp.list_targets", "args": {}, "risk": 0},
            {
                "tool": "notify",
                "args": {"message": f"无法自动规划，请细化目标: {g}"},
                "risk": 0,
            },
        ]


class ToolBroker:
    async def run(self, tool: str, args: dict) -> Any:
        if tool == "dcp.list_targets":
            return await rpc_call("dcpd", "list_targets", {})
        if tool == "dcp.snapshot":
            return await rpc_call("dcpd", "snapshot", {"target": args["target"]})
        if tool == "dcp.find":
            return await rpc_call("dcpd", "find", {"target": args["target"], "query": args.get("query") or {}})
        if tool == "dcp.act":
            return await rpc_call(
                "dcpd",
                "act",
                {
                    "target": args["target"],
                    "action": args["action"],
                    "args": args.get("args") or {},
                    "confirmed": bool(args.get("confirmed")),
                },
            )
        if tool == "dcp.assert":
            return await rpc_call(
                "dcpd",
                "assert",
                {"target": args["target"], "condition": args["condition"], "timeout_ms": args.get("timeout_ms", 3000)},
            )
        if tool == "dcp.freeze":
            return await rpc_call("dcpd", "freeze", {})
        if tool == "notify":
            log.info("NOTIFY: %s", args.get("message"))
            return {"ok": True}
        if tool == "ai.infer":
            return await rpc_call("ai-engined", "infer", args)
        raise AiosError(ErrorCode.NOT_FOUND, f"unknown tool {tool}")


class AgentSupervisor:
    def __init__(self):
        self.planner = Planner()
        self.tools = ToolBroker()
        self.tasks: dict[str, Task] = {}
        self._abort = set()

    async def run(self, goal: str, context: Optional[dict] = None, opts: Optional[dict] = None) -> dict:
        opts = opts or {}
        task = Task(id=f"task_{uuid.uuid4().hex[:10]}", goal=goal)
        if opts.get("max_steps"):
            task.budget.max_steps = int(opts["max_steps"])
        if opts.get("max_seconds"):
            task.budget.max_seconds = float(opts["max_seconds"])
        self.tasks[task.id] = task
        task.timeline.append({"event": "start", "goal": goal, "ts": time.time()})

        plan = opts.get("plan")
        if not plan:
            plan = await self.planner.plan(goal, context)
        if opts.get("plan_only"):
            task.status = "done"
            task.plan = plan
            return {"task_id": task.id, "plan": plan, "status": "planned"}

        # Allow edit via opts["plan"] already
        task.plan = plan
        task.timeline.append({"event": "plan", "steps": plan, "ts": time.time()})

        try:
            for i, step in enumerate(plan):
                if task.id in self._abort:
                    task.status = "aborted"
                    await self.tools.run("dcp.freeze", {})
                    break
                task.budget.tick_step()
                tool = step["tool"]
                args = step.get("args") or {}
                task.timeline.append({"event": "step_begin", "i": i, "tool": tool, "ts": time.time()})
                try:
                    result = await self.tools.run(tool, args)
                    task.timeline.append({"event": "step_ok", "i": i, "result": result, "ts": time.time()})
                    if step.get("assert") and tool.startswith("dcp"):
                        target = args.get("target") or "fixture:hello"
                        await self.tools.run(
                            "dcp.assert",
                            {"target": target, "condition": step["assert"], "timeout_ms": 2000},
                        )
                except AiosError as e:
                    task.timeline.append({"event": "step_fail", "i": i, "error": e.to_dict(), "ts": time.time()})
                    if opts.get("stop_on_error", True):
                        task.status = "failed"
                        task.result = e.to_dict()
                        return {
                            "task_id": task.id,
                            "status": task.status,
                            "timeline": task.timeline,
                            "error": e.to_dict(),
                        }
            if task.status == "running":
                task.status = "done"
                task.result = {"ok": True}
        except AiosError as e:
            task.status = "failed"
            task.result = e.to_dict()

        # Optional skill save
        if opts.get("save_skill") and task.status == "done":
            self._save_skill(opts["save_skill"], goal, plan)

        return {
            "task_id": task.id,
            "status": task.status,
            "plan": task.plan,
            "timeline": task.timeline,
            "result": task.result,
        }

    def abort(self, task_id: Optional[str] = None) -> dict:
        if task_id:
            self._abort.add(task_id)
            if task_id in self.tasks:
                self.tasks[task_id].status = "aborted"
            return {"aborted": task_id}
        for tid in list(self.tasks):
            self._abort.add(tid)
            self.tasks[tid].status = "aborted"
        return {"aborted": "all"}

    def _save_skill(self, name: str, goal: str, plan: list) -> Path:
        d = skills_dir() / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.yaml").write_text(
            yaml.dump({"name": name, "goal_template": goal, "version": 1}, allow_unicode=True)
        )
        (d / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        return d

    def list_skills(self) -> list:
        out = []
        for p in skills_dir().iterdir() if skills_dir().exists() else []:
            if p.is_dir() and (p / "manifest.yaml").exists():
                out.append({"name": p.name, "path": str(p)})
        return out


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    supervisor = AgentSupervisor()
    srv = RpcServer("agentd")

    @srv.method("ping")
    async def ping(_p):
        return {"ok": True, "service": "agentd"}

    @srv.method("run")
    async def run(p):
        return await supervisor.run(p["goal"], p.get("context"), p.get("opts"))

    @srv.method("abort")
    async def abort(p):
        r = supervisor.abort(p.get("task_id"))
        try:
            await rpc_call("dcpd", "freeze", {})
        except Exception:  # noqa: BLE001
            pass
        try:
            await rpc_call("policy", "freeze", {})
        except Exception:  # noqa: BLE001
            pass
        return r

    @srv.method("get_task")
    async def get_task(p):
        t = supervisor.tasks.get(p["task_id"])
        if not t:
            raise AiosError(ErrorCode.NOT_FOUND, "task not found")
        return {
            "id": t.id,
            "goal": t.goal,
            "status": t.status,
            "plan": t.plan,
            "timeline": t.timeline,
            "result": t.result,
        }

    @srv.method("list_skills")
    async def list_skills(_p):
        return {"skills": supervisor.list_skills()}

    await srv.start()
    stop = asyncio.Event()

    def _stop(*_a):
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass
    log.info("agentd ready")
    await stop.wait()
    await srv.stop()


def main():
    argparse.ArgumentParser(prog="agentd").parse_args()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
