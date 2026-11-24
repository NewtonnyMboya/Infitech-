"""Regression tests for durable HTTP/WebSocket session integration."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime" / "python"))

from postgres_sessions import PostgreSQLSessionStore
from security import Principal
from session_auth import (
    SessionHTTPMiddleware,
    session_clear_cookie,
    session_set_cookie,
    websocket_scope_authorizer,
    websocket_session_authenticator,
)


class SessionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal("keycloak", "subject-123", frozenset({"profile.read"}), 4_000_000_000)
        self.store = PostgreSQLSessionStore(lambda: None)
        self.store.authenticate = lambda headers: (
            self.principal if headers.get("Cookie") == "valid-cookie" else None
        )

    def app(self, environ, start_response):
        self.seen_principal = environ.get("infilink.principal")
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"ok":true}']

    def request(self, middleware, **overrides):
        environ = {
            "REQUEST_METHOD": "POST",
            "PATH_INFO": "/v1/services/profile/messages",
            "HTTP_ORIGIN": "https://app.example.test",
            "HTTP_COOKIE": "valid-cookie",
            "CONTENT_LENGTH": "2",
        }
        environ.update(overrides)
        result = {}
        body = middleware(environ, lambda status, headers: result.update(
            status=status, headers=headers
        ))
        return result, body

    def test_cookie_is_secure_host_only_and_http_only(self):
        header = session_set_cookie("A" * 43, 4_000_000_000, max_age=3600)
        self.assertIn("Secure", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Strict", header)
        self.assertIn("Path=/", header)
        self.assertNotIn("Domain=", header)
        self.assertIn("Max-Age=3600", header)

    def test_logout_cookie_clears_same_cookie_scope(self):
        header = session_clear_cookie()
        self.assertIn("Max-Age=0", header)
        self.assertIn("HttpOnly", header)
        self.assertIn("Secure", header)
        self.assertIn("Path=/", header)

    def test_authenticated_request_reaches_app_with_principal(self):
        middleware = SessionHTTPMiddleware(
            self.app, self.store,
            allowed_origins={"https://app.example.test"},
            service_scopes={"profile": "profile.read"},
        )
        result, body = self.request(middleware)
        self.assertEqual(result["status"], "200 OK")
        self.assertEqual(body, [b'{"ok":true}'])
        self.assertEqual(self.seen_principal, self.principal)

    def test_missing_session_is_rejected(self):
        self.store.authenticate = lambda headers: None
        middleware = SessionHTTPMiddleware(
            self.app, self.store,
            allowed_origins={"https://app.example.test"},
            service_scopes={"profile": "profile.read"},
        )
        result, _ = self.request(middleware)
        self.assertEqual(result["status"], "401 Unauthorized")

    def test_insufficient_scope_is_rejected(self):
        self.principal = Principal("keycloak", "subject-123", frozenset({"ws.connect"}), 4_000_000_000)
        middleware = SessionHTTPMiddleware(
            self.app, self.store,
            allowed_origins={"https://app.example.test"},
            service_scopes={"profile": "profile.read"},
        )
        result, _ = self.request(middleware)
        self.assertEqual(result["status"], "403 Forbidden")

    def test_untrusted_origin_is_rejected(self):
        middleware = SessionHTTPMiddleware(
            self.app, self.store,
            allowed_origins={"https://app.example.test"},
            service_scopes={"profile": "profile.read"},
        )
        result, _ = self.request(middleware, HTTP_ORIGIN="https://evil.example")
        self.assertEqual(result["status"], "403 Forbidden")

    def test_cross_site_fetch_metadata_is_rejected(self):
        middleware = SessionHTTPMiddleware(
            self.app, self.store,
            allowed_origins={"https://app.example.test"},
            service_scopes={"profile": "profile.read"},
        )
        result, _ = self.request(middleware, HTTP_SEC_FETCH_SITE="cross-site")
        self.assertEqual(result["status"], "403 Forbidden")

    def test_websocket_callbacks_use_shared_store_and_explicit_scope(self):
        authenticate = websocket_session_authenticator(self.store)
        self.assertEqual(authenticate({"Cookie": "valid-cookie"}), self.principal)
        authorize = websocket_scope_authorizer({"profile": "profile.read"})
        self.assertTrue(authorize(self.principal, "profile", {}))
        self.assertFalse(authorize(self.principal, "admin", {}))


if __name__ == "__main__":
    unittest.main()
