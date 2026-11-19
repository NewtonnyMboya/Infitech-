/** Browser HTTP/WebSocket helpers for the experimental INFILINK Bridge. */
import { encode, decode, MAX_PAYLOAD } from "./iilp.browser.mjs";

const SERVICE = /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/;
const MESSAGE_TYPE = /^[A-Za-z][A-Za-z0-9_.:-]{0,63}$/;

function makeId(cryptoProvider) {
  if (typeof cryptoProvider?.randomUUID === "function") return cryptoProvider.randomUUID();
  if (typeof cryptoProvider?.getRandomValues !== "function")
    throw new Error("secure browser crypto is required");
  const bytes = cryptoProvider.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
}

function validateBaseUrl(value) {
  const url = new URL(value);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.username || url.password || url.search || url.hash ||
      (url.protocol !== "https:" && !(local && url.protocol === "http:")))
    throw new TypeError("base URL must use HTTPS (HTTP is allowed only on localhost)");
  url.pathname = url.pathname.replace(/\/$/, "");
  return url;
}

export class IILPBrowserClient {
  constructor({ baseUrl, fetchImpl = globalThis.fetch, cryptoProvider = globalThis.crypto,
                timeoutMs = 10_000 } = {}) {
    if (typeof fetchImpl !== "function") throw new TypeError("Fetch API is required");
    if (!Number.isInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 120_000)
      throw new RangeError("timeoutMs must be 100..120000");
    this.baseUrl = validateBaseUrl(baseUrl);
    this.fetchImpl = fetchImpl;
    this.cryptoProvider = cryptoProvider;
    this.timeoutMs = timeoutMs;
  }

  async send(service, type, body) {
    if (typeof service !== "string" || !SERVICE.test(service))
      throw new TypeError("invalid service name");
    if (typeof type !== "string" || !MESSAGE_TYPE.test(type))
      throw new TypeError("invalid message type");
    if (!body || typeof body !== "object" || Array.isArray(body))
      throw new TypeError("body must be a JSON object");
    const id = makeId(this.cryptoProvider);
    const payload = JSON.stringify({ type, body });
    if (new TextEncoder().encode(payload).byteLength > MAX_PAYLOAD)
      throw new RangeError("request exceeds 1 MiB limit");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const base = this.baseUrl.href.replace(/\/$/, "");
      const url = new URL(`${base}/v1/services/${encodeURIComponent(service)}/messages`);
      const response = await this.fetchImpl(url, {
        method: "POST", mode: "cors", credentials: "omit", cache: "no-store",
        redirect: "error", signal: controller.signal,
        headers: { "Accept": "application/json", "Content-Type": "application/json",
                   "X-Request-ID": id },
        body: payload
      });
      const contentType = response.headers?.get?.("content-type") || "";
      if (!contentType.toLowerCase().includes("application/json"))
        throw new Error("gateway response is not JSON");
      const raw = await response.text();
      if (new TextEncoder().encode(raw).byteLength > MAX_PAYLOAD)
        throw new RangeError("gateway response exceeds 1 MiB limit");
      let result;
      try { result = JSON.parse(raw); } catch { throw new Error("gateway returned invalid JSON"); }
      if (!response.ok) throw new Error(result?.detail || result?.error || `HTTP ${response.status}`);
      if (!result || result.id !== id || result.type !== "response" ||
          !result.body || typeof result.body !== "object")
        throw new Error("gateway response envelope does not match request");
      return result.body;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Open a raw IILP binary WebSocket. The server must implement this framing profile. */
  openWebSocket({ url, protocols = ["iilp.v1"] } = {}) {
    const target = new URL(url);
    const offered = Array.isArray(protocols) ? protocols : [protocols];
    if (!offered.includes("iilp.v1")) throw new TypeError("iilp.v1 WebSocket subprotocol is required");
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(target.hostname);
    if (target.username || target.password || target.search || target.hash ||
        (target.protocol !== "wss:" && !(local && target.protocol === "ws:")))
      throw new TypeError("WebSocket URL must use WSS (WS is allowed only on localhost)");
    if (typeof globalThis.WebSocket !== "function") throw new Error("WebSocket API is unavailable");
    const socket = new globalThis.WebSocket(target, protocols);
    socket.binaryType = "arraybuffer";
    return socket;
  }

  async sendWebSocket(socket, service, type, body, timeoutMs = this.timeoutMs) {
    if (!socket || socket.readyState !== 1 || typeof socket.send !== "function")
      throw new Error("WebSocket must be open before sending");
    if (typeof service !== "string" || !SERVICE.test(service)) throw new TypeError("invalid service name");
    if (typeof type !== "string" || !MESSAGE_TYPE.test(type)) throw new TypeError("invalid message type");
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new TypeError("body must be a JSON object");
    if (!Number.isInteger(timeoutMs) || timeoutMs < 100 || timeoutMs > 120_000) throw new RangeError("timeoutMs must be 100..120000");
    const id = makeId(this.cryptoProvider);
    const frame = encode({ type, id, body: { ...body, target: service } });
    return await new Promise((resolve, reject) => {
      const cleanup = () => { clearTimeout(timer); socket.removeEventListener("message", onMessage); socket.removeEventListener("close", onClose); socket.removeEventListener("error", onError); };
      const timer = setTimeout(() => { cleanup(); reject(new Error("WebSocket request timed out")); }, timeoutMs);
      const onClose = () => { cleanup(); reject(new Error("WebSocket closed before response")); };
      const onError = () => { cleanup(); reject(new Error("WebSocket transport error")); };
      const onMessage = async event => {
        try {
          let data = event.data;
          if (typeof Blob !== "undefined" && data instanceof Blob) data = await data.arrayBuffer();
          if (!(data instanceof ArrayBuffer) && !ArrayBuffer.isView(data)) return;
          const response = decode(data);
          if (response.id !== id) return;
          cleanup();
          if (response.type !== "response" || !response.body || response.body.ok !== true) reject(new Error(response.body?.error || "IILP WebSocket request failed"));
          else resolve(response.body.result);
        } catch (error) { cleanup(); reject(error); }
      };
      socket.addEventListener("message", onMessage);
      socket.addEventListener("close", onClose, { once: true });
      socket.addEventListener("error", onError, { once: true });
      try { socket.send(frame); } catch (error) { cleanup(); reject(error); }
    });
  }

  encodeFrame(message) { return encode(message); }
  decodeFrame(frame) { return decode(frame); }
}
