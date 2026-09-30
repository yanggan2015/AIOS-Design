
"""rcp-dump — hex + field decode for RCP frames."""
from __future__ import annotations

import argparse
import binascii
import json
import sys

from aios_common.proto.rcp import MSG_NAMES, FrameError, decode_exact, encode_frame, Frame, MsgId


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rcp-dump")
    ap.add_argument("hex", nargs="?", help="frame hex string")
    ap.add_argument("--build", help="build sample: HELLO|PING|WIN_LIST")
    ap.add_argument("--seq", type=int, default=1)
    args = ap.parse_args(argv)

    if args.build:
        name = args.build.upper()
        mid = getattr(MsgId, name)
        frame = Frame(msg_id=int(mid), seq=args.seq, payload={"ts": 0})
        raw = encode_frame(frame)
        print(raw.hex())
        print(json.dumps({"msg": name, "len": len(raw)}, indent=2))
        return

    if not args.hex:
        ap.error("hex or --build required")
    data = binascii.unhexlify(args.hex.replace(" ", "").replace("\n", ""))
    try:
        frame = decode_exact(data)
    except FrameError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({
        "msg_id": hex(frame.msg_id),
        "msg": MSG_NAMES.get(frame.msg_id, "?"),
        "seq": frame.seq,
        "flags": frame.flags,
        "payload": frame.payload,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
