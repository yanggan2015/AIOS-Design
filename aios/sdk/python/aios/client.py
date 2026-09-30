
"""High-level Python SDK for local RPC and RCP."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from aios_common.ipc import call as rpc_call
from aios_common.paths import runtime_dir
from aios_common.proto.rcp import FLAG_JSON, FLAG_NEED_ACK, Frame, MsgId, encode_frame, try_decode


class Client:
    """Local Unix-RPC client helpers."""

    async def dcp_targets(self):
        return await rpc_call("dcpd", "list_targets", {})

    async def dcp_act(self, target: str, action: str, args: dict):
        return await rpc_call("dcpd", "act", {"target": target, "action": action, "args": args})

    async def agent_run(self, goal: str, **opts):
        return await rpc_call("agentd", "run", {"goal": goal, "opts": opts})

    async def ping(self, service: str = "dcpd"):
        return await rpc_call(service, "ping", {})


class RcpClient:
    def __init__(self, path: Optional[str] = None, host: str = "127.0.0.1", port: int = 17420, use_tcp: bool = False):
        self.path = path or str(runtime_dir() / "rcp.sock")
        self.host = host
        self.port = port
        self.use_tcp = use_tcp
        self.sid = None
        self._seq = 0
        self._reader = None
        self._writer = None

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    async def connect(self):
        if self.use_tcp:
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        else:
            self._reader, self._writer = await asyncio.open_unix_connection(self.path)

    async def close(self):
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    async def request(self, msg_id: int, payload: dict | None = None) -> Frame:
        if not self._writer:
            await self.connect()
        payload = dict(payload or {})
        if self.sid:
            payload["sid"] = self.sid
        payload.setdefault("ts", int(time.time() * 1000))
        frame = Frame(msg_id=msg_id, seq=self._next_seq(), payload=payload, flags=FLAG_NEED_ACK | FLAG_JSON)
        self._writer.write(encode_frame(frame))
        await self._writer.drain()
        buf = bytearray()
        while True:
            chunk = await self._reader.read(4096)
            if not chunk:
                raise ConnectionError("rcp closed")
            buf.extend(chunk)
            resp, _ = try_decode(buf)
            if resp is not None:
                return resp

    async def hello(self):
        return await self.request(MsgId.HELLO, {"client_id": "py-sdk", "ver": 1, "transport": "unix"})

    async def auth_pairing(self, code: str):
        resp = await self.request(MsgId.AUTH, {"mode": "pairing_code", "code": code, "client_id": "py-sdk"})
        if resp.msg_id == MsgId.AUTH_OK:
            self.sid = resp.payload.get("sid")
        return resp

    async def win_list(self):
        return await self.request(MsgId.WIN_LIST, {})

    async def dcp_act(self, target: str, action: str, **args):
        return await self.request(MsgId.DCP_ACT, {"target": target, "args": {"action": action, **args}})
