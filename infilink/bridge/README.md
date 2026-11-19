# INFILINK Bridge

Bridge connects external HTTP applications and APIs to explicitly registered INFILINK
Core services. This milestone includes a WSGI JSON gateway and a restricted outbound
HTTPS JSON client.

## Inbound gateway

The gateway accepts:

- `GET /health`
- `POST /v1/services/{service}/messages`

Example JSON request:

```json
{"type":"echo","body":{"text":"hello"}}
```

The gateway adds the selected service as `body.target`, validates the envelope by
encoding and decoding an IILP/1 frame, then dispatches only through the Core registry.
Request bodies are limited to 1 MiB (configurable downward), and responses include
`Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

## Run locally (development only)

From the `infilink/` directory, with `runtime/python` on `PYTHONPATH`:

```sh
PYTHONPATH=runtime/python python -c 'from core import ServiceRegistry, MessageRouter; from bridge import create_wsgi_app; from wsgiref.simple_server import make_server; import asyncio; r=ServiceRegistry(); asyncio.run(r.register("echo", lambda m: asyncio.sleep(0, result={"echo":m["body"]}), {"echo"})); make_server("127.0.0.1", 8080, create_wsgi_app(MessageRouter(r))).serve_forever()'
```

This example is for local development. The WSGI gateway does not terminate TLS or
authenticate users. In production, place it behind a correctly configured TLS 1.3
reverse proxy and add authentication, authorization, rate limiting, audit logging and
request-level identity before exposing it to any network.

## Outbound HTTPS adapter

`AllowlistedHTTPSClient` only accepts HTTPS URLs whose exact origin is configured.
Redirects are disabled, request and response bodies are bounded, and response JSON
must be an object. Provider-specific OAuth/OIDC, signing, pagination and retry policies
must be implemented deliberately by the integration using this client. Never put API
secrets in source control.

## Limitations

This is a starter bridge, not a general-purpose browser, proxy or arbitrary URL fetcher.
It does not support WebSocket, OAuth token acquisition, automatic retries, streaming,
or direct database credentials. External calls are synchronous and should be isolated
from latency-sensitive event loops.
