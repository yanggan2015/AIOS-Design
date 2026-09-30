"""RCP binary frame codec — design §13.4–13.8."""
from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional, Tuple

import cbor2

SOF = b"\xA1\x05"
VER = 0x01
HEADER_FMT = ">2sBBIIHI"  # sof(2) already separate; we pack manually
HEADER_SIZE = 18
MAX_PAYLOAD = 65536
CRC_SIZE = 4

FLAG_NEED_ACK = 0x01
FLAG_JSON = 0x02
FLAG_COMPRESS = 0x04  # reserved


class MsgId(IntEnum):
    HELLO = 0x0001
    HELLO_ACK = 0x0002
    AUTH = 0x0010
    AUTH_OK = 0x0011
    AUTH_FAIL = 0x0012
    PING = 0x0020
    PONG = 0x0021
    SYS_INFO = 0x0100
    SYS_CALL = 0x0101
    APP_LIST = 0x0200
    APP_LAUNCH = 0x0201
    APP_CLOSE = 0x0202
    WIN_LIST = 0x0210
    DCP_SNAPSHOT = 0x0211
    DCP_FIND = 0x0212
    DCP_ACT = 0x0213
    DCP_ASSERT = 0x0214
    AGENT_RUN = 0x0300
    AGENT_EVENT = 0x0301
    AGENT_ABORT = 0x0302
    CONFIRM_REQ = 0x03F0
    CONFIRM_RSP = 0x03F1
    ACK = 0x7F00
    NACK = 0x7F01
    LINK_RESET = 0x7F10
    LINK_SET_BAUD = 0x7F11


MSG_NAMES = {int(m): m.name for m in MsgId}


def crc32(data: bytes) -> int:
    """CRC-32/ISO-HDLC (zlib)."""
    return zlib.crc32(data) & 0xFFFFFFFF


@dataclass
class Frame:
    msg_id: int
    seq: int
    payload: dict = field(default_factory=dict)
    flags: int = FLAG_NEED_ACK | FLAG_JSON
    ver: int = VER

    @property
    def need_ack(self) -> bool:
        return bool(self.flags & FLAG_NEED_ACK)

    @property
    def use_json(self) -> bool:
        return bool(self.flags & FLAG_JSON)


class FrameError(ValueError):
    pass


def encode_payload(payload: dict, use_json: bool) -> bytes:
    if use_json:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return cbor2.dumps(payload)


def decode_payload(raw: bytes, use_json: bool) -> dict:
    if not raw:
        return {}
    if use_json:
        return json.loads(raw.decode("utf-8"))
    obj = cbor2.loads(raw)
    if not isinstance(obj, dict):
        raise FrameError("payload must be map")
    return obj


def encode_frame(frame: Frame) -> bytes:
    body = encode_payload(frame.payload, frame.use_json)
    if len(body) > MAX_PAYLOAD:
        raise FrameError(f"payload too large: {len(body)}")
    header = struct.pack(
        ">2sBBIIHI",
        SOF,
        frame.ver & 0xFF,
        frame.flags & 0xFF,
        frame.msg_id & 0xFFFFFFFF,
        frame.seq & 0xFFFFFFFF,
        0,  # RSV
        len(body) & 0xFFFFFFFF,
    )
    # struct: 2s B B I I H I = 2+1+1+4+4+2+4 = 18 ✓
    assert len(header) == HEADER_SIZE
    blob = header + body
    return blob + struct.pack(">I", crc32(blob))


def try_decode(buf: bytearray) -> Tuple[Optional[Frame], int]:
    """
    Try to decode one frame from buffer.
    Returns (frame_or_None, bytes_consumed).
    On incomplete data returns (None, 0).
    On bad SOF/CRC may consume and skip.
    """
    if len(buf) < HEADER_SIZE + CRC_SIZE:
        return None, 0

    # Resync to SOF
    idx = buf.find(SOF)
    if idx < 0:
        # keep last byte in case split SOF
        keep = 1 if buf and buf[-1] == SOF[0] else 0
        consumed = len(buf) - keep
        del buf[:consumed]
        return None, consumed
    if idx > 0:
        del buf[:idx]
        return None, idx

    if len(buf) < HEADER_SIZE:
        return None, 0

    sof, ver, flags, msg_id, seq, rsv, length = struct.unpack_from(">2sBBIIHI", buf, 0)
    if sof != SOF:
        del buf[:1]
        return None, 1
    if ver != VER:
        # consume header+payload+crc if possible else wait
        total = HEADER_SIZE + length + CRC_SIZE
        if len(buf) < total:
            return None, 0
        del buf[:total]
        raise FrameError(f"bad version {ver}")
    if length > MAX_PAYLOAD:
        del buf[:HEADER_SIZE]
        raise FrameError("LEN exceeds max")

    total = HEADER_SIZE + length + CRC_SIZE
    if len(buf) < total:
        return None, 0

    blob = bytes(buf[: HEADER_SIZE + length])
    (got_crc,) = struct.unpack_from(">I", buf, HEADER_SIZE + length)
    expect = crc32(blob)
    if got_crc != expect:
        del buf[:total]
        raise FrameError(f"CRC mismatch got={got_crc:#x} expect={expect:#x}")

    body = bytes(buf[HEADER_SIZE : HEADER_SIZE + length])
    del buf[:total]
    use_json = bool(flags & FLAG_JSON)
    try:
        payload = decode_payload(body, use_json)
    except Exception as e:
        raise FrameError(f"payload decode: {e}") from e

    return Frame(msg_id=msg_id, seq=seq, payload=payload, flags=flags, ver=ver), total


def decode_exact(data: bytes) -> Frame:
    buf = bytearray(data)
    frame, n = try_decode(buf)
    if frame is None:
        raise FrameError("incomplete frame")
    if buf:
        raise FrameError("trailing bytes")
    return frame


def nack(seq: int, code: int, reason: str, data: Any = None, sid: str | None = None) -> Frame:
    payload: dict[str, Any] = {"code": code, "reason": reason}
    if data is not None:
        payload["data"] = data
    if sid:
        payload["sid"] = sid
    return Frame(msg_id=MsgId.NACK, seq=seq, payload=payload)


def ack(seq: int, data: Any = None, reason: str = "OK", sid: str | None = None) -> Frame:
    payload: dict[str, Any] = {"code": 0, "reason": reason}
    if data is not None:
        payload["data"] = data
    if sid:
        payload["sid"] = sid
    return Frame(msg_id=MsgId.ACK, seq=seq, payload=payload)