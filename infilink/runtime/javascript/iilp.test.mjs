import test from "node:test";
import assert from "node:assert/strict";
import { encode, decode } from "./iilp.mjs";

test("IILP/1 round-trip", () => {
  const value = { type: "ping", id: "js-test-1", body: { greeting: "hello 🌍" } };
  assert.deepEqual(decode(encode(value)), value);
});

test("rejects malformed magic", () => {
  const frame = encode({ type: "ping", id: "1", body: {} });
  frame[0] = 0;
  assert.throws(() => decode(frame), /magic/);
});

test("rejects trailing bytes", () => {
  const frame = encode({ type: "ping", id: "1", body: {} });
  assert.throws(() => decode(Buffer.concat([frame, Buffer.from([0])])), /trailing/);
});

test("rejects missing body", () => {
  assert.throws(() => encode({ type: "ping", id: "1" }), /body/);
});
