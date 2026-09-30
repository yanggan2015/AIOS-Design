"""aios-gateway — local MCP/HTTP capability bus."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from aiohttp import web

from aios_common.errors import AiosError
from aios_common.ipc import RpcServer, call as rpc_call

log = logging.getLogger("aios-gateway")


async def handle_mcp_tools(_request: web.Request) -> web.Response:
    tools = [
        {"name": "dcp.list_targets", "description": "List desktop targets"},
        {"name": "dcp.snapshot", "description": "Snapshot UI tree"},
        {"name": "dcp.find", "description": "Find nodes"},
        {"name": "dcp.act", "description": "Act on node"},
        {"name": "agent.run", "description": "Run agent goal"},
        {"name": "agent.abort", "description": "Abort agent"},
    ]
    return web.json_response({"tools": tools})


async def handle_mcp_call(request: web.Request) -> web.Response:
    body = await request.json()
    name = body.get("name")
    args = body.get("arguments") or {}
    try:
        if name == "dcp.list_targets":
            r = await rpc_call("dcpd", "list_targets", {})
        elif name == "dcp.snapshot":
            r = await rpc_call("dcpd", "snapshot", args)
        elif name == "dcp.find":
            r = await rpc_call("dcpd", "find", args)
        elif name == "dcp.act":
            r = await rpc_call("dcpd", "act", args)
        elif name == "agent.run":
            r = await rpc_call("agentd", "run", args)
        elif name == "agent.abort":
            r = await rpc_call("agentd", "abort", args)
        else:
            return web.json_response({"error": f"unknown tool {name}"}, status=404)
        return web.json_response({"result": r})
    except AiosError as e:
        return web.json_response({"error": e.to_dict()}, status=400)
    except Exception as e:  # noqa: BLE001
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "aios-gateway"})


async def amain(port: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    srv = RpcServer("gateway")

    @srv.method("ping")
    async def ping(_p):
        return {"ok": True, "service": "gateway"}

    await srv.start()

    app = web.Application()
    app.router.add_get("/health", handle_health)
    app.router.add_get("/mcp/tools", handle_mcp_tools)
    app.router.add_post("/mcp/call", handle_mcp_call)
    app.router.add_get("/v1/dcp/targets", lambda r: _proxy(r, "dcpd", "list_targets"))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    log.info("gateway http://127.0.0.1:%s", port)

    stop = asyncio.Event()

    def _stop(*_a):
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass
    await stop.wait()
    await runner.cleanup()
    await srv.stop()


async def _proxy(request: web.Request, service: str, method: str) -> web.Response:
    try:
        r = await rpc_call(service, method, dict(request.query))
        return web.json_response(r)
    except Exception as e:  # noqa: BLE001
        return web.json_response({"error": str(e)}, status=500)


def main():
    ap = argparse.ArgumentParser(prog="aios-gateway")
    ap.add_argument("--port", type=int, default=18765)
    args = ap.parse_args()
    asyncio.run(amain(args.port))


if __name__ == "__main__":
    main()
