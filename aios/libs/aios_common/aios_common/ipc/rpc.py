"""JSON-RPC-ish Unix socket IPC between luminOS daemons."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from aios_common.errors import AiosError, ErrorCode
from aios_common.paths import sock_path

log = logging.getLogger("aios.ipc")

Handler = Callable[[dict], Awaitable[Any]]


@dataclass
class RpcRequest:
    method: str
    params: dict
    id: str


class RpcServer:
    def __init__(self, name: str):
        self.name = name
        self.path = sock_path(name)
        self._handlers: Dict[str, Handler] = {}
        self._server: Optional[asyncio.AbstractServer] = None

    def method(self, name: str):
        def deco(fn: Handler):
            self._handlers[name] = fn
            return fn

        return deco

    def register(self, name: str, fn: Handler) -> None:
        self._handlers[name] = fn

    async def start(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self._server = await asyncio.start_unix_server(self._on_client, path=str(self.path))
        os.chmod(self.path, 0o600)
        log.info("%s listening on %s", self.name, self.path)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self.path.exists():
            self.path.unlink(missing_ok=True)

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    await self._write(writer, {"id": None, "error": {"code": 1, "reason": "BAD_JSON"}})
                    continue
                req_id = msg.get("id") or str(uuid.uuid4())
                method = msg.get("method")
                params = msg.get("params") or {}
                if method not in self._handlers:
                    await self._write(
                        writer,
                        {"id": req_id, "error": {"code": int(ErrorCode.NOT_FOUND), "reason": f"unknown method {method}"}},
                    )
                    continue
                try:
                    result = await self._handlers[method](params)
                    await self._write(writer, {"id": req_id, "result": result})
                except AiosError as e:
                    await self._write(writer, {"id": req_id, "error": e.to_dict()})
                except Exception as e:  # noqa: BLE001
                    log.exception("handler %s failed", method)
                    await self._write(
                        writer,
                        {"id": req_id, "error": {"code": int(ErrorCode.INTERNAL), "reason": str(e)}},
                    )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    async def _write(self, writer: asyncio.StreamWriter, obj: dict) -> None:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        writer.write(data)
        await writer.drain()


class RpcClient:
    def __init__(self, name: str, timeout: float = 30.0):
        self.name = name
        self.path = sock_path(name)
        self.timeout = timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_unix_connection(str(self.path))

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        self._reader = self._writer = None

    async def call(self, method: str, params: Optional[dict] = None) -> Any:
        if not self._writer or not self._reader:
            await self.connect()
        assert self._writer and self._reader
        req_id = str(uuid.uuid4())
        msg = {"id": req_id, "method": method, "params": params or {}}
        async with self._lock:
            self._writer.write((json.dumps(msg) + "\n").encode("utf-8"))
            await self._writer.drain()
            try:
                line = await asyncio.wait_for(self._reader.readline(), timeout=self.timeout)
            except asyncio.TimeoutError as e:
                raise AiosError(ErrorCode.TIMEOUT, f"rpc {self.name}.{method} timeout") from e
        if not line:
            raise AiosError(ErrorCode.INTERNAL, f"rpc {self.name} connection closed")
        resp = json.loads(line.decode("utf-8"))
        if "error" in resp and resp["error"]:
            err = resp["error"]
            raise AiosError(ErrorCode(err.get("code", 100)), err.get("reason", "error"), err.get("data"))
        return resp.get("result")


async def call(name: str, method: str, params: Optional[dict] = None, timeout: float = 30.0) -> Any:
    client = RpcClient(name, timeout=timeout)
    try:
        return await client.call(method, params)
    finally:
        await client.close()


def ensure_socket_gone(name: str) -> Path:
    p = sock_path(name)
    if p.exists():
        p.unlink()
    return p