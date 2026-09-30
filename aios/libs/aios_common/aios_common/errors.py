"""Shared error codes aligned with RCP 13.8 and internal tools."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class ErrorCode(IntEnum):
    OK = 0
    BAD_FRAME = 1
    UNAUTH = 2
    FORBIDDEN = 3
    NEED_CONFIRM = 4
    NO_SESSION = 5
    NOT_FOUND = 6
    TIMEOUT = 7
    REVOKED = 8
    REPLAY = 9
    BUSY = 10
    DENIED_UI = 11
    INTERNAL = 100
    BUDGET_EXCEEDED = 101
    ASSERT_FAILED = 102
    CHANNEL_UNAVAILABLE = 103


@dataclass
class AiosError(Exception):
    code: ErrorCode
    reason: str
    data: Any = None

    def __str__(self) -> str:
        return f"{self.code.name}({int(self.code)}): {self.reason}"

    def to_dict(self) -> dict:
        d = {"code": int(self.code), "reason": self.reason}
        if self.data is not None:
            d["data"] = self.data
        return d


REASON = {
    ErrorCode.OK: "OK",
    ErrorCode.BAD_FRAME: "BAD_FRAME",
    ErrorCode.UNAUTH: "UNAUTH",
    ErrorCode.FORBIDDEN: "FORBIDDEN",
    ErrorCode.NEED_CONFIRM: "NEED_CONFIRM",
    ErrorCode.NO_SESSION: "NO_SESSION",
    ErrorCode.NOT_FOUND: "NOT_FOUND",
    ErrorCode.TIMEOUT: "TIMEOUT",
    ErrorCode.REVOKED: "REVOKED",
    ErrorCode.REPLAY: "REPLAY",
    ErrorCode.BUSY: "BUSY",
    ErrorCode.DENIED_UI: "DENIED_UI",
    ErrorCode.INTERNAL: "INTERNAL",
    ErrorCode.BUDGET_EXCEEDED: "BUDGET_EXCEEDED",
    ErrorCode.ASSERT_FAILED: "ASSERT_FAILED",
    ErrorCode.CHANNEL_UNAVAILABLE: "CHANNEL_UNAVAILABLE",
}