import unittest
from unittest.mock import patch

from keycloak_browser_oidc import KeycloakAuthorizationCodeFlow, OIDCLoginResult
from keycloak_oidc import KeycloakOIDCConfig, KeycloakOIDCVerifier
from postgres_oidc_browser_binding import PostgreSQLBrowserBindingStore
from postgres_oidc_transactions import PostgreSQLLoginTransactionStore
from postgres_sessions import PostgreSQLSessionStore
from security import Principal
from oidc_http_routes import KeycloakOIDCHTTPRoutes


class OIDCHTTPRouteTests(unittest.TestCase):
    def setUp(self):
        config = KeycloakOIDCConfig(
            issuer="https://id.example.test/realms/infilink",
            audience="infilink-api",
            client_id="infilink-web",
            jwks_url="https://id.example.test/realms/infilink/protocol/openid-connect/certs",
            role_scope_map={"infilink-user": frozenset({"profile.read"})},
        )
        verifier = KeycloakOIDCVerifier(config)
        self.transactions = PostgreSQLLoginTransactionStore(lambda: None)
        self.flow = KeycloakAuthorizationCodeFlow(
            issuer=config.issuer,
            authorization_endpoint="https://id.example.test/realms/infilink/protocol/openid-connect/auth",
            token_endpoint="https://id.example.test/realms/infilink/protocol/openid-connect/token",
            client_id="infilink-web",
            redirect_uri="https://app.example.test/oidc/callback",
            verifier=verifier,
            transactions=self.transactions,
            post_form=lambda *args: {},
        )
        self.sessions = PostgreSQLSessionStore(lambda: None)
        self.bindings = PostgreSQLBrowserBindingStore(lambda: None)
        self.calls = []

        def app(environ, start_response):
            start_response("200 OK", [("Content-Length", "0")])
            return [b""]

        self.routes = KeycloakOIDCHTTPRoutes(
            app,
            flow=self.flow,
            sessions=self.sessions,
            transactions=self.transactions,
            bindings=self.bindings,
            allowed_origins={"https://app.example.test"},
            success_redirect="https://app.example.test/",
            post_logout_redirect_uri="https://app.example.test/signed-out",
        )

    def invoke(self, method, path, **extra):
        result = {}
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": "",
            "HTTP_COOKIE": "",
        }
        environ.update(extra)

        def start_response(status, headers):
            result["status"] = status
            result["headers"] = headers

        body = b"".join(self.routes(environ, start_response))
        return result, body

    def test_login_starts_pkce_and_sets_browser_cookie(self):
        with patch("oidc_http_routes.begin_browser_bound_login") as begin:
            begin.return_value = (
                "https://id.example.test/authorize?state=opaque",
                "__Host-infilink_oidc_browser=opaque; Secure; HttpOnly; Path=/",
            )
            result, _ = self.invoke("GET", "/auth/login")
        self.assertEqual(result["status"], "303 See Other")
        headers = dict((k, v) for k, v in result["headers"] if k != "Set-Cookie")
        self.assertEqual(headers["Location"], "https://id.example.test/authorize?state=opaque")
        self.assertTrue(any(k == "Set-Cookie" and "oidc_browser" in v
                            for k, v in result["headers"]))

    def test_callback_issues_session_and_clears_browser_cookie(self):
        principal = Principal("key-id", "subject-1", frozenset({"profile.read"}), 2_000_000_000)
        login = OIDCLoginResult(principal, "access-token", 300)
        with patch("oidc_http_routes.complete_browser_bound_login", return_value=login), \
             patch("oidc_http_routes.issue_session_cookie",
                   return_value=("__Host-infilink_session=opaque; Secure; HttpOnly", 2_000_000_000)):
            result, _ = self.invoke(
                "GET", "/oidc/callback", QUERY_STRING="code=code123&state=state123",
                HTTP_COOKIE="__Host-infilink_oidc_browser=browser123",
            )
        self.assertEqual(result["status"], "303 See Other")
        cookies = [v for k, v in result["headers"] if k == "Set-Cookie"]
        self.assertEqual(len(cookies), 2)
        self.assertTrue(any("infilink_session" in v for v in cookies))
        self.assertTrue(any("Max-Age=0" in v for v in cookies))

    def test_logout_requires_exact_origin_and_revokes_before_redirect(self):
        with patch("oidc_http_routes.revoke_session_from_headers", return_value=True) as revoke:
            denied, _ = self.invoke("POST", "/auth/logout", HTTP_ORIGIN="https://evil.example")
            self.assertEqual(denied["status"], "403 Forbidden")
            revoke.assert_not_called()

            result, _ = self.invoke(
                "POST", "/auth/logout",
                HTTP_ORIGIN="https://app.example.test",
                HTTP_SEC_FETCH_SITE="same-origin",
                HTTP_COOKIE="__Host-infilink_session=opaque",
            )
        self.assertEqual(result["status"], "303 See Other")
        revoke.assert_called_once()
        location = dict(result["headers"])["Location"]
        self.assertIn("/protocol/openid-connect/logout?", location)
        self.assertIn("client_id=infilink-web", location)
        self.assertIn("post_logout_redirect_uri=", location)
        self.assertEqual(len([v for k, v in result["headers"] if k == "Set-Cookie"]), 2)

    def test_login_and_logout_enforce_methods(self):
        login, _ = self.invoke("POST", "/auth/login")
        logout, _ = self.invoke("GET", "/auth/logout")
        self.assertEqual(login["status"], "405 Method Not Allowed")
        self.assertEqual(logout["status"], "405 Method Not Allowed")

    def test_fixed_redirect_must_be_https_and_allowed_origin(self):
        with self.assertRaises(ValueError):
            KeycloakOIDCHTTPRoutes(
                lambda *args: [],
                flow=self.flow,
                sessions=self.sessions,
                transactions=self.transactions,
                bindings=self.bindings,
                allowed_origins={"https://app.example.test"},
                success_redirect="https://evil.example/",
                post_logout_redirect_uri="https://app.example.test/signed-out",
            )


if __name__ == "__main__":
    unittest.main()
