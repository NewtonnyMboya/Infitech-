"""Framework-neutral WSGI routes for Keycloak browser login and logout.

Requires PostgreSQL-backed OIDC transactions, browser bindings, and sessions.
Mount behind a trusted HTTPS reverse proxy. Owns only explicit auth paths.
"""
from __future__ import annotations

from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlsplit

from keycloak_browser_oidc import KeycloakAuthorizationCodeFlow, OIDCFlowError
from postgres_oidc_transactions import PostgreSQLLoginTransactionStore
from postgres_oidc_browser_binding import (
    PostgreSQLBrowserBindingStore,
    begin_browser_bound_login,
    clear_browser_cookie,
    complete_browser_bound_login,
)
from postgres_sessions import PostgreSQLSessionStore
from session_auth import issue_session_cookie, revoke_session_from_headers, session_clear_cookie


class KeycloakOIDCHTTPRoutes:
    """WSGI middleware for browser OIDC login, callback, and logout."""

    def __init__(
        self, app: Callable, *, flow: KeycloakAuthorizationCodeFlow,
        sessions: PostgreSQLSessionStore,
        transactions: PostgreSQLLoginTransactionStore,
        bindings: PostgreSQLBrowserBindingStore,
        allowed_origins: set[str], success_redirect: str,
        post_logout_redirect_uri: str,
        login_path: str = "/auth/login", logout_path: str = "/auth/logout",
    ) -> None:
        if not callable(app) or not isinstance(flow, KeycloakAuthorizationCodeFlow):
            raise ValueError("WSGI app and Keycloak flow are required")
        if not isinstance(sessions, PostgreSQLSessionStore):
            raise ValueError("PostgreSQLSessionStore is required")
        if not isinstance(transactions, PostgreSQLLoginTransactionStore):
            raise ValueError("PostgreSQLLoginTransactionStore is required")
        if not isinstance(bindings, PostgreSQLBrowserBindingStore):
            raise ValueError("PostgreSQLBrowserBindingStore is required")
        if flow.transactions is not transactions:
            raise ValueError("flow must use the supplied durable transaction store")
        if not allowed_origins:
            raise ValueError("exact HTTPS origins are required")
        for origin in allowed_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.path not in ("", "/")
                    or parsed.query or parsed.fragment):
                raise ValueError("allowed origins must be exact HTTPS origins")
        self._validate_fixed_url(success_redirect, allowed_origins, "success_redirect")
        self._validate_fixed_url(
            post_logout_redirect_uri, allowed_origins, "post_logout_redirect_uri"
        )
        for route in (login_path, logout_path):
            if (not isinstance(route, str) or not route.startswith("/")
                    or route.startswith("//") or "?" in route or "#" in route):
                raise ValueError("invalid authentication route path")
        if login_path == logout_path:
            raise ValueError("login and logout paths must differ")
        self.app, self.flow, self.sessions = app, flow, sessions
        self.transactions, self.bindings = transactions, bindings
        self.allowed_origins = frozenset(allowed_origins)
        self.success_redirect = success_redirect
        self.post_logout_redirect_uri = post_logout_redirect_uri
        self.login_path, self.logout_path = login_path, logout_path
        self.callback_path = urlsplit(flow.redirect_uri).path
        if not self.callback_path or self.callback_path in (login_path, logout_path):
            raise ValueError("OIDC callback path must be distinct from login and logout")
        issuer = urlsplit(flow.issuer)
        self.end_session_endpoint = (
            issuer.scheme + "://" + issuer.netloc + issuer.path.rstrip("/")
            + "/protocol/openid-connect/logout"
        )

    @staticmethod
    def _validate_fixed_url(value: str, allowed_origins: set[str], label: str) -> None:
        parsed = urlsplit(value) if isinstance(value, str) else None
        if (parsed is None or parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.fragment or parsed.query):
            raise ValueError(label + " must be a fixed HTTPS URL without query or fragment")
        origin = parsed.scheme + "://" + parsed.netloc
        if origin not in allowed_origins:
            raise ValueError(label + " origin must be explicitly allowed")

    @staticmethod
    def _response(start_response: Callable, status: str, body: bytes,
                  headers: list[tuple[str, str]] | None = None):
        response_headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
            ("Pragma", "no-cache"), ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
        ]
        response_headers.extend(headers or [])
        start_response(status, response_headers)
        return [body]

    @classmethod
    def _redirect(cls, start_response: Callable, location: str,
                  cookies: list[str] | None = None):
        headers = [("Location", location)]
        headers.extend(("Set-Cookie", value) for value in (cookies or []))
        return cls._response(start_response, "303 See Other", b"", headers)

    def _callback(self, environ: dict[str, Any], start_response: Callable):
        query = environ.get("QUERY_STRING", "")
        if not isinstance(query, str) or len(query) > 8192:
            return self._response(
                start_response, "400 Bad Request", b'{"error":"invalid_callback"}',
                [("Set-Cookie", clear_browser_cookie())],
            )
        params = parse_qs(query, keep_blank_values=True)
        if params.get("error"):
            return self._response(
                start_response, "400 Bad Request",
                b'{"error":"identity_provider_rejected_login"}',
                [("Set-Cookie", clear_browser_cookie())],
            )
        codes, states = params.get("code", []), params.get("state", [])
        if len(codes) != 1 or len(states) != 1 or not codes[0] or not states[0]:
            return self._response(
                start_response, "400 Bad Request", b'{"error":"invalid_callback"}',
                [("Set-Cookie", clear_browser_cookie())],
            )
        try:
            result = complete_browser_bound_login(
                self.flow, self.bindings, code=codes[0], state=states[0],
                cookie_header=environ.get("HTTP_COOKIE", ""),
            )
            cookie, _ = issue_session_cookie(
                self.sessions, result.principal, ttl_seconds=min(result.expires_in, 3600)
            )
        except (OIDCFlowError, ValueError, RuntimeError):
            return self._response(
                start_response, "401 Unauthorized",
                b'{"error":"authentication_failed"}',
                [("Set-Cookie", clear_browser_cookie())],
            )
        except Exception:
            return self._response(
                start_response, "503 Service Unavailable",
                b'{"error":"authentication_unavailable"}',
                [("Set-Cookie", clear_browser_cookie())],
            )
        return self._redirect(
            start_response, self.success_redirect, [cookie, clear_browser_cookie()]
        )

    def _logout(self, environ: dict[str, Any], start_response: Callable):
        origin = environ.get("HTTP_ORIGIN")
        fetch_site = environ.get("HTTP_SEC_FETCH_SITE")
        if origin not in self.allowed_origins or (
            fetch_site and fetch_site not in ("same-origin", "same-site", "none")
        ):
            return self._response(
                start_response, "403 Forbidden", b'{"error":"csrf_check_failed"}'
            )
        # Local revocation happens before redirecting to Keycloak.
        try:
            revoke_session_from_headers(
                self.sessions, {"Cookie": environ.get("HTTP_COOKIE", "")}
            )
        except Exception:
            return self._response(
                start_response, "503 Service Unavailable",
                b'{"error":"logout_unavailable"}'
            )
        location = self.end_session_endpoint + "?" + urlencode({
            "client_id": self.flow.client_id,
            "post_logout_redirect_uri": self.post_logout_redirect_uri,
        })
        return self._redirect(
            start_response, location, [session_clear_cookie(), clear_browser_cookie()]
        )

    def __call__(self, environ: dict[str, Any], start_response: Callable):
        method, path = environ.get("REQUEST_METHOD", ""), environ.get("PATH_INFO", "")
        if path == self.login_path:
            if method != "GET":
                return self._response(
                    start_response, "405 Method Not Allowed",
                    b'{"error":"method_not_allowed"}', [("Allow", "GET")]
                )
            try:
                location, browser_cookie = begin_browser_bound_login(
                    self.flow, self.bindings
                )
            except Exception:
                return self._response(
                    start_response, "503 Service Unavailable",
                    b'{"error":"login_unavailable"}'
                )
            return self._redirect(start_response, location, [browser_cookie])
        if path == self.callback_path:
            if method != "GET":
                return self._response(
                    start_response, "405 Method Not Allowed",
                    b'{"error":"method_not_allowed"}', [("Allow", "GET")]
                )
            return self._callback(environ, start_response)
        if path == self.logout_path:
            if method != "POST":
                return self._response(
                    start_response, "405 Method Not Allowed",
                    b'{"error":"method_not_allowed"}', [("Allow", "POST")]
                )
            return self._logout(environ, start_response)
        return self.app(environ, start_response)
