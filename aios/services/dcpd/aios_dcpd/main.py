"""dcpd — Desktop Control Plane daemon (session)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from aios_common.ipc import RpcServer
from aios_dcpd.engine import DcpEngine

log = logging.getLogger("dcpd")


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    engine = DcpEngine(use_policy=os.environ.get("AIOS_DCP_NO_POLICY") != "1")
    srv = RpcServer("dcpd")

    @srv.method("ping")
    async def ping(_p):
        return {"ok": True, "service": "dcpd", "frozen": engine.frozen}

    @srv.method("list_targets")
    async def list_targets(_p):
        return {"targets": engine.list_targets()}

    @srv.method("snapshot")
    async def snapshot(p):
        return engine.snapshot(p["target"])

    @srv.method("find")
    async def find(p):
        return {"nodes": engine.find(p["target"], p.get("query") or {})}

    @srv.method("act")
    async def act(p):
        return await engine.act(p["target"], p["action"], p.get("args") or {}, confirmed=bool(p.get("confirmed")))

    @srv.method("assert")
    async def assert_cond(p):
        return await engine.assert_cond(p["target"], p["condition"], int(p.get("timeout_ms", 3000)))

    @srv.method("freeze")
    async def freeze(_p):
        return engine.freeze()

    @srv.method("unfreeze")
    async def unfreeze(_p):
        return engine.unfreeze()

    @srv.method("stats")
    async def stats(_p):
        return {"stats": engine.stats()}

    @srv.method("invoke")
    async def invoke(p):
        # System intent layer stub — map known intents to fixture actions
        intent = p.get("intent")
        params = p.get("params") or {}
        if intent == "hello.set_text":
            return await engine.act("fixture:hello", "ime_commit", {"node": "w_entry", "text": params.get("text", "")})
        if intent == "hello.click_ok":
            return await engine.act("fixture:hello", "click", {"node": "w_btn_ok"})
        from aios_common.errors import AiosError, ErrorCode

        raise AiosError(ErrorCode.NOT_FOUND, f"unknown intent {intent}")

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
    log.info("dcpd ready")
    await stop.wait()
    await srv.stop()


def main():
    argparse.ArgumentParser(prog="dcpd").parse_args()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
