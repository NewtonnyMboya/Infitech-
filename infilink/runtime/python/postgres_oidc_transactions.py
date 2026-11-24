"""PostgreSQL-backed, atomic one-time OIDC login transactions.

Stores only a SHA-256 digest of the browser state. The nonce and PKCE verifier
are retained server-side until an atomic consume; never log these values.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from typing import Any

from keycloak_browser_oidc import LoginTransaction
from keycloak_browser_oidc import OIDCFlowError


_STATE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


class PostgreSQLLoginTransactionStore:
    """Implements the put()/consume() contract used by KeycloakAuthorizationCodeFlow.

    The supplied connection factory must return a psycopg connection. Atomic
    DELETE ... RETURNING makes a state value single-use across all workers.
    """

    def __init__(self, connect: Any) -> None:
        if not callable(connect):
            raise ValueError("a PostgreSQL connection factory is required")
        self._connect = connect

    def put(self, state: str, transaction: LoginTransaction) -> None:
        if not isinstance(state, str) or not _STATE.fullmatch(state):
            raise ValueError("invalid OIDC state")
        if not isinstance(transaction, LoginTransaction):
            raise ValueError("LoginTransaction is required")
        if (not isinstance(transaction.nonce, str) or not 32 <= len(transaction.nonce) <= 256
                or not isinstance(transaction.code_verifier, str)
                or not 43 <= len(transaction.code_verifier) <= 128
                or isinstance(transaction.expires_at, bool)
                or not isinstance(transaction.expires_at, (int, float))
                or not math.isfinite(transaction.expires_at)
                or float(transaction.expires_at) <= time.time()):
            raise ValueError("invalid OIDC transaction")
        digest = hashlib.sha256(state.encode("ascii")).digest()
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO infilink_oidc_transactions
                    (state_digest, nonce, code_verifier, expires_at)
                VALUES (%s, %s, %s, to_timestamp(%s))
                ON CONFLICT (state_digest) DO NOTHING
                RETURNING state_digest
                """,
                (digest, transaction.nonce, transaction.code_verifier,
                 float(transaction.expires_at)),
            ).fetchone()
        if row is None:
            raise OIDCFlowError("duplicate OIDC state")

    def consume(self, state: str) -> LoginTransaction:
        if not isinstance(state, str) or not _STATE.fullmatch(state):
            raise OIDCFlowError("invalid or expired login state")
        digest = hashlib.sha256(state.encode("ascii")).digest()
        with self._connect() as conn:
            row = conn.execute(
                """
                DELETE FROM infilink_oidc_transactions
                WHERE state_digest = %s AND expires_at > clock_timestamp()
                RETURNING nonce, code_verifier,
                          EXTRACT(EPOCH FROM expires_at)
                """,
                (digest,),
            ).fetchone()
        if row is None:
            raise OIDCFlowError("invalid or expired login state")
        nonce, verifier, expires_at = row
        return LoginTransaction(nonce, verifier, float(expires_at))
