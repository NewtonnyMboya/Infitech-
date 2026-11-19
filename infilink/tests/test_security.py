import unittest

from security import (APIKeyStore, Authorizer, MemoryAuditSink, RequestSigner, SecurityError,\n                      Principal, WebSocketSessionStore)


class Clock:
    def __init__(self, value=1_700_000_000):
        self.value = value
    def __call__(self):
        return self.value


class SecurityTests(unittest.TestCase):
    def test_api_key_issue_verify_and_scope(self):
        clock = Clock()
        store = APIKeyStore(clock=clock)
        token, principal = store.issue("service-a", {"orders.read", "orders.write"}, 60)
        self.assertEqual(store.verify(token), principal)
        self.assertIn("orders.read", principal.scopes)

    def test_api_key_invalid_expired_and_revoked(self):
        clock = Clock()
        store = APIKeyStore(clock=clock)
        token, principal = store.issue("service-a", {"orders.read"}, 10)
        with self.assertRaises(SecurityError):
            store.verify(token + "x")
        self.assertTrue(store.revoke(principal.key_id))
        with self.assertRaises(SecurityError):
            store.verify(token)
        token2, principal2 = store.issue("service-b", {"orders.read"}, 10)
        clock.value += 10
        with self.assertRaises(SecurityError):
            store.verify(token2)

    def test_api_key_capacity_and_bad_scopes(self):
        store = APIKeyStore(max_keys=1)
        store.issue("one", {"read"})
        with self.assertRaises(SecurityError):
            store.issue("two", {"read"})
        with self.assertRaises(ValueError):
            APIKeyStore().issue("x", {"Bad Scope"})

    def test_rbac_explicit_permissions(self):
        auth = Authorizer({"operator": {"deploy.read", "deploy.write"},
                           "viewer": {"deploy.read"}})
        auth.require({"operator"}, "deploy.write")
        with self.assertRaises(SecurityError):
            auth.require({"viewer"}, "deploy.write")
        with self.assertRaises(SecurityError):
            auth.require({"unknown"}, "deploy.read")

    def test_request_signature_and_replay_protection(self):
        clock = Clock()
        signer = RequestSigner(b"x" * 32, clock=clock)
        body = {"amount": 12, "currency": "KES"}
        headers = signer.sign("POST", "/v1/payments", body, nonce="nonce-abcdefghijkl")
        signer.verify("POST", "/v1/payments", body, headers)
        with self.assertRaises(SecurityError):
            signer.verify("POST", "/v1/payments", body, headers)

    def test_signature_rejects_tampering_and_wrong_path(self):
        signer = RequestSigner(b"y" * 32)
        headers = signer.sign("POST", "/v1/a", {"value": 1})
        with self.assertRaises(SecurityError):
            signer.verify("POST", "/v1/a", {"value": 2}, headers)
        with self.assertRaises(SecurityError):
            signer.verify("POST", "/v1/b", {"value": 1}, headers)

    def test_signature_rejects_stale_timestamp(self):
        clock = Clock()
        signer = RequestSigner(b"z" * 32, clock=clock, max_clock_skew=30)
        headers = signer.sign("GET", "/health", {}, timestamp=clock.value - 31,
                              nonce="nonce-abcdefghijkl")
        with self.assertRaises(SecurityError):
            signer.verify("GET", "/health", {}, headers)

    def test_audit_sink_redacts_by_rejecting_secret_fields(self):
        audit = MemoryAuditSink()
        event = audit.record("login", "service-a", "success", {"source": "gateway"})
        self.assertEqual(event.details, (("source", "gateway"),))
        with self.assertRaises(ValueError):
            audit.record("login", "service-a", "success", {"api_key": "do-not-store"})
        self.assertEqual(len(audit.events()), 1)

    def test_audit_capacity(self):
        audit = MemoryAuditSink(capacity=1)
        audit.record("one", "subject", "ok")
        with self.assertRaises(SecurityError):
            audit.record("two", "subject", "ok")


if __name__ == "__main__":
    unittest.main()
