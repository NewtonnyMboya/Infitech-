"""HTTP and WebSocket integration helpers for durable INFILINK sessions.

The caller must complete OIDC validation before issuing a session. This module
never accepts identity or scope claims supplied by the browser.
"""
from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any, Callable
from email.utils import formatdate
from urllib.parse import urlsplit

from security import Principal, SecurityError

from postgres_sessions import PostgreSQLSessionStore


COOKIE_NAME = PostgreSQLSessionStore.COOKIE_NAME


def session_set_cookie(token: str, expires_at: float, *, max_age: int) -> str:
    """Build the host-only session cookie; only call over HTTPS."""
    if not isinstance(token, str) or not PostgreSQLSessionStore._TOKEN.fullmatch(token):
        raise ValueError("invalid session token")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or not 1 <= max_age <= 86_400:
        raise ValueError("max_age must be between 1 and 86400")
    cookie = SimpleCookie()
    cookie[COOKIE_NAME] = token
    morsel = cookie[COOKIE_NAME]
    morsel["path"] = "/"
    morsel["secure"] = True
    morsel["httponly"] = True
    morsel["samesite"] = "Strict"
    morsel["max-age"] = str(max_age)
    morsel["expires"] = formatdate(expires_at, usegmt=True)
    return morsel.OutputString()


def session_clear_cookie() -> str:
    """Expire the session cookie using the same host-only attributes."""
    cookie = SimpleCookie()
    cookie[COOKIE_NAME] = ""
    morsel = cookie[COOKIE_NAME]
    morsel["path"] = "/"
    morsel["secure"] = True
    morsel["httponly"] = True
    morsel["samesite"] = "Strict"
    morsel["max-age"] = "0"
    morsel["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    return morsel.OutputString()


class SessionHTTPMiddleware:
    """Require a live shared session and service scope for bridge requests.

    Only GET /health is public. Mutating requests require an exact allowed
    Origin and reject cross-site Fetch Metadata. Scope mapping is explicit.
    """
    def __init__(
        self,
        app: Callable,
        sessions: PostgreSQLSessionStore,
        *,
        allowed_origins: set[str],
        service_scopes: dict[str, str],
    ) -> None:
        if not callable(app) or not isinstance(sessions, PostgreSQLSessionStore):
            raise ValueError("app and PostgreSQLSessionStore are required")
        if not allowed_origins:
            raise ValueError("exact HTTPS origins are required")
        for origin in allowed_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme != "https" or not parsed.hostname
                    or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                    or parsed.username or parsed.password):
                raise ValueError("exact HTTPS origins are required")
        if not service_scopes or any(
            not isinstance(k, str) or not k or not isinstance(v, str) or not v
            for k, v in service_scopes.items()
        ):
            raise ValueError("explicit service scope mapping is required")
        self.app = app
        self.sessions = sessions
        self.allowed_origins = frozenset(allowed_origins)
        self.service_scopes = dict(service_scopes)

    @staticmethod
    def _respond(start_response: Callable, status: str, body: bytes):
        start_response(status, [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ])
        return [body]

    def __call__(self, environ: dict[str, Any], start_response: Callable):
        method = environ.get("REQUEST_METHOD", "")
        path = environ.get("PATH_INFO", "")
        if method == "GET" and path == "/health":
            return self.app(environ, start_response)
        prefix = "/v1/services/"
        if not path.startswith(prefix):
            return self.app(environ, start_response)
        service = path[len(prefix):].split("/", 1)[0]
        required_scope = self.service_scopes.get(service)
        if required_scope is None or not path.endswith("/messages"):
            return self._respond(start_response, "403 Forbidden", b'{"error":"forbidden"}')
        origin = environ.get("HTTP_ORIGIN")
        if origin not in self.allowed_origins:
            return self._respond(start_response, "403 Forbidden", b'{"error":"origin_forbidden"}')
        fetch_site = environ.get("HTTP_SEC_FETCH_SITE")
        if fetch_site and fetch_site not in ("same-origin", "same-site", "none"):
            return self._respond(start_response, "403 Forbidden", b'{"error":"cross_site_request"}')
        headers = {"Cookie": environ.get("HTTP_COOKIE", "")}
        try:
            principal = self.sessions.authenticate(headers)
        except SecurityError:
            principal = None
        if principal is None:
            return self._respond(start_response, "401 Unauthorized", b'{"error":"authentication_required"}')
        if required_scope not in principal.scopes:
            return self._respond(start_response, "403 Forbidden", b'{"error":"insufficient_scope"}')
        environ["infilink.principal"] = principal
        return self.app(environ, start_response)


def websocket_session_authenticator(sessions: PostgreSQLSessionStore):
    """Return the WebSocket handshake authenticator backed by shared sessions."""
    if not isinstance(sessions, PostgreSQLSessionStore):
        raise ValueError("PostgreSQLSessionStore is required")

    def authenticate(headers: Any) -> Principal | None:
        return sessions.authenticate(headers)

    return authenticate


def websocket_scope_authorizer(service_scopes: dict[str, str]):
    """Return an explicit WebSocket service-to-scope authorization callback."""
    if not isinstance(service_scopes, dict) or not service_scopes:
        raise ValueError("explicit service scope mapping is required")
    mapping = dict(service_scopes)

    def authorize(principal: Principal, target: str, message: dict[str, Any]) -> bool:
        if not isinstance(principal, Principal):
            return False
        required = mapping.get(target)
        return required is not None and required in principal.scopes

    return authorize
