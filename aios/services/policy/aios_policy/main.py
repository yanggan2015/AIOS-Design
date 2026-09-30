
"""aios-policy — permission / confirm / audit daemon."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from aios_common.ipc import RpcServer
from aios_common.policy_lib import PolicyEngine, Risk, load_policy_config

log = logging.getLogger("aios-policy")


def build_engine() -> PolicyEngine:
    cfg = load_policy_config()
    auto = Risk(int(cfg.get("auto_confirm_max", 1)))
    return PolicyEngine(
        auto_confirm_max=auto,
        allow_remote_confirm=bool(cfg.get("allow_remote_confirm", False)),
        headless_auto_confirm=os.environ.get("AIOS_HEADLESS") == "1",
    )


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    engine = build_engine()
    srv = RpcServer("policy")

    @srv.method("ping")
    async def ping(_p):
        return {"ok": True, "service": "aios-policy"}

    @srv.method("authorize")
    async def authorize(p):
        d = engine.authorize(
            p["action"],
            target=p.get("target"),
            uid=p.get("uid"),
            node=p.get("node"),
            confirmed=bool(p.get("confirmed")),
            confirm_id=p.get("confirm_id"),
            transport=p.get("transport", "local"),
            client_id=p.get("client_id"),
            meta=p.get("meta"),
        )
        return d.to_dict()

    @srv.method("confirm")
    async def confirm(p):
        return engine.confirm(p["confirm_id"], approved=bool(p.get("approved", True)))

    @srv.method("list_pending")
    async def list_pending(_p):
        return {"pending": engine.list_pending()}

    @srv.method("freeze")
    async def freeze(_p):
        return {"revoked": engine.freeze_all()}

    @srv.method("grant_trust")
    async def grant_trust(p):
        engine.grant_trust(p["action"], p.get("target"), float(p.get("ttl", 300)))
        return {"ok": True}

    @srv.method("verify_capability")
    async def verify_capability(p):
        cap = engine.caps.get(p["token"])
        return cap.to_public()

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
    log.info("aios-policy ready (headless=%s)", os.environ.get("AIOS_HEADLESS"))
    await stop.wait()
    await srv.stop()


def main():
    parser = argparse.ArgumentParser(prog="aios-policy")
    parser.parse_args()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
