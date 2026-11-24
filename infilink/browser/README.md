# INFILINK Browser Integration (experimental)

The browser milestone adds a browser-native IILP/1 binary codec and a small JavaScript client for the existing HTTP JSON Bridge.

## Components

- `runtime/javascript/iilp.browser.mjs`: uses `Uint8Array`, `DataView`, `TextEncoder` and `TextDecoder`; it does not depend on Node.js `Buffer`.
- `runtime/javascript/iilp-browser-client.mjs`: sends bounded JSON requests to the Bridge endpoint and validates the response envelope. It also exposes an opt-in raw binary WebSocket connection helper and frame encode/decode methods.
- `runtime/javascript/iilp-browser.test.mjs`: Node.js tests for the browser-native codec and HTTP client.

## HTTP usage

Serve the modules from your own HTTPS application origin (or bundle them with your frontend):

```js
import { IILPBrowserClient } from "./iilp-browser-client.mjs";

const client = new IILPBrowserClient({
  baseUrl: "https://api.example.com"
});

const response = await client.send("orders", "order.create", {
  product_id: "SKU-42",
  quantity: 1
});

console.log(response.result);
```

The client uses HTTPS, CORS mode, `credentials: omit`, `cache: no-store`, redirect rejection, a request timeout and 1 MiB request/response limits. It creates a secure random request identifier and checks that the response ID matches. The browser's Fetch implementation still enforces browser CORS and mixed-content rules.

## WebSocket status

`openWebSocket({ url })` permits WSS, or WS only for localhost development. It configures binary frames and the codec can encode/decode IILP/1 frames. **A matching WebSocket server endpoint, authentication handshake and reconnect/backpressure protocol have not yet been implemented.** Do not point this helper at the current WSGI Bridge and assume WebSocket support.

## Deployment and security

- Configure the API server's CORS policy to allow only your real frontend origins and required methods/headers (`Content-Type`, `X-Request-ID`). CORS is not authentication.
- Keep the browser application and API on HTTPS. Localhost HTTP is allowed only for development.
- Never embed API keys, HMAC signing secrets, database credentials or private tokens in browser JavaScript. Anything shipped to a browser is public to that user.
- The current Bridge gateway does not yet invoke the Security module. Do not expose it publicly until server-side authentication, authorization, rate limiting, TLS termination and monitoring are integrated.
- Browser requests use the existing JSON gateway; this does not mean browsers natively speak the IILP binary protocol to the Python server.
- WebSocket binary framing is a client-side primitive only until the server profile is implemented and reviewed.

Run the full repository CI suite to test the browser modules. IILP remains experimental and is not a web standard.
