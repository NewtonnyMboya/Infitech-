"""Opt-in PostgreSQL integration tests for cross-worker session semantics."""
import os
import unittest

from security import Principal
from postgres_sessions import PostgreSQLSessionStore

DSN = os.environ.get("INFILINK_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "set INFILINK_TEST_DATABASE_URL for PostgreSQL integration tests")
class PostgreSQLSessionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest("install psycopg[binary] to run PostgreSQL integration tests") from exc
        cls.connect = staticmethod(lambda: psycopg.connect(DSN))
        with psycopg.connect(DSN) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS infilink_sessions (
                    token_digest BYTEA PRIMARY KEY CHECK (octet_length(token_digest) = 32),
                    key_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    scopes JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    revoked_at TIMESTAMPTZ
                )
            """)

    def setUp(self):
        with self.connect() as conn:
            conn.execute("DELETE FROM infilink_sessions")
        self.worker_a = PostgreSQLSessionStore(self.connect)
        self.worker_b = PostgreSQLSessionStore(self.connect)
        self.principal = Principal("keycloak-subject-123", "alice",
                                   frozenset({"profile.read", "ws.connect"}),
                                   4_000_000_000)

    def test_session_issued_on_worker_a_authenticates_on_worker_b(self):
        token, expires = self.worker_a.issue(self.principal, ttl_seconds=600)
        self.assertGreater(expires, 0)
        headers = {"Cookie": f"{self.worker_a.COOKIE_NAME}={token}"}
        self.assertEqual(self.worker_b.authenticate(headers).subject, "alice")

    def test_revocation_on_worker_a_is_immediately_visible_on_worker_b(self):
        token, _ = self.worker_a.issue(self.principal)
        headers = {"Cookie": f"{self.worker_a.COOKIE_NAME}={token}"}
        self.assertIsNotNone(self.worker_b.authenticate(headers))
        self.assertTrue(self.worker_a.revoke(token))
        self.assertIsNone(self.worker_b.authenticate(headers))
        self.assertFalse(self.worker_b.revoke(token))

    def test_database_stores_only_digest_not_raw_cookie_token(self):
        token, _ = self.worker_a.issue(self.principal)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT token_digest FROM infilink_sessions"
            ).fetchone()
        self.assertEqual(len(row[0]), 32)
        self.assertNotEqual(row[0], token.encode("ascii"))

    def test_expired_principal_is_not_issued(self):
        expired = Principal("keycloak-subject-123", "alice",
                            frozenset({"ws.connect"}), 1)
        with self.assertRaises(Exception):
            self.worker_a.issue(expired, ttl_seconds=30)


if __name__ == "__main__":
    unittest.main()
