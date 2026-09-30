export interface RcpFrame {
  msgId: number;
  seq: number;
  payload: Record<string, unknown>;
  flags: number;
}

export const SOF = Uint8Array.from([0xa1, 0x05]);
export const MsgId = {
  HELLO: 0x0001,
  HELLO_ACK: 0x0002,
  AUTH: 0x0010,
  AUTH_OK: 0x0011,
  PING: 0x0020,
  PONG: 0x0021,
  WIN_LIST: 0x0210,
  DCP_ACT: 0x0213,
  NACK: 0x7f01,
  ACK: 0x7f00,
} as const;

function crc32(buf: Uint8Array): number {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) {
      c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
    }
  }
  return ~c >>> 0;
}

export function encodeFrame(frame: RcpFrame): Uint8Array {
  const body = new TextEncoder().encode(JSON.stringify(frame.payload ?? {}));
  const header = new ArrayBuffer(18);
  const v = new DataView(header);
  v.setUint8(0, 0xa1);
  v.setUint8(1, 0x05);
  v.setUint8(2, 1);
  v.setUint8(3, frame.flags ?? 0x03);
  v.setUint32(4, frame.msgId);
  v.setUint32(8, frame.seq);
  v.setUint16(12, 0);
  v.setUint32(14, body.length);
  const blob = new Uint8Array(18 + body.length);
  blob.set(new Uint8Array(header), 0);
  blob.set(body, 18);
  const out = new Uint8Array(blob.length + 4);
  out.set(blob, 0);
  const crc = crc32(blob);
  new DataView(out.buffer).setUint32(blob.length, crc);
  return out;
}

/** Browser/Node TCP client is environment-specific; this package ships codec + types. */
export class RcpCodec {
  static encode = encodeFrame;
  static crc32 = crc32;
}
