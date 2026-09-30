
"""aios CLI — operator entry for luminOS services."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from aios_common.ipc import call as rpc_call


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


async def cmd_ping(args):
    for s in args.services.split(","):
        s = s.strip()
        try:
            r = await rpc_call(s, "ping", {}, timeout=2)
            _print({"service": s, "result": r})
        except Exception as e:
            _print({"service": s, "error": str(e)})


async def cmd_dcp(args):
    if args.dcp_cmd == "targets":
        _print(await rpc_call("dcpd", "list_targets", {}))
    elif args.dcp_cmd == "snapshot":
        _print(await rpc_call("dcpd", "snapshot", {"target": args.target}))
    elif args.dcp_cmd == "find":
        q = json.loads(args.query) if args.query else {"contains": args.contains or ""}
        _print(await rpc_call("dcpd", "find", {"target": args.target, "query": q}))
    elif args.dcp_cmd == "act":
        a = json.loads(args.args_json) if args.args_json else {"node": args.node}
        _print(await rpc_call("dcpd", "act", {"target": args.target, "action": args.action, "args": a}))
    elif args.dcp_cmd == "freeze":
        _print(await rpc_call("dcpd", "freeze", {}))


async def cmd_agent(args):
    if args.agent_cmd == "run":
        opts = {}
        if args.plan_only:
            opts["plan_only"] = True
        _print(await rpc_call("agentd", "run", {"goal": args.goal, "opts": opts}))
    elif args.agent_cmd == "abort":
        _print(await rpc_call("agentd", "abort", {"task_id": args.task_id}))


async def cmd_pair(args):
    _print(await rpc_call("rcpd", "issue_pairing", {}))


def main(argv=None):
    p = argparse.ArgumentParser(prog="aios", description="luminOS control CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("ping")
    sp.add_argument("--services", default="policy,dcpd,agentd,ai-engined,rcpd,gateway,scheduler,store")
    sp.set_defaults(func=cmd_ping)

    sd = sub.add_parser("dcp")
    sd.add_argument("dcp_cmd", choices=["targets", "snapshot", "find", "act", "freeze"])
    sd.add_argument("--target", default="fixture:hello")
    sd.add_argument("--query")
    sd.add_argument("--contains")
    sd.add_argument("--action", default="click")
    sd.add_argument("--node")
    sd.add_argument("--args-json")
    sd.set_defaults(func=cmd_dcp)

    sa = sub.add_parser("agent")
    sa.add_argument("agent_cmd", choices=["run", "abort"])
    sa.add_argument("--goal", default="")
    sa.add_argument("--task-id")
    sa.add_argument("--plan-only", action="store_true")
    sa.set_defaults(func=cmd_agent)

    spair = sub.add_parser("pair")
    spair.set_defaults(func=cmd_pair)

    args = p.parse_args(argv)
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
