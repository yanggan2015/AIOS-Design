"""ai-engined — model router, OCR stub, offline planner assist."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import re
import signal
import time
from typing import Any, Optional

from aios_common.errors import AiosError, ErrorCode
from aios_common.ipc import RpcServer
from aios_common.paths import state_dir

log = logging.getLogger("ai-engined")


class ModelRegistry:
    def __init__(self):
        self.models = {
            "local-rules": {
                "id": "local-rules",
                "backend": "rules",
                "offline": True,
                "privacy": "local",
            },
            "local-echo": {
                "id": "local-echo",
                "backend": "echo",
                "offline": True,
                "privacy": "local",
            },
        }
        self.active = "local-rules"
        self.byo: dict[str, dict] = {}

    def list(self) -> list:
        return list(self.models.values()) + list(self.byo.values())

    def add_byo(self, name: str, endpoint: str, meta: Optional[dict] = None) -> dict:
        # Never log secrets
        entry = {
            "id": name,
            "backend": "byo",
            "endpoint": endpoint,
            "offline": False,
            "privacy": "user",
            "meta": {k: v for k, v in (meta or {}).items() if k != "api_key"},
        }
        if meta and "api_key" in meta:
            # store handle only
            handle = hashlib.sha256(meta["api_key"].encode()).hexdigest()[:16]
            secret_path = state_dir() / "secrets"
            secret_path.mkdir(exist_ok=True)
            (secret_path / f"model_{name}.handle").write_text(handle)
            os.chmod(secret_path / f"model_{name}.handle", 0o600)
            entry["key_handle"] = handle
        self.byo[name] = entry
        return entry


class Router:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self.force_local = os.environ.get("AIOS_OFFLINE") == "1"

    def choose(self, request: dict) -> dict:
        sensitivity = request.get("sensitivity", "normal")
        if self.force_local or sensitivity == "sensitive":
            return {"model_id": "local-rules", "reason": "local_policy"}
        preferred = request.get("model_id") or self.registry.active
        if preferred in self.registry.byo and not self.force_local:
            return {"model_id": preferred, "reason": "byo"}
        return {"model_id": preferred if preferred in self.registry.models else "local-rules", "reason": "default"}


class Engine:
    def __init__(self):
        self.registry = ModelRegistry()
        self.router = Router(self.registry)

    def infer(self, request: dict) -> dict:
        decision = self.router.choose(request)
        model_id = decision["model_id"]
        prompt = request.get("prompt") or request.get("inputs", {}).get("text", "")
        # Mark untrusted segments
        untrusted = request.get("untrusted_text", "")
        if untrusted and re.search(r"忽略|ignore (all )?rules|bypass", untrusted, re.I):
            return {
                "request_id": request.get("request_id"),
                "model_id": model_id,
                "output": {"text": "", "blocked": True, "reason": "PROMPT_INJECTION"},
                "route": decision,
            }
        if model_id == "local-echo":
            text = f"echo:{prompt[:200]}"
        else:
            text = self._rules_reply(prompt)
        return {
            "request_id": request.get("request_id"),
            "model_id": model_id,
            "output": {"text": text},
            "route": decision,
            "usage": {"tokens": max(1, len(prompt) // 4)},
        }

    def _rules_reply(self, prompt: str) -> str:
        if not prompt:
            return ""
        if "计划" in prompt or "plan" in prompt.lower():
            return "使用 dcp 操作 fixture:hello"
        return f"local-rules: understood ({len(prompt)} chars)"

    def plan(self, goal: str, context: Optional[dict] = None) -> dict:
        # Structured steps for agentd; keep simple & deterministic
        g = goal
        steps = []
        m = re.search(r"[「\"]([^」\"]+)[」\"]", g)
        text = m.group(1) if m else None
        if text or "hello" in g.lower() or "夹具" in g:
            if text:
                steps.append(
                    {
                        "tool": "dcp.act",
                        "args": {
                            "target": "fixture:hello",
                            "action": "ime_commit",
                            "args": {"node": "w_entry", "text": text},
                        },
                        "risk": 1,
                    }
                )
            steps.append(
                {
                    "tool": "dcp.act",
                    "args": {"target": "fixture:hello", "action": "click", "args": {"node": "w_btn_ok"}},
                    "risk": 1,
                }
            )
        return {"steps": steps, "model_id": "local-rules"}

    def ocr(self, roi: Optional[dict] = None) -> dict:
        # Deterministic OCR stub for Mode-C anchors
        return {
            "items": [
                {"text": "OK", "box": [20, 110, 80, 32], "conf": 0.99},
                {"text": "发送", "box": [120, 110, 80, 32], "conf": 0.98},
                {"text": "Ready", "box": [20, 20, 200, 24], "conf": 0.95},
            ]
        }


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    eng = Engine()
    srv = RpcServer("ai-engined")

    @srv.method("ping")
    async def ping(_p):
        return {"ok": True, "service": "ai-engined", "active": eng.registry.active}

    @srv.method("infer")
    async def infer(p):
        return eng.infer(p)

    @srv.method("plan")
    async def plan(p):
        return eng.plan(p.get("goal", ""), p.get("context"))

    @srv.method("ocr")
    async def ocr(p):
        return eng.ocr(p.get("roi"))

    @srv.method("list_models")
    async def list_models(_p):
        return {"models": eng.registry.list()}

    @srv.method("set_active")
    async def set_active(p):
        mid = p["model_id"]
        if mid not in eng.registry.models and mid not in eng.registry.byo:
            raise AiosError(ErrorCode.NOT_FOUND, "model not found")
        eng.registry.active = mid
        return {"active": mid}

    @srv.method("add_byo")
    async def add_byo(p):
        return eng.registry.add_byo(p["name"], p["endpoint"], p.get("meta"))

    @srv.method("route")
    async def route(p):
        return eng.router.choose(p)

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
    log.info("ai-engined ready offline=%s", os.environ.get("AIOS_OFFLINE"))
    await stop.wait()
    await srv.stop()


def main():
    argparse.ArgumentParser(prog="ai-engined").parse_args()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
