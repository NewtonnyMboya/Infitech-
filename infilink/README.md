# INFILINK

**International InfiLink Protocol (IILP)** is a proposed, open, versioned interoperability layer for applications and services. This repository starts with a deliberately small, testable foundation rather than claiming universal compatibility prematurely.

## Architecture

- **IILP wire format** — bounded, versioned messages with canonical JSON payloads.
- **IIL Runtime** — bounded registry for trusted language adapters (Python reference adapter implemented).
- **IIL DataCore** — SQLite reference storage, versioned schemas, document CRUD, indexes, backups and integrity checks (reference adapter implemented).
- **IIL Bridge** — bounded JSON-over-HTTP gateway and allowlisted outbound HTTPS JSON client (starter adapters implemented).
- **IIL Cloud** — validated Kubernetes Deployment and internal Service manifest generator (starter implemented; deployment execution remains operator-controlled).
- **IIL Security** — experimental API keys, explicit scopes/RBAC, HMAC request signing with replay checks, bounded audit events and opaque browser WebSocket sessions (process-local reference implementation).
- **IIL Browser and Live Connectivity** — browser-native IILP/1 codec, HTTPS Bridge client, authenticated TLS WebSocket transport and binary request/response client (experimental starter implemented).

## Compatibility strategy

Do not reimplement every language, server, browser, operating system or Internet protocol. Integrate through documented adapters and existing standards: HTTP(S), DNS, TLS, TCP, QUIC, WebSocket, OAuth/OIDC, SQL, object storage and language-specific runtimes. Unsupported features must fail explicitly and safely.

## Current implementation

- `runtime/python/iilp.py`: cross-platform Python reference codec for IILP/1.
- `runtime/python/core.py`: bounded service registry and message router.
- `runtime/python/server.py`: TLS-context-required reference server.
- `runtime/python/runtime.py`: bounded runtime registry for trusted in-process Python handlers, with explicit capabilities, JSON limits and invocation deadlines.
- `runtime/python/datacore.py`: SQLite-backed document store with schema validation, indexes, backup and integrity checks.
- `runtime/python/bridge.py`: HTTP JSON gateway to registered Core services and allowlisted HTTPS JSON client.
- `runtime/python/cloud.py`: validated Kubernetes manifest builder with digest-pinned images, resource bounds, secret references and hardened container defaults.
- `runtime/python/security.py`: API key digest store, scopes, explicit RBAC, HMAC request signing/replay protection, in-memory audit sink and bounded opaque-cookie WebSocket session store.
- `runtime/python/keycloak_oidc.py`: optional Keycloak OIDC access-token verifier using PyJWT/JWKS, issuer/audience/authorized-party validation and explicit role-to-scope mapping.
- `runtime/python/websocket_server.py`: TLS WebSocket listener with strict Origin/subprotocol checks, required authentication and per-message authorization callbacks, bounded binary IILP frames and heartbeat/timeouts.
- `runtime/javascript/iilp-browser-client.mjs`: browser HTTPS and binary WebSocket request/response clients.
- `runtime/javascript/`: Node.js IILP codec plus browser-native codec, HTTPS client, WebSocket connection helper and tests.
- `browser/README.md`: browser setup, CORS and security guidance.
- `connectivity/README.md`: live WSS server setup, browser usage and deployment requirements.
- `requirements-websocket.txt`: optional WebSocket server dependency.

Run from the `infilink/` directory:

```sh
python3 runtime/python/iilp.py --self-test
PYTHONPATH=runtime/python:tests python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test runtime/javascript/*.test.mjs
python -m pip install -r requirements-websocket.txt
```

### Keycloak OIDC access-token validation

Install the optional verifier dependency from `infilink/`:

```sh
python -m pip install -r requirements-oidc.txt
```

Configure the exact Keycloak realm issuer, API audience, confidential/public client ID as appropriate for the token's `azp`, and realm JWKS endpoint. The audience must be present in the access token; configure a Keycloak audience mapper if needed. Map only approved Keycloak realm/client roles to INFILINK permissions:

```python
from keycloak_oidc import KeycloakOIDCConfig, KeycloakOIDCVerifier

config = KeycloakOIDCConfig(
    issuer="https://id.example.com/realms/infilink",
    audience="infilink-api",
    client_id="infilink-web",
    jwks_url="https://id.example.com/realms/infilink/protocol/openid-connect/certs",
    role_scope_map={
        "infilink-user": frozenset({"profile.read", "ws.connect"}),
        "infilink-operator": frozenset({"profile.read", "ws.connect", "deploy.read"}),
    },
)
verifier = KeycloakOIDCVerifier(config)
principal = verifier.verify_access_token(access_token)
# Only after this succeeds, issue the INFILINK opaque session:
token, expires_at = sessions.issue(principal, ttl_seconds=1800)
```

The verifier pins RS256, validates the JWT signature through Keycloak's JWKS, and checks issuer, audience, expiry, issued-at, subject and authorized party (`azp`). Unknown Keycloak roles grant no INFILINK permissions. Keep the JWKS endpoint and issuer on trusted HTTPS origins. Do not accept ID tokens as API access tokens, do not log tokens, and do not place tokens in URLs or browser storage.

The browser Authorization Code + PKCE flow is implemented in `runtime/python/keycloak_browser_oidc.py`. Draft integration layers are available in `postgres_oidc_transactions.py`, `postgres_oidc_browser_binding.py`, `postgres_sessions.py`, `session_auth.py`, and `oidc_http_routes.py`. The WSGI gateway can be composed with these durable adapters using `create_authenticated_wsgi_app` from `bridge.py`; it mounts `GET /auth/login`, the configured OIDC callback path, and `POST /auth/logout`, and protects service message routes with explicit session scopes and exact HTTPS Origin checks.

The factory requires a shared PostgreSQL session store, OIDC transaction store, and browser-binding store. Configure the Keycloak issuer, authorization/token endpoints, client ID, callback URI, allowed browser origins, service-to-scope mapping, and fixed success/logout redirect URIs from trusted deployment configuration. Run migrations 001–003 before starting the application. The callback issues only an opaque Secure, HttpOnly, host-only session cookie; logout revokes the local session before redirecting to Keycloak. Do not expose the unauthenticated `create_wsgi_app` factory to untrusted networks.

This integration is still under review: CI, live PostgreSQL multi-worker tests, and an end-to-end browser test against the real Keycloak realm—including logout, browser-back behavior, and revoked-session reuse—must pass before production use. JWT/JWKS unit tests mock the cryptographic provider boundary; they do not replace live identity-provider verification.

### Browser WebSocket session authentication

After authenticating a user with a trusted identity provider or server-side login flow, create a `Principal` and issue an opaque session token:

```python
from security import WebSocketSessionStore

sessions = WebSocketSessionStore()
# principal must come from a trusted server-side identity flow
token, expires_at = sessions.issue(principal, ttl_seconds=1800)

# Set this from the HTTPS login response; do not expose token to JavaScript:
# Set-Cookie: __Host-infilink_session=<token>; Path=/; Secure; HttpOnly; SameSite=Strict

transport = IILPWebSocketServer(
    router, tls_context,
    allowed_origins={"https://app.example.com"},
    authenticate=sessions.authenticate,
    authorize=authorize_request,
)
```

The `__Host-` cookie must be issued over HTTPS with `Path=/`, `Secure`, no `Domain`, and `HttpOnly`; `SameSite=Strict` is the conservative default. The application must also implement login/logout, session rotation, CSRF protections for state-changing HTTP endpoints, and identity-provider validation. Revoke a session with `sessions.revoke(token)` at logout. The reference store is process-local, so sessions do not survive restart and are not shared across workers; production deployments need a durable, shared session backend, key rotation, rate limiting and monitoring. Never accept roles or scopes supplied by the browser.
## Engineering rules

1. No unbounded "infinite loop": background reconciliation must be bounded, observable, cancellable and rate-limited.
2. Validate every frame, schema, identity and authorization decision at trust boundaries.
3. Use TLS 1.3 or QUIC security; never invent cryptography.
4. Make schemas versioned and migrations reversible where possible.
5. Test conformance across operating systems and language implementations.
6. Treat IILP as an experimental protocol until reviewed, published, interoperably implemented and assigned any necessary protocol identifiers.
7. Never treat an invocation timeout as a sandbox; isolate untrusted workloads at the operating-system or container boundary.

## Status

Early draft / experimental. The Runtime currently registers trusted in-process Python handlers only; it does not execute arbitrary source code or provide a universal multi-language VM. The DataCore SQLite adapter is a local reference implementation; remote adapters and replication remain unimplemented. The Bridge gateway requires a TLS-terminating reverse proxy and authentication/authorization controls before network exposure. Cloud currently generates manifests only; it does not deploy workloads or configure ingress, network policies, monitoring or secret rotation. Security primitives are process-local reference components: API keys and replay state are not durable or shared, audit events are not tamper-evident, and no identity provider or production KMS integration is supplied. HMAC provides integrity/authentication, not confidentiality. The browser HTTP client uses the JSON Bridge; live binary IILP request/response is now available through a separate optional WSS server. That server requires host-supplied authentication and per-message authorization callbacks, TLS certificates and a strict Origin allowlist. Streaming, reconnect/resume and multi-node session coordination are not implemented. Do not use this implementation for sensitive or production workloads without a separate security review and production-grade operational controls. IILP is not an Internet standard.
