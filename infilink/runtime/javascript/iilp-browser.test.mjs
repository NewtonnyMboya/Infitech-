import test from "node:test";
import assert from "node:assert/strict";
import { encode, decode, HEADER_SIZE } from "./iilp.browser.mjs";
import { IILPBrowserClient } from "./iilp-browser-client.mjs";

const cryptoProvider = { randomUUID: () => "browser-request-123" };

test("browser codec round-trips UTF-8 frames", () => {
  const message = { type: "event", id: "browser-1", body: { text: "Athi River 🌍" } };
  const frame = encode(message);
  assert.ok(frame instanceof Uint8Array);
  assert.deepEqual(decode(frame), message);
});

test("browser codec rejects malformed frames and flags", () => {
  const frame = encode({ type: "event", id: "id", body: {} });
  const invalid = frame.slice();
  invalid[5] = 1;
  assert.throws(() => decode(invalid), /flags/);
  assert.throws(() => decode(frame.slice(0, HEADER_SIZE - 1)), /header/);
});

test("browser client posts JSON to the Bridge and validates response id", async () => {
  let captured;
  const fetchImpl = async (url, options) => {
    captured = { url: String(url), options };
    return {
      ok: true, status: 200,
      headers: { get: () => "application/json; charset=utf-8" },
      text: async () => JSON.stringify({
        type: "response", id: "browser-request-123",
        body: { ok: true, result: { accepted: true } }
      })
    };
  };
  const client = new IILPBrowserClient({
    baseUrl: "https://api.example.test",
    fetchImpl, cryptoProvider
  });
  const response = await client.send("orders", "order.create", { item: "book" });
  assert.deepEqual(response, { ok: true, result: { accepted: true } });
  assert.equal(captured.url, "https://api.example.test/v1/services/orders/messages");
  assert.equal(captured.options.credentials, "omit");
  assert.equal(captured.options.redirect, "error");
  assert.equal(captured.options.headers["X-Request-ID"], "browser-request-123");
});

test("browser client respects a configured API path prefix", async () => {
  let requestedUrl;
  const client = new IILPBrowserClient({
    baseUrl: "https://api.example.test/edge/",
    cryptoProvider,
    fetchImpl: async url => {
      requestedUrl = String(url);
      return {
        ok: true, status: 200,
        headers: { get: () => "application/json" },
        text: async () => JSON.stringify({
          type: "response", id: "browser-request-123", body: { ok: true }
        })
      };
    }
  });
  await client.send("catalog", "catalog.list", {});
  assert.equal(requestedUrl, "https://api.example.test/edge/v1/services/catalog/messages");
});

test("browser client rejects a mismatched response id", async () => {
  const client = new IILPBrowserClient({
    baseUrl: "https://api.example.test",
    cryptoProvider,
    fetchImpl: async () => ({
      ok: true, status: 200,
      headers: { get: () => "application/json" },
      text: async () => JSON.stringify({ type: "response", id: "wrong", body: {} })
    })
  });
  await assert.rejects(client.send("orders", "order.read", {}), /does not match/);
});

test("browser client restricts insecure origins and malformed inputs", async () => {
  assert.throws(() => new IILPBrowserClient({ baseUrl: "http://api.example.test" }),
                /HTTPS/);
  assert.throws(() => new IILPBrowserClient({ baseUrl: "https://user:pass@example.test" }),
                /HTTPS/);
  const client = new IILPBrowserClient({
    baseUrl: "https://api.example.test", cryptoProvider,
    fetchImpl: async () => { throw new Error("should not be called"); }
  });
  await assert.rejects(client.send("../admin", "order.read", {}), /service name/);
  await assert.rejects(client.send("orders", "order.read", []), /JSON object/);
});

class FakeSocket {
  constructor() { this.readyState = 1; this.listeners = new Map(); this.sent = []; }
  addEventListener(name, fn) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name).add(fn);
  }
  removeEventListener(name, fn) { this.listeners.get(name)?.delete(fn); }
  send(frame) {
    this.sent.push(frame);
    const request = decode(frame);
    const reply = encode({
      type: "response", id: request.id,
      body: { ok: true, result: { received: request.body.value, target: request.body.target } }
    });
    queueMicrotask(() => {
      for (const fn of this.listeners.get("message") || []) fn({ data: reply.buffer.slice(reply.byteOffset, reply.byteOffset + reply.byteLength) });
    });
  }
}

test("browser WebSocket client sends binary IILP and resolves matching response", async () => {
  const client = new IILPBrowserClient({
    baseUrl: "https://api.example.test", cryptoProvider
  });
  const socket = new FakeSocket();
  const result = await client.sendWebSocket(socket, "orders", "order.read", { value: 42 });
  assert.deepEqual(result, { received: 42, target: "orders" });
  assert.deepEqual(decode(socket.sent[0]).body, { value: 42, target: "orders" });
});

test("browser WebSocket client rejects a closed socket", async () => {
  const client = new IILPBrowserClient({
    baseUrl: "https://api.example.test", cryptoProvider
  });
  await assert.rejects(client.sendWebSocket({ readyState: 3 }, "orders", "order.read", {}),
                       /must be open/);
});

test("browser WebSocket requires the IILP subprotocol", () => {
  const client = new IILPBrowserClient({ baseUrl: "https://api.example.test", cryptoProvider });
  assert.throws(
    () => client.openWebSocket({ url: "wss://api.example.test/iilp", protocols: ["other"] }),
    /subprotocol/
  );
});
