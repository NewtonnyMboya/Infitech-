import sys
import types
import unittest
from unittest.mock import patch

from security import Principal, SecurityError
from keycloak_oidc import KeycloakOIDCConfig, KeycloakOIDCVerifier


class FakeJWKS:
    def __init__(self, *args, **kwargs):
        pass
    def get_signing_key_from_jwt(self, token):
        return types.SimpleNamespace(key="verified-test-key")


class KeycloakOIDCTests(unittest.TestCase):
    def config(self, **kwargs):
        values = dict(
            issuer="https://id.example.test/realms/infilink",
            audience="infilink-api",
            client_id="infilink-web",
            jwks_url="https://id.example.test/realms/infilink/protocol/openid-connect/certs",
            role_scope_map={"infilink-user": frozenset({"profile.read", "ws.connect"})},
        )
        values.update(kwargs)
        return KeycloakOIDCConfig(**values)

    def test_config_rejects_non_https_endpoints_and_algorithms(self):
        with self.assertRaises(ValueError):
            self.config(issuer="http://id.example.test/realms/infilink")
        with self.assertRaises(ValueError):
            self.config(algorithms=("HS256",))

    def test_maps_only_explicitly_configured_roles(self):
        config = self.config()
        claims = {
            "realm_access": {"roles": ["infilink-user", "unmapped-admin"]},
            "resource_access": {"infilink-web": {"roles": ["infilink-user"]}},
        }
        verifier = object.__new__(KeycloakOIDCVerifier)
        verifier.config = config
        self.assertEqual(verifier._map_scopes(claims),
                         {"profile.read", "ws.connect"})

    def test_valid_token_maps_to_principal(self):
        claims = {
            "sub": "user-123", "exp": 2_000_000_000,
            "azp": "infilink-web",
            "realm_access": {"roles": ["infilink-user"]},
        }
        fake_jwt = types.SimpleNamespace(
            PyJWKClient=FakeJWKS,
            decode=lambda *args, **kwargs: claims,
        )
        with patch.dict(sys.modules, {"jwt": fake_jwt}):
            principal = KeycloakOIDCVerifier(self.config()).verify_access_token("signed.jwt.token")
        self.assertIsInstance(principal, Principal)
        self.assertEqual(principal.subject, "user-123")
        self.assertEqual(principal.scopes, frozenset({"profile.read", "ws.connect"}))

    def test_rejects_wrong_authorized_party_and_unmapped_user(self):
        claims = {"sub": "user-123", "exp": 2_000_000_000,
                  "azp": "other-client",
                  "realm_access": {"roles": ["infilink-user"]}}
        fake_jwt = types.SimpleNamespace(PyJWKClient=FakeJWKS,
                                         decode=lambda *args, **kwargs: claims)
        with patch.dict(sys.modules, {"jwt": fake_jwt}):
            verifier = KeycloakOIDCVerifier(self.config())
            with self.assertRaises(SecurityError):
                verifier.verify_access_token("signed.jwt.token")
            claims["azp"] = "infilink-web"
            claims["realm_access"]["roles"] = ["unknown"]
            with self.assertRaises(SecurityError):
                verifier.verify_access_token("signed.jwt.token")


if __name__ == "__main__":
    unittest.main()
