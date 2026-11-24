"""Browser-bound OIDC state helpers backed by PostgreSQL.

A short-lived HttpOnly cookie binds the authorization callback to the browser
that initiated login. Both state and browser binding are stored only as
SHA-256 digests. A wrong browser cannot consume the legitimate transaction.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from http.cookies import CookieError, SimpleCookie
from typing import Any
from urllib.parse import parse_qs, urlsplit

from keycloak_browser_oidc import KeycloakAuthorizationCodeFlow, OIDCFlowError


BROWSER_COOKIE = "__Host-infilink_oidc_browser"
_TOKEN_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_MAX_TOKEN_LENGTH = 256


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("ascii")).digest()


class PostgreSQLBrowserBindingStore:
    """Atomic one-time state-to-browser binding store."""

    def __init__(self, connect: Any) -> None:
        if not callable(connect):
            raise ValueError("a PostgreSQL connection factory is required")
        self._connect = connect

    def put(self, state: str, browser_binding: str, expires_at: float) -> None:
        if not self._valid(state) or not self._valid(browser_binding):
            raise ValueError("invalid OIDC state or browser binding")
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
            raise ValueError("invalid OIDC transaction expiry")
        if expires_at <= time.time():
            raise ValueError("OIDC transaction is already expired")
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO infilink_oidc_browser_bindings
                    (state_digest, browser_digest, expires_at)
                VALUES (%s, %s, to_timestamp(%s))
                ON CONFLICT (state_digest) DO NOTHING
                RETURNING state_digest
                """,
                (_digest(state), _digest(browser_binding), float(expires_at)),
            ).fetchone()
        if row is None:
            raise OIDCFlowError("duplicate OIDC browser transaction")

    def consume(self, state: str, browser_binding: str) -> None:
        if not self._valid(state) or not self._valid(browser_binding):
            raise OIDCFlowError("invalid or expired login transaction")
        with self._connect() as conn:
            row = conn.execute(
                """
                DELETE FROM infilink_oidc_browser_bindings
                WHERE state_digest = %s
                  AND browser_digest = %s
                  AND expires_at > clock_timestamp()
                RETURNING state_digest
                """,
                (_digest(state), _digest(browser_binding)),
            ).fetchone()
        if row is None:
            raise OIDCFlowError("invalid or expired login transaction")

    @staticmethod
    def _valid(value: str) -> bool:
        return (isinstance(value, str) and 32 <= len(value) <= _MAX_TOKEN_LENGTH
                and all(char in _TOKEN_CHARS for char in value))


def _browser_cookie(value: str, max_age: int) -> str:
    cookie = SimpleCookie()
    cookie[BROWSER_COOKIE] = value
    morsel = cookie[BROWSER_COOKIE]
    morsel["path"] = "/"
    morsel["secure"] = True
    morsel["httponly"] = True
    # Lax is required for the top-level GET redirect back from Keycloak.
    morsel["samesite"] = "Lax"
    morsel["max-age"] = str(max_age)
    return morsel.OutputString()


def clear_browser_cookie() -> str:
    cookie = SimpleCookie()
    cookie[BROWSER_COOKIE] = ""
    morsel = cookie[BROWSER_COOKIE]
    morsel["path"] = "/"
    morsel["secure"] = True
    morsel["httponly"] = True
    morsel["samesite"] = "Lax"
    morsel["max-age"] = "0"
    morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    return morsel.OutputString()


def begin_browser_bound_login(
    flow: KeycloakAuthorizationCodeFlow, bindings: PostgreSQLBrowserBindingStore
) -> tuple[str, str]:
    """Return (authorization URL, Set-Cookie value) for a browser-bound login."""
    if not isinstance(flow, KeycloakAuthorizationCodeFlow):
        raise ValueError("KeycloakAuthorizationCodeFlow is required")
    if not isinstance(bindings, PostgreSQLBrowserBindingStore):
        raise ValueError("PostgreSQLBrowserBindingStore is required")
    browser_binding = secrets.token_urlsafe(32)
    authorization_url = flow.begin_login()
    states = parse_qs(urlsplit(authorization_url).query).get("state", [])
    if len(states) != 1:
        raise OIDCFlowError("authorization URL did not contain exactly one state")
    bindings.put(states[0], browser_binding, time.time() + flow.transaction_ttl)
    return authorization_url, _browser_cookie(browser_binding, flow.transaction_ttl)


def complete_browser_bound_login(
    flow: KeycloakAuthorizationCodeFlow,
    bindings: PostgreSQLBrowserBindingStore,
    *,
    code: str,
    state: str,
    cookie_header: str,
):
    """Verify the initiating browser before consuming the OIDC code transaction."""
    if not isinstance(cookie_header, str) or not cookie_header or len(cookie_header) > 8192:
        raise OIDCFlowError("browser login binding is missing")
    cookies = SimpleCookie()
    try:
        cookies.load(cookie_header)
    except (CookieError, TypeError, ValueError) as exc:
        raise OIDCFlowError("browser login binding is invalid") from exc
    morsel = cookies.get(BROWSER_COOKIE)
    if morsel is None:
        raise OIDCFlowError("browser login binding is missing")
    binding = morsel.value
    if not PostgreSQLBrowserBindingStore._valid(binding):
        raise OIDCFlowError("browser login binding is invalid")
    bindings.consume(state, binding)
    return flow.complete_login(code=code, state=state)
