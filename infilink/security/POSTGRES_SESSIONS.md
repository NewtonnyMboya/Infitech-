# INFILINK session storage

## PostgreSQL-backed sessions

The optional `runtime/python/postgres_sessions.py` adapter provides shared
browser/WebSocket sessions for multiple INFILINK workers. It implements the
same `issue(principal, ttl_seconds)`, `authenticate(headers)`, and
`revoke(token)` operations as the in-memory `WebSocketSessionStore`.

### Provisioning

1. Provision a PostgreSQL database owned by the INFILINK application. Do not
   reuse or connect to Keycloak's private database.
2. Apply `infilink/migrations/001_create_infilink_sessions.sql` using a
   migration/DDL role.
3. Install the optional driver with
   `pip install -r infilink/requirements-postgres.txt`.
4. Give the runtime database role only the required table permissions:
   `SELECT, INSERT, UPDATE` on `infilink_sessions`. Keep credentials in the
   deployment secret manager and require TLS for remote database connections.
5. Construct the adapter with a psycopg connection factory, for example:

```python
import os
import psycopg
from postgres_sessions import PostgreSQLSessionStore

sessions = PostgreSQLSessionStore(
    lambda: psycopg.connect(os.environ["INFILINK_DATABASE_URL"], sslmode="verify-full")
)
```

Use `session_auth.py` to integrate the store. After validating the Keycloak
OIDC login result, call `issue_session_cookie(sessions, principal)` and add
the returned value as a `Set-Cookie` response header. It persists the session
before returning a cookie and does not expose the raw token to the caller.
Wrap the WSGI bridge with `SessionHTTPMiddleware`, configuring exact HTTPS
origins and an explicit service-to-scope map. For WebSockets, pass
`websocket_session_authenticator(sessions)` and
`websocket_scope_authorizer(service_scopes)` to `IILPWebSocketServer`.
On logout, call `revoke_session_from_headers(sessions, headers)` before
returning `session_clear_cookie()` as the `Set-Cookie` response header.
Never return the token in JSON, URLs, or browser-readable storage. These are
integration helpers; the application still owns its OIDC routes, HTTPS
termination, and response construction.

### Guarantees and boundaries

- Only SHA-256 token digests are persisted; raw cookie tokens are returned once
  to the caller and are not stored.
- PostgreSQL transactions make inserts and revocation atomic.
- Authentication and revocation use the database clock, so workers share
  expiry and revocation state.
- Revocation updates the row; expired/revoked rows are never authenticated.
  Schedule cleanup of expired rows as operational maintenance.
- The integration helpers provide cookie construction, session issue/revoke
  operations, WSGI session/scope enforcement, origin and Fetch Metadata checks,
  and WebSocket authentication/authorization callbacks.
- The helpers do not implement HTTP login/callback/logout routes, actual
  response routing, connection pooling, or Keycloak token refresh. The app
  must invoke them from its OIDC callback and logout handlers.
- Apply migrations before deploying the adapter. The optional PostgreSQL
  integration tests require a disposable test database and
  `INFILINK_TEST_DATABASE_URL`; they are skipped otherwise.

Run Python tests with `infilink/tests/run_tests.sh`. For integration coverage,
install the optional driver, apply the migration to a disposable database, set
`INFILINK_TEST_DATABASE_URL`, and run
`python -m unittest discover -s infilink/tests -p 'test_postgres_sessions.py' -v`.
