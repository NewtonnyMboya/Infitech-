/** Browser-native IILP/1 codec. No Node.js APIs or third-party dependencies. */
export const MAGIC = new Uint8Array([0x49, 0x49, 0x4c, 0x50]);
export const VERSION = 1;
export const HEADER_SIZE = 10;
export const MAX_PAYLOAD = 1_048_576;
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });

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
  const payload = encoder.encode(JSON.stringify(message));
  if (payload.byteLength > MAX_PAYLOAD) throw new RangeError("payload exceeds 1 MiB limit");
  const frame = new Uint8Array(HEADER_SIZE + payload.byteLength);
  frame.set(MAGIC, 0);
  frame[4] = VERSION;
  frame[5] = 0;
  new DataView(frame.buffer).setUint32(6, payload.byteLength, false);
  frame.set(payload, HEADER_SIZE);
  return frame;
}

export function decode(input) {
  const frame = input instanceof Uint8Array ? input : new Uint8Array(input);
  if (frame.byteLength < HEADER_SIZE) throw new Error("truncated header");
  if (!MAGIC.every((value, index) => frame[index] === value)) throw new Error("invalid magic");
  if (frame[4] !== VERSION) throw new Error("unsupported version");
  if (frame[5] !== 0) throw new Error("reserved flags must be zero");
  const length = new DataView(frame.buffer, frame.byteOffset, frame.byteLength).getUint32(6, false);
  if (length > MAX_PAYLOAD) throw new RangeError("payload exceeds 1 MiB limit");
  if (frame.byteLength !== HEADER_SIZE + length) throw new Error("truncated payload or trailing bytes");
  const message = JSON.parse(decoder.decode(frame.subarray(HEADER_SIZE)));
  validate(message);
  return message;
}
