"""Opt-in PostgreSQL tests for cross-worker, single-use OIDC state."""
import os
import secrets
import time
import unittest

DSN = os.environ.get("INFILINK_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "set INFILINK_TEST_DATABASE_URL for PostgreSQL integration tests")
class PostgreSQLOIDCTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest("install psycopg[binary] for PostgreSQL integration tests") from exc
        cls.connect = staticmethod(lambda: psycopg.connect(DSN))
        with psycopg.connect(DSN) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS infilink_oidc_transactions (
                    state_digest BYTEA PRIMARY KEY CHECK (octet_length(state_digest) = 32),
                    nonce TEXT NOT NULL,
                    code_verifier TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    CHECK (expires_at > created_at)
                )
            """)

    def setUp(self):
        from postgres_oidc_transactions import PostgreSQLLoginTransactionStore
        with self.connect() as conn:
            conn.execute("DELETE FROM infilink_oidc_transactions")
        self.worker_a = PostgreSQLLoginTransactionStore(self.connect)
        self.worker_b = PostgreSQLLoginTransactionStore(self.connect)

    def test_state_created_on_one_worker_is_consumed_on_another(self):
        from keycloak_browser_oidc import LoginTransaction
        state = secrets.token_urlsafe(32)
        expected = LoginTransaction(secrets.token_urlsafe(32),
                                    secrets.token_urlsafe(64), time.time() + 300)
        self.worker_a.put(state, expected)
        actual = self.worker_b.consume(state)
        self.assertEqual(actual.nonce, expected.nonce)
        self.assertEqual(actual.code_verifier, expected.code_verifier)
        # PostgreSQL TIMESTAMPTZ stores microsecond precision; compare expiry
        # with a tolerance rather than requiring Python float bit equality.
        self.assertAlmostEqual(actual.expires_at, expected.expires_at, places=5)

    def test_state_can_only_be_consumed_once_across_workers(self):
        from keycloak_browser_oidc import LoginTransaction, OIDCFlowError
        state = secrets.token_urlsafe(32)
        self.worker_a.put(state, LoginTransaction(secrets.token_urlsafe(32),
                                                  secrets.token_urlsafe(64),
                                                  time.time() + 300))
        self.worker_b.consume(state)
        with self.assertRaises(OIDCFlowError):
            self.worker_a.consume(state)

    def test_expired_state_is_rejected(self):
        from keycloak_browser_oidc import LoginTransaction, OIDCFlowError
        state = secrets.token_urlsafe(32)
        with self.assertRaises(ValueError):
            self.worker_a.put(state, LoginTransaction(secrets.token_urlsafe(32),
                                                      secrets.token_urlsafe(64),
                                                      time.time() - 1))


if __name__ == "__main__":
    unittest.main()
