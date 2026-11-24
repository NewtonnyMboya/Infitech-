import base64
import hashlib
import sys
import types
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from keycloak_browser_oidc import (
    KeycloakAuthorizationCodeFlow, LoginTransactionStore, OIDCFlowError,
)
from keycloak_oidc import KeycloakOIDCConfig, KeycloakOIDCVerifier
from security import Principal, SecurityError


class FakeJWKS:
    def __init__(self, *args, **kwargs): pass
    def get_signing_key_from_jwt(self, token):
        return types.SimpleNamespace(key="verified-test-key")


class BrowserOIDCTests(unittest.TestCase):
    def setUp(self):
        self.config = KeycloakOIDCConfig(
            issuer="https://id.example.test/realms/infilink",
            audience="infilink-api", client_id="infilink-web",
            jwks_url="https://id.example.test/realms/infilink/protocol/openid-connect/certs",
            role_scope_map={"infilink-user": frozenset({"profile.read", "ws.connect"})},
        )
        self.claims = {
            "sub": "user-123", "exp": 2_000_000_000, "iat": 1_900_000_000,
            "iss": self.config.issuer, "aud": "infilink-web",
            "azp": "infilink-web", "nonce": None,
            "realm_access": {"roles": ["infilink-user"]},
        }
        fake_jwt = types.SimpleNamespace(
            PyJWKClient=FakeJWKS,
            decode=lambda *args, **kwargs: dict(self.claims),
        )
        self.jwt_patch = patch.dict(sys.modules, {"jwt": fake_jwt})
        self.jwt_patch.start()
        self.addCleanup(self.jwt_patch.stop)
        self.verifier = KeycloakOIDCVerifier(self.config)
        self.exchange_calls = []
        def exchange(url, form, timeout):
            self.exchange_calls.append((url, form, timeout))
            return {"access_token": "access-token", "id_token": "signed.id.token",
                    "expires_in": 300}
        self.flow = KeycloakAuthorizationCodeFlow(
            issuer=self.config.issuer,
            authorization_endpoint="https://id.example.test/realms/infilink/protocol/openid-connect/auth",
            token_endpoint="https://id.example.test/realms/infilink/protocol/openid-connect/token",
            client_id="infilink-web", redirect_uri="https://app.example.test/oidc/callback",
            verifier=self.verifier, post_form=exchange,
        )

    def test_begin_login_uses_s256_and_state_nonce(self):
        url = self.flow.begin_login()
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["scope"], ["openid profile"])
        self.assertEqual(len(params["state"][0]), 43)
        self.assertEqual(len(params["nonce"][0]), 43)
        self.assertEqual(len(params["code_challenge"][0]), 43)

    def test_callback_exchanges_code_and_verifies_nonce(self):
        url = self.flow.begin_login()
        params = parse_qs(urlsplit(url).query)
        state, nonce = params["state"][0], params["nonce"][0]
        self.claims["nonce"] = nonce
        result = self.flow.complete_login(code="auth-code", state=state)
        self.assertIsInstance(result.principal, Principal)
        self.assertEqual(result.principal.subject, "user-123")
        self.assertEqual(result.access_token, "access-token")
        sent = self.exchange_calls[0][1]
        self.assertEqual(sent["code"], "auth-code")
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(sent["code_verifier"].encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self.assertEqual(params["code_challenge"][0], expected)
        self.assertNotIn("client_secret", sent)

    def test_callback_state_is_one_time_and_nonce_is_enforced(self):
        params = parse_qs(urlsplit(self.flow.begin_login()).query)
        self.claims["nonce"] = "wrong-nonce"
        with self.assertRaises(SecurityError):
            self.flow.complete_login(code="auth-code", state=params["state"][0])
        with self.assertRaises(OIDCFlowError):
            self.flow.complete_login(code="auth-code", state=params["state"][0])

    def test_expired_and_unknown_state_rejected(self):
        store = LoginTransactionStore(clock=lambda: 100)
        from keycloak_browser_oidc import LoginTransaction
        store.put("s" * 43, LoginTransaction("n" * 43, "v" * 64, 99))
        with self.assertRaises(OIDCFlowError):
            store.consume("s" * 43)
        with self.assertRaises(OIDCFlowError):
            store.consume("x" * 43)

    def test_configuration_requires_https_and_matching_verifier(self):
        with self.assertRaises(ValueError):
            KeycloakAuthorizationCodeFlow(
                issuer=self.config.issuer, authorization_endpoint="http://id.test/auth",
                token_endpoint="https://id.example.test/token", client_id="infilink-web",
                redirect_uri="https://app.example.test/callback", verifier=self.verifier,
            )
        with self.assertRaises(ValueError):
            KeycloakAuthorizationCodeFlow(
                issuer="https://other.example.test", authorization_endpoint="https://id.example.test/auth",
                token_endpoint="https://id.example.test/token", client_id="infilink-web",
                redirect_uri="https://app.example.test/callback", verifier=self.verifier,
            )


if __name__ == "__main__":
    unittest.main()
