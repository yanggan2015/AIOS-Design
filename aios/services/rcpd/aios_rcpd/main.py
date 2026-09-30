"""rcpd — Remote Control Protocol daemon (TCP + Unix loopback + serial stub)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import signal
import socket
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from aios_common.errors import ErrorCode
from aios_common.ipc import RpcServer, call as rpc_call
from aios_common.proto.rcp import (
    FLAG_JSON,
    FLAG_NEED_ACK,
    Frame,
    FrameError,
    MsgId,
    ack,
    encode_frame,
    nack,
    try_decode,
)

log = logging.getLogger("rcpd")

SYS_WHITELIST = {
    "power.suspend": ("sys.power.suspend", 3),
    "power.reboot": ("sys.power.reboot", 3),
    "power.poweroff": ("sys.power.poweroff", 3),
    "audio.set_volume": ("sys.audio.set_volume", 1),
    "audio.set_mute": ("sys.audio.set_mute", 1),
    "net.set_wifi": ("sys.net.set_wifi", 2),
    "session.lock": ("sys.session.lock", 1),
    "svc.status": ("sys.svc.status", 0),
    "svc.restart": ("sys.svc.restart", 3),
}


@dataclass
class Session:
    sid: str
    client_id: str
    transport: str
    scopes: list[str]
    created: float = field(default_factory=time.time)
    last_seq: int = -1
    expires: float = field(default_factory=lambda: time.time() + 8 * 3600)


class RateLimiter:
    def __init__(self, rate: float = 20.0):
        self.rate = rate
        self.tokens = rate
        self.updated = time.time()

    def allow(self) -> bool:
        now = time.time()
        self.tokens = min(self.rate, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RcpCore:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self.pairing_code: Optional[str] = None
        self.pairing_expires = 0.0
        self.network_enabled = os.environ.get("AIOS_RCP_NETWORK", "0") == "1"
        self.serial_enabled = os.environ.get("AIOS_RCP_SERIAL", "0") == "1"
        self._sys_state = {"volume": 50, "mute": False, "wifi": True, "locked": False}

    def issue_pairing(self) -> dict:
        self.pairing_code = f"{secrets.randbelow(1000000):06d}"
        self.pairing_expires = time.time() + 60
        # Never log plaintext code at info in production; debug only
        log.info("pairing code issued (expires 60s)")
        return {"code": self.pairing_code, "expires_in": 60}

    def _check_seq(self, sess: Session, seq: int) -> Optional[Frame]:
        if seq <= sess.last_seq:
            return nack(seq, ErrorCode.REPLAY, "REPLAY", sid=sess.sid)
        sess.last_seq = seq
        return None

    async def handle(self, frame: Frame, transport: str, peer: str, limiter: RateLimiter) -> list[Frame]:
        mid = frame.msg_id
        seq = frame.seq
        p = frame.payload or {}

        if mid == MsgId.HELLO:
            return [
                Frame(
                    msg_id=MsgId.HELLO_ACK,
                    seq=seq,
                    payload={
                        "ver": 1,
                        "need_auth": True,
                        "pairing_required": True,
                        "server": "luminOS-rcpd/0.1",
                        "transport": transport,
                    },
                )
            ]

        if mid == MsgId.PING:
            return [Frame(msg_id=MsgId.PONG, seq=seq, payload={"ts": int(time.time() * 1000)})]

        if mid == MsgId.AUTH:
            code = str(p.get("code", ""))
            mode = p.get("mode", "pairing_code")
            client_id = p.get("client_id") or peer
            if mode == "pairing_code":
                if not self.pairing_code or time.time() > self.pairing_expires or code != self.pairing_code:
                    self.pairing_code = None
                    return [Frame(msg_id=MsgId.AUTH_FAIL, seq=seq, payload={"code": 2, "reason": "UNAUTH"})]
                self.pairing_code = None  # one-time
            sid = f"s_{uuid.uuid4().hex[:8]}"
            scopes = ["sys.read", "dcp.act", "agent.run", "sys.call"]
            self.sessions[sid] = Session(sid=sid, client_id=client_id, transport=transport, scopes=scopes)
            return [
                Frame(
                    msg_id=MsgId.AUTH_OK,
                    seq=seq,
                    payload={"sid": sid, "scopes": scopes, "ttl": 8 * 3600},
                )
            ]

        # Business frames require sid
        sid = p.get("sid")
        sess = self.sessions.get(sid) if sid else None
        if mid not in (MsgId.HELLO, MsgId.AUTH, MsgId.PING) and not sess:
            return [nack(seq, ErrorCode.UNAUTH, "UNAUTH")]

        if sess:
            bad = self._check_seq(sess, seq)
            if bad:
                return [bad]
            if time.time() > sess.expires:
                self.sessions.pop(sess.sid, None)
                return [nack(seq, ErrorCode.REVOKED, "REVOKED")]

        # Rate limit action frames
        if mid in (MsgId.DCP_ACT, MsgId.SYS_CALL, MsgId.AGENT_RUN, MsgId.APP_LAUNCH):
            if not limiter.allow():
                return [nack(seq, ErrorCode.BUSY, "BUSY", sid=sid)]

        try:
            if mid == MsgId.SYS_INFO:
                has_session = True
                try:
                    await rpc_call("dcpd", "ping", {}, timeout=1.0)
                except Exception:
                    has_session = False
                return [
                    ack(
                        seq,
                        {
                            "hostname": socket.gethostname(),
                            "version": "luminOS-0.1.0",
                            "graphical_session": has_session,
                            "battery": None,
                        },
                        sid=sid,
                    )
                ]

            if mid == MsgId.SYS_CALL:
                method = (p.get("args") or {}).get("method") or p.get("method")
                if method == "shell" or method not in SYS_WHITELIST:
                    return [nack(seq, ErrorCode.FORBIDDEN, "FORBIDDEN", {"method": method}, sid=sid)]
                action, _risk = SYS_WHITELIST[method]
                decision = await rpc_call(
                    "policy",
                    "authorize",
                    {
                        "action": action,
                        "transport": transport,
                        "client_id": sess.client_id if sess else peer,
                        "confirmed": bool((p.get("args") or {}).get("confirmed")),
                    },
                )
                if not decision.get("allow"):
                    code = decision.get("code", ErrorCode.NEED_CONFIRM)
                    return [nack(seq, code, decision.get("reason", "NEED_CONFIRM"), {"method": method}, sid=sid)]
                # Execute whitelist locally (safe stubs)
                args = p.get("args") or {}
                if method.startswith("power."):
                    return [
                        ack(seq, {"method": method, "scheduled": True, "dry_run": True}, reason="DRY_RUN", sid=sid)
                    ]
                if method == "audio.set_volume":
                    self._sys_state["volume"] = int(args.get("value", 50))
                elif method == "audio.set_mute":
                    self._sys_state["mute"] = bool(args.get("value", True))
                elif method == "net.set_wifi":
                    self._sys_state["wifi"] = bool(args.get("value", True))
                elif method == "session.lock":
                    self._sys_state["locked"] = True
                elif method == "svc.status":
                    return [ack(seq, {"unit": args.get("unit"), "active": "unknown"}, sid=sid)]
                elif method == "svc.restart":
                    return [ack(seq, {"unit": args.get("unit"), "restarted": False, "dry_run": True}, sid=sid)]
                return [ack(seq, {"method": method, "state": self._sys_state}, sid=sid)]

            if mid == MsgId.WIN_LIST:
                try:
                    r = await rpc_call("dcpd", "list_targets", {})
                except Exception:
                    return [nack(seq, ErrorCode.NO_SESSION, "NO_SESSION", sid=sid)]
                return [ack(seq, {"windows": r.get("targets", [])}, sid=sid)]

            if mid == MsgId.DCP_SNAPSHOT:
                target = p.get("target") or (p.get("args") or {}).get("target")
                r = await rpc_call("dcpd", "snapshot", {"target": target})
                return [ack(seq, r, sid=sid)]

            if mid == MsgId.DCP_FIND:
                args = p.get("args") or {}
                r = await rpc_call(
                    "dcpd",
                    "find",
                    {"target": p.get("target") or args.get("target"), "query": args.get("query") or args},
                )
                return [ack(seq, r, sid=sid)]

            if mid == MsgId.DCP_ACT:
                args = p.get("args") or {}
                target = p.get("target") or args.get("target")
                action = args.get("action", "click")
                try:
                    r = await rpc_call(
                        "dcpd",
                        "act",
                        {
                            "target": target,
                            "action": action,
                            "args": args,
                            "confirmed": bool(args.get("confirmed")),
                        },
                    )
                    return [ack(seq, r, reason=r.get("reason", "OK"), sid=sid)]
                except Exception as e:
                    from aios_common.errors import AiosError

                    if isinstance(e, AiosError):
                        return [nack(seq, e.code, e.reason, e.data, sid=sid)]
                    return [nack(seq, ErrorCode.INTERNAL, str(e), sid=sid)]

            if mid == MsgId.DCP_ASSERT:
                args = p.get("args") or {}
                r = await rpc_call(
                    "dcpd",
                    "assert",
                    {
                        "target": p.get("target") or args.get("target"),
                        "condition": args.get("condition") or args,
                        "timeout_ms": args.get("timeout_ms", 3000),
                    },
                )
                return [ack(seq, r, sid=sid)]

            if mid == MsgId.APP_LIST:
                return [
                    ack(
                        seq,
                        {
                            "apps": [
                                {"id": "org.luminos.controlcenter", "name": "AI 控制中心"},
                                {"id": "org.luminos.fixture.hello", "name": "Hello Fixture"},
                            ]
                        },
                        sid=sid,
                    )
                ]

            if mid == MsgId.APP_LAUNCH:
                return [ack(seq, {"launched": (p.get("args") or {}).get("desktop_id"), "dry_run": True}, sid=sid)]

            if mid == MsgId.AGENT_RUN:
                goal = (p.get("args") or {}).get("goal") or p.get("goal")
                r = await rpc_call("agentd", "run", {"goal": goal, "opts": (p.get("args") or {}).get("opts")})
                return [ack(seq, r, sid=sid)]

            if mid == MsgId.AGENT_ABORT:
                r = await rpc_call("agentd", "abort", {"task_id": (p.get("args") or {}).get("task_id")})
                return [ack(seq, r, sid=sid)]

            if mid == MsgId.CONFIRM_RSP:
                cid = (p.get("args") or {}).get("confirm_id") or p.get("confirm_id")
                r = await rpc_call("policy", "confirm", {"confirm_id": cid, "approved": bool(p.get("approved", True))})
                return [ack(seq, r, sid=sid)]

            return [nack(seq, ErrorCode.NOT_FOUND, f"unhandled msg {mid:#x}", sid=sid)]
        except Exception as e:  # noqa: BLE001
            from aios_common.errors import AiosError

            log.exception("handle failed")
            if isinstance(e, AiosError):
                return [nack(seq, e.code, e.reason, e.data, sid=sid)]
            return [nack(seq, ErrorCode.INTERNAL, str(e), sid=sid)]


async def _read_frames(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, core: RcpCore, transport: str, peer: str):
    buf = bytearray()
    limiter = RateLimiter(20)
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            buf.extend(chunk)
            while True:
                try:
                    frame, n = try_decode(buf)
                except FrameError as e:
                    log.warning("bad frame from %s: %s", peer, e)
                    writer.write(encode_frame(nack(0, ErrorCode.BAD_FRAME, "BAD_FRAME")))
                    await writer.drain()
                    continue
                if frame is None:
                    break
                replies = await core.handle(frame, transport, peer, limiter)
                for rep in replies:
                    writer.write(encode_frame(rep))
                await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def amain(host: str, port: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    core = RcpCore()
    srv = RpcServer("rcpd")

    @srv.method("ping")
    async def ping(_p):
        return {"ok": True, "service": "rcpd", "network": core.network_enabled}

    @srv.method("issue_pairing")
    async def issue_pairing(_p):
        return core.issue_pairing()

    @srv.method("set_network")
    async def set_network(p):
        core.network_enabled = bool(p.get("enabled"))
        return {"network": core.network_enabled}

    await srv.start()

    tcp_server = None
    if core.network_enabled or os.environ.get("AIOS_RCP_LOOPBACK") == "1":
        bind_host = host if core.network_enabled else "127.0.0.1"
        tcp_server = await asyncio.start_server(
            lambda r, w: _read_frames(r, w, core, "tcp", bind_host),
            bind_host,
            port,
        )
        log.info("RCP TCP on %s:%s", bind_host, port)

    # Always offer Unix RCP stream for local SDK / tests
    from aios_common.paths import runtime_dir

    rcp_sock = runtime_dir() / "rcp.sock"
    if rcp_sock.exists():
        rcp_sock.unlink()

    async def on_unix(reader, writer):
        await _read_frames(reader, writer, core, "unix", "local")

    unix_server = await asyncio.start_unix_server(on_unix, path=str(rcp_sock))
    os.chmod(rcp_sock, 0o600)
    log.info("RCP unix on %s", rcp_sock)

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
    unix_server.close()
    await unix_server.wait_closed()
    if tcp_server:
        tcp_server.close()
        await tcp_server.wait_closed()
    await srv.stop()


def main():
    ap = argparse.ArgumentParser(prog="rcpd")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=17420)
    args = ap.parse_args()
    # Default: enable loopback TCP for daily builds
    os.environ.setdefault("AIOS_RCP_LOOPBACK", "1")
    asyncio.run(amain(args.host, args.port))


if __name__ == "__main__":
    main()
