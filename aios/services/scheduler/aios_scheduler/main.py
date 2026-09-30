
"""aios-scheduler — cron-like agent job runner."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import time
from pathlib import Path

from aios_common.ipc import RpcServer, call as rpc_call
from aios_common.paths import state_dir

log = logging.getLogger("aios-scheduler")


class Scheduler:
    def __init__(self):
        self.jobs_path = state_dir() / "scheduler_jobs.json"
        self.jobs = self._load()
        self._task = None

    def _load(self):
        if self.jobs_path.exists():
            return json.loads(self.jobs_path.read_text())
        return []

    def _save(self):
        self.jobs_path.write_text(json.dumps(self.jobs, ensure_ascii=False, indent=2))

    def add(self, job: dict) -> dict:
        job = dict(job)
        job.setdefault("id", f"job_{int(time.time())}")
        job.setdefault("enabled", True)
        job.setdefault("interval_sec", 3600)
        job["next_run"] = time.time() + float(job["interval_sec"])
        self.jobs.append(job)
        self._save()
        return job

    def list(self):
        return list(self.jobs)

    async def tick(self):
        now = time.time()
        for job in self.jobs:
            if not job.get("enabled"):
                continue
            if now >= float(job.get("next_run", 0)):
                goal = job.get("goal")
                log.info("run job %s goal=%s", job["id"], goal)
                try:
                    await rpc_call("agentd", "run", {"goal": goal, "opts": job.get("opts") or {}})
                except Exception as e:
                    log.warning("job failed: %s", e)
                job["next_run"] = now + float(job.get("interval_sec", 3600))
                job["last_run"] = now
        self._save()


async def amain():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    sched = Scheduler()
    srv = RpcServer("scheduler")

    @srv.method("ping")
    async def ping(_p):
        return {"ok": True, "service": "scheduler"}

    @srv.method("add_job")
    async def add_job(p):
        return sched.add(p)

    @srv.method("list_jobs")
    async def list_jobs(_p):
        return {"jobs": sched.list()}

    await srv.start()

    async def loop():
        while True:
            await sched.tick()
            await asyncio.sleep(5)

    task = asyncio.create_task(loop())
    stop = asyncio.Event()
    def _stop(*_a):
        stop.set()
    loop_ = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop_.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass
    await stop.wait()
    task.cancel()
    await srv.stop()


def main():
    argparse.ArgumentParser(prog="aios-scheduler").parse_args()
    asyncio.run(amain())


if __name__ == "__main__":
    main()
