"""PostgreSQL-backed shared sessions for INFILINK browser/WebSocket auth.

Requires psycopg 3 and an application-owned PostgreSQL database. The adapter
stores only SHA-256 token digests and relies on PostgreSQL time for expiry and
revocation decisions, so separate workers observe the same session state.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from http.cookies import CookieError, SimpleCookie
from typing import Any, Callable

from security import Principal, SecurityError


class PostgreSQLSessionStore:
    """Durable session store; pass a psycopg connection factory as connect.

    Apply migrations/001_create_infilink_sessions.sql before use. Each method
    opens its own connection, making the instance safe to share across worker
    processes. The database connection must target INFILINK's own database,
    not Keycloak's private database.
    """

    COOKIE_NAME = "__Host-infilink_session"
    _TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")

    def __init__(self, connect: Callable[[], Any]) -> None:
        if not callable(connect):
            raise ValueError("connect must be a PostgreSQL connection factory")
        self._connect = connect

    @staticmethod
    def _digest(token: str) -> bytes:
        return hashlib.sha256(token.encode("ascii")).digest()

    @staticmethod
    def _validate_principal(principal: Principal) -> None:
        if not isinstance(principal, Principal):
            raise ValueError("an authenticated Principal is required")
        if (not isinstance(principal.key_id, str) or not principal.key_id
                or len(principal.key_id) > 128
                or not isinstance(principal.subject, str) or not principal.subject
                or len(principal.subject) > 256
                or not isinstance(principal.expires_at, (int, float))):
            raise ValueError("principal fields are invalid")
        if (not principal.scopes or len(principal.scopes) > 64
                or any(not isinstance(s, str) or not re.fullmatch(
                    r"[a-z][a-z0-9_.:-]{0,63}", s
                ) for s in principal.scopes)):
            raise ValueError("principal scopes are invalid")

    def issue(self, principal: Principal, ttl_seconds: int = 3600) -> tuple[str, float]:
        self._validate_principal(principal)
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 86_400:
            raise ValueError("ttl_seconds must be between 1 second and 1 day")
        token = secrets.token_urlsafe(32)
        digest = self._digest(token)
        scopes = json.dumps(sorted(principal.scopes), separators=(",", ":"))
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO infilink_sessions
                            (token_digest, key_id, subject, scopes, expires_at)
                        VALUES
                            (%s, %s, %s, %s::jsonb,
                             LEAST(clock_timestamp() + (%s * interval '1 second'),
                                   to_timestamp(%s)))
                        RETURNING EXTRACT(EPOCH FROM expires_at)
                        """,
                        (digest, principal.key_id, principal.subject, scopes,
                         ttl_seconds, float(principal.expires_at)),
                    )
                    row = cur.fetchone()
        except Exception:
            # Do not return a token unless its durable row was committed.
            raise
        if not row or row[0] is None:
            raise SecurityError("session could not be persisted")
        expires_at = float(row[0])
        if expires_at <= 0:
            raise SecurityError("principal has expired")
        return token, expires_at

    def authenticate(self, headers: Any) -> Principal | None:
        if headers is None:
            return None
        cookie_header = headers.get("Cookie")
        if not isinstance(cookie_header, str) or not cookie_header or len(cookie_header) > 8192:
            return None
        cookies = SimpleCookie()
        try:
            cookies.load(cookie_header)
        except (CookieError, TypeError, ValueError):
            return None
        morsel = cookies.get(self.COOKIE_NAME)
        if morsel is None or not self._TOKEN.fullmatch(morsel.value):
            return None
        digest = self._digest(morsel.value)
        # PostgreSQL's clock and active-row predicate make revocation visible
        # immediately to every worker and avoid app-server clock skew.
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT key_id, subject, scopes, EXTRACT(EPOCH FROM expires_at)
                    FROM infilink_sessions
                    WHERE token_digest = %s
                      AND revoked_at IS NULL
                      AND expires_at > clock_timestamp()
                    """,
                    (digest,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        key_id, subject, scopes, expires_at = row
        if isinstance(scopes, str):
            scopes = json.loads(scopes)
        if not isinstance(scopes, list):
            raise SecurityError("stored session scopes are invalid")
        return Principal(str(key_id), str(subject), frozenset(scopes), float(expires_at))

    def revoke(self, token: str) -> bool:
        if not isinstance(token, str) or not self._TOKEN.fullmatch(token):
            return False
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE infilink_sessions
                    SET revoked_at = clock_timestamp()
                    WHERE token_digest = %s
                      AND revoked_at IS NULL
                      AND expires_at > clock_timestamp()
                    RETURNING token_digest
                    """,
                    (self._digest(token),),
                )
                return cur.fetchone() is not None
