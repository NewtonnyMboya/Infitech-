# INFILINK Live Connectivity (experimental)

This milestone adds a real TLS WebSocket transport for binary IILP/1 frames and a browser request/response client.

## Python server

Install the optional server dependency:

```sh
python -m pip install -r requirements-websocket.txt
```

Example application wiring (the authentication and authorization policies belong to the host application):

```python
import asyncio
import ssl
from core import MessageRouter, ServiceRegistry
from websocket_server import IILPWebSocketServer

async def main():
    registry = ServiceRegistry()
    async def echo(message):
        return {"echo": message["body"].get("value")}
    await registry.register("echo", echo, {"echo"})
    router = MessageRouter(registry)

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_3
    tls.load_cert_chain("server-cert.pem", "server-key.pem")

    def authenticate(headers):
        # Replace with a real server-side session/token verifier.
        # Return a trusted principal only after verification.
        return verify_application_session(headers.get("Cookie"))

    def authorize(principal, service, message):
        return application_policy_allows(principal, service, message)

    server = IILPWebSocketServer(
        router, tls,
        allowed_origins={"https://app.example.com"},
        authenticate=authenticate,
        authorize=authorize,
    )
    await server.start("0.0.0.0", 9444)
    await asyncio.Future()

asyncio.run(main())
```

The server requires TLS, an exact HTTPS Origin allowlist, the `iilp.v1` WebSocket subprotocol, authentication and per-message authorization callbacks. It accepts binary IILP frames only, applies bounded message size, connection count, queue size, idle/request timeout, ping/pong heartbeat and disables per-message compression. Each WebSocket message carries one IILP request frame and receives one response frame. The Core registry still controls service and message-type capabilities.

## Browser client

```js
import { IILPBrowserClient } from "./iilp-browser-client.mjs";

const client = new IILPBrowserClient({ baseUrl: "https://api.example.com" });
const socket = client.openWebSocket({ url: "wss://api.example.com/iilp" });
socket.addEventListener("open", async () => {
  try {
    const result = await client.sendWebSocket(socket, "orders", "order.read", {
      order_id: "ORD-100"
    });
    console.log(result);
  } catch (error) {
    console.error("IILP request failed", error);
  }
});
```

The client negotiates `iilp.v1`, sends binary frames, matches responses by request ID, and applies a request timeout. A WebSocket URL must use WSS; WS is allowed only on localhost development. Browser WebSocket handshakes include applicable cookies automatically; configure secure, HttpOnly, SameSite session cookies where appropriate. Never embed API keys or signing secrets in browser code.

## Operational and security notes

- The WebSocket server is a separate listener from the WSGI HTTP Bridge. Configure the reverse proxy/load balancer to forward WebSocket upgrades to the server.
- WebSocket Origin checks mitigate cross-site browser initiation but are not authentication. The supplied callbacks must verify real credentials and authorize each requested service/message. Never trust identity, role or scope values supplied in message bodies or arbitrary headers.
- Browser WebSocket APIs do not allow arbitrary Authorization headers. Prefer secure same-site session cookies or a short-lived, narrowly scoped, server-issued handshake credential; do not put reusable secrets in query strings.
- The sample callback names are placeholders; replace them with your application's actual session verifier and policy engine before deployment.
- Configure certificate renewal, connection/rate limits at the edge, observability, graceful shutdown and shared authentication state for multi-instance deployments.
- The server currently supports one IILP request per WebSocket message. Streaming, multiplexed request cancellation, reconnect/resume, cross-node session state and durable delivery are not implemented.
- This is experimental transport code, not a production security certification or an Internet standard.

Run the repository Python and JavaScript test suites through GitHub Actions before considering the transport validated.
