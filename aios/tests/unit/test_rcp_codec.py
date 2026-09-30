"""Unit tests: RCP codec."""
from aios_common.proto.rcp import (
    FLAG_JSON,
    FLAG_NEED_ACK,
    Frame,
    FrameError,
    MsgId,
    crc32,
    decode_exact,
    encode_frame,
    nack,
    try_decode,
)


def test_roundtrip_json():
    f = Frame(msg_id=MsgId.WIN_LIST, seq=7, payload={"sid": "s_1", "ts": 1})
    raw = encode_frame(f)
    assert raw[:2] == b"\xa1\x05"
    got = decode_exact(raw)
    assert got.msg_id == MsgId.WIN_LIST
    assert got.seq == 7
    assert got.payload["sid"] == "s_1"


def test_roundtrip_cbor():
    f = Frame(msg_id=MsgId.PING, seq=1, payload={"x": 1}, flags=FLAG_NEED_ACK)  # no JSON bit
    raw = encode_frame(f)
    got = decode_exact(raw)
    assert got.payload == {"x": 1}
    assert not (got.flags & FLAG_JSON)


def test_bad_crc():
    f = Frame(msg_id=MsgId.PING, seq=1, payload={})
    raw = bytearray(encode_frame(f))
    raw[-1] ^= 0xFF
    buf = raw
    try:
        try_decode(buf)
        assert False, "expected FrameError"
    except FrameError as e:
        assert "CRC" in str(e)


def test_resync_sof():
    f = Frame(msg_id=MsgId.PONG, seq=2, payload={"a": True})
    good = encode_frame(f)
    buf = bytearray(b"\x00\x01\x02" + good)
    frame, n = try_decode(buf)
    # first call may only skip garbage
    if frame is None:
        frame, n2 = try_decode(buf)
        n += n2
    assert frame is not None
    assert frame.seq == 2


def test_nack_helper():
    fr = nack(3, 2, "UNAUTH")
    assert fr.msg_id == MsgId.NACK
    assert fr.payload["code"] == 2


def test_crc_stable():
    import zlib

    assert crc32(b"\xa1\x05") == (zlib.crc32(b"\xa1\x05") & 0xFFFFFFFF)
