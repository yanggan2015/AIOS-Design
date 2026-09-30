
"""aios-store-daemon — skill/app metadata stub."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path

from aios_common.ipc import RpcServer
from aios_common.paths import state_dir

log = logging.getLogger("aios-store")

CATALOG = [
    {"id": "skill.hello-ok", "type": "skill", "name": "Hello OK", "dcp_grade": "A"},
    {"id": "app.control-center", "type": "app", "name": "AI 控制中心", "dcp_grade": "A"},
]


async def amain():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    catalog_path = state_dir() / "store_catalog.json"
    if not catalog_path.exists():
        catalog_path.write_text(json.dumps(CATALOG, ensure_ascii=False, indent=2))
    srv = RpcServer("store")

    @srv.method("ping")
    async def ping(_p):
        return {"ok": True, "service": "store"}

    @srv.method("search")
    async def search(p):
        q = (p.get("q") or "").lower()
        items = json.loads(catalog_path.read_text())
        if q:
            items = [i for i in items if q in i["name"].lower() or q in i["id"].lower()]
        return {"items": items}

    @srv.method("compat")
    async def compat(p):
        return {"app_id": p.get("app_id"), "dcp_grade": "A", "min_os": "0.1.0"}

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
    await stop.wait()
    await srv.stop()


def main():
    argparse.ArgumentParser(prog="aios-store").parse_args()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
