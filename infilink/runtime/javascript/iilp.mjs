/** Experimental IILP/1 codec for Node.js 20+; no third-party dependencies. */
import { Buffer } from "node:buffer";

export const MAGIC = Buffer.from("IILP", "ascii");
export const VERSION = 1;
export const HEADER_SIZE = 10;
export const MAX_PAYLOAD = 1_048_576;

function validate(message) {
  if (!message || typeof message !== "object" || Array.isArray(message))
    throw new TypeError("message must be an object");
  if (typeof message.type !== "string" || message.type.length < 1 || message.type.length > 64)
    throw new TypeError("type must contain 1..64 characters");
  if (typeof message.id !== "string" || message.id.length < 1 || message.id.length > 128)
    throw new TypeError("id must contain 1..128 characters");
  if (!Object.hasOwn(message, "body")) throw new TypeError("body is required");
  if (message.extensions !== undefined &&
      (!message.extensions || typeof message.extensions !== "object" || Array.isArray(message.extensions)))
    throw new TypeError("extensions must be an object");
}

export function encode(message) {
  validate(message);
  const payload = Buffer.from(JSON.stringify(message), "utf8");
  if (payload.length > MAX_PAYLOAD) throw new RangeError("payload exceeds 1 MiB limit");
  const frame = Buffer.alloc(HEADER_SIZE + payload.length);
  MAGIC.copy(frame, 0);
  frame.writeUInt8(VERSION, 4);
  frame.writeUInt8(0, 5);
  frame.writeUInt32BE(payload.length, 6);
  payload.copy(frame, HEADER_SIZE);
  return frame;
}

export function decode(frame) {
  if (!Buffer.isBuffer(frame)) frame = Buffer.from(frame);
  if (frame.length < HEADER_SIZE) throw new Error("truncated header");
  if (!frame.subarray(0, 4).equals(MAGIC)) throw new Error("invalid magic");
  if (frame.readUInt8(4) !== VERSION) throw new Error("unsupported version");
  if (frame.readUInt8(5) !== 0) throw new Error("reserved flags must be zero");
  const length = frame.readUInt32BE(6);
  if (length > MAX_PAYLOAD) throw new RangeError("payload exceeds 1 MiB limit");
  if (frame.length !== HEADER_SIZE + length) throw new Error("truncated payload or trailing bytes");
  const text = new TextDecoder("utf-8", { fatal: true }).decode(frame.subarray(HEADER_SIZE));
  const message = JSON.parse(text);
  validate(message);
  return message;
}
