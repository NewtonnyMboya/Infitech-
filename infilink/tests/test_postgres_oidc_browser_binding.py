"""Opt-in PostgreSQL integration tests for browser-bound OIDC callbacks."""
import os
import secrets
import time
import unittest

DSN = os.environ.get("INFILINK_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "set INFILINK_TEST_DATABASE_URL for PostgreSQL integration tests")
class PostgreSQLBrowserBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import psycopg
        except ImportError as exc:
            raise unittest.SkipTest("install psycopg[binary] for PostgreSQL integration tests") from exc
        cls.connect = staticmethod(lambda: psycopg.connect(DSN))
        with psycopg.connect(DSN) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS infilink_oidc_browser_bindings (
                    state_digest BYTEA PRIMARY KEY CHECK (octet_length(state_digest) = 32),
                    browser_digest BYTEA NOT NULL CHECK (octet_length(browser_digest) = 32),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    CHECK (expires_at > created_at)
                )
            """)

    def setUp(self):
        from postgres_oidc_browser_binding import PostgreSQLBrowserBindingStore
        with self.connect() as conn:
            conn.execute("DELETE FROM infilink_oidc_browser_bindings")
        self.worker_a = PostgreSQLBrowserBindingStore(self.connect)
        self.worker_b = PostgreSQLBrowserBindingStore(self.connect)

    def test_correct_browser_can_consume_state_on_another_worker(self):
        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.worker_a.put(state, browser, time.time() + 300)
        self.worker_b.consume(state, browser)

    def test_wrong_browser_cannot_consume_legitimate_state(self):
        from keycloak_browser_oidc import OIDCFlowError
        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.worker_a.put(state, browser, time.time() + 300)
        with self.assertRaises(OIDCFlowError):
            self.worker_b.consume(state, secrets.token_urlsafe(32))
        self.worker_b.consume(state, browser)

    def test_binding_is_single_use_and_expiry_is_enforced(self):
        from keycloak_browser_oidc import OIDCFlowError
        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.worker_a.put(state, browser, time.time() + 300)
        self.worker_b.consume(state, browser)
        with self.assertRaises(OIDCFlowError):
            self.worker_a.consume(state, browser)
        expired_state, expired_browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.worker_a.put(expired_state, expired_browser, time.time() + 1)
        time.sleep(1.1)
        with self.assertRaises(OIDCFlowError):
            self.worker_b.consume(expired_state, expired_browser)


if __name__ == "__main__":
    unittest.main()
