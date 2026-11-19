"""INFILINK Security primitives (experimental, standard-library only).

This module provides bounded reference controls, not a complete identity platform.
Use TLS 1.3/QUIC in transit and a durable secret manager for production.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable

_ID = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
_SCOPE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
MAX_BODY_BYTES = 1_048_576


class SecurityError(RuntimeError):
    """Authentication, authorization, or signed-request failure."""


def _json_bytes(value: dict[str, Any]) -> bytes:
    if not isinstance(value, dict):
        raise ValueError("body must be a JSON object")
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("body must contain interoperable JSON values") from exc
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("body exceeds the 1 MiB limit")
    return raw


@dataclass(frozen=True)
class Principal:
    key_id: str
    subject: str
    scopes: frozenset[str]
    expires_at: float


@dataclass
class _KeyRecord:
    subject: str
    digest: bytes
    scopes: frozenset[str]
    expires_at: float
    revoked: bool = False


class APIKeyStore:
    """Bounded in-memory API key registry; only SHA-256 digests are retained."""
    def __init__(self, max_keys: int = 10_000,
                 clock: Callable[[], float] = time.time) -> None:
        if not 1 <= max_keys <= 100_000:
            raise ValueError("max_keys must be between 1 and 100000")
        self._max_keys, self._clock = max_keys, clock
        self._records: dict[str, _KeyRecord] = {}
        self._lock = threading.RLock()

    def issue(self, subject: str, scopes: set[str] | frozenset[str],
              ttl_seconds: int = 3600) -> tuple[str, Principal]:
        if not isinstance(subject, str) or not subject or len(subject) > 128:
            raise ValueError("subject must contain 1..128 characters")
        scopes = frozenset(scopes)
        if not scopes or len(scopes) > 64 or any(
            not isinstance(s, str) or not _SCOPE.fullmatch(s) for s in scopes
        ):
            raise ValueError("1..64 valid scopes are required")
        if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 31_536_000:
            raise ValueError("ttl_seconds must be between 1 second and 1 year")
        key_id = secrets.token_urlsafe(9)
        secret = secrets.token_urlsafe(32)
        token = key_id + "." + secret
        expires = self._clock() + ttl_seconds
        record = _KeyRecord(subject, hashlib.sha256(secret.encode("ascii")).digest(),
                            scopes, expires)
        with self._lock:
            if len(self._records) >= self._max_keys:
                raise SecurityError("API key store capacity reached")
            self._records[key_id] = record
        return token, Principal(key_id, subject, scopes, expires)

    def verify(self, token: str) -> Principal:
        if not isinstance(token, str) or len(token) > 256 or token.count(".") != 1:
            raise SecurityError("invalid API key")
        key_id, secret = token.split(".", 1)
        if not _ID.fullmatch(key_id) or not secret:
            raise SecurityError("invalid API key")
        with self._lock:
            record = self._records.get(key_id)
            supplied = hashlib.sha256(secret.encode("utf-8")).digest()
            if (record is None or record.revoked or
                not hmac.compare_digest(record.digest, supplied) or
                self._clock() >= record.expires_at):
                raise SecurityError("invalid API key")
            return Principal(key_id, record.subject, record.scopes, record.expires_at)

    def revoke(self, key_id: str) -> bool:
        with self._lock:
            record = self._records.get(key_id)
            if record is None or record.revoked:
                return False
            record.revoked = True
            return True


class Authorizer:
    """Explicit role-to-permission mapping; no implicit role inheritance."""
    def __init__(self, role_permissions: dict[str, set[str] | frozenset[str]]) -> None:
        if not isinstance(role_permissions, dict) or len(role_permissions) > 128:
            raise ValueError("role_permissions must be a bounded object")
        self._permissions: dict[str, frozenset[str]] = {}
        for role, permissions in role_permissions.items():
            if not isinstance(role, str) or not _SCOPE.fullmatch(role):
                raise ValueError("invalid role")
            perms = frozenset(permissions)
            if any(not isinstance(p, str) or not _SCOPE.fullmatch(p) for p in perms):
                raise ValueError("invalid permission")
            self._permissions[role] = perms

    def require(self, roles: set[str] | frozenset[str], permission: str) -> None:
        if not isinstance(permission, str) or not _SCOPE.fullmatch(permission):
            raise ValueError("invalid permission")
        allowed = any(permission in self._permissions.get(role, frozenset())
                      for role in roles)
        if not allowed:
            raise SecurityError("permission denied")


class RequestSigner:
    """HMAC-SHA256 request authentication with timestamp and bounded replay cache."""
    def __init__(self, secret: bytes, *, max_clock_skew: int = 300,
                 max_nonces: int = 100_000,
                 clock: Callable[[], float] = time.time) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("secret must contain at least 32 bytes")
        if not 1 <= max_clock_skew <= 3600:
            raise ValueError("max_clock_skew must be 1..3600 seconds")
        if not 1 <= max_nonces <= 1_000_000:
            raise ValueError("max_nonces must be 1..1000000")
        self._secret, self._skew, self._max_nonces = secret, max_clock_skew, max_nonces
        self._clock = clock
        self._seen: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _message(method: str, path: str, timestamp: int, nonce: str,
                 body: dict[str, Any]) -> bytes:
        if (not isinstance(method, str) or not re.fullmatch(r"[A-Z]{1,16}", method)
            or not isinstance(path, str) or not path.startswith("/")
            or len(path) > 2048 or "\n" in path or "\r" in path):
            raise ValueError("invalid method or path")
        if not isinstance(timestamp, int) or not isinstance(nonce, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{16,128}", nonce
        ):
            raise ValueError("invalid timestamp or nonce")
        return b"\n".join((method.encode(), path.encode(), str(timestamp).encode(),
                           nonce.encode(), _json_bytes(body)))

    def sign(self, method: str, path: str, body: dict[str, Any],
             *, timestamp: int | None = None, nonce: str | None = None) -> dict[str, Any]:
        ts = int(self._clock()) if timestamp is None else timestamp
        n = secrets.token_urlsafe(18) if nonce is None else nonce
        message = self._message(method, path, ts, n, body)
        signature = hmac.new(self._secret, message, hashlib.sha256).hexdigest()
        return {"timestamp": ts, "nonce": n, "signature": signature}

    def verify(self, method: str, path: str, body: dict[str, Any],
               headers: dict[str, Any]) -> None:
        if not isinstance(headers, dict):
            raise SecurityError("invalid signed request")
        ts, nonce, signature = (headers.get("timestamp"), headers.get("nonce"),
                                headers.get("signature"))
        if (not isinstance(ts, int) or abs(self._clock() - ts) > self._skew
            or not isinstance(nonce, str) or not isinstance(signature, str)
            or not re.fullmatch(r"[0-9a-f]{64}", signature)):
            raise SecurityError("invalid signed request")
        try:
            message = self._message(method, path, ts, nonce, body)
        except (TypeError, ValueError) as exc:
            raise SecurityError("invalid signed request") from exc
        expected = hmac.new(self._secret, message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise SecurityError("invalid signed request")
        with self._lock:
            cutoff = self._clock() - self._skew
            while self._seen:
                first_nonce, first_time = next(iter(self._seen.items()))
                if first_time >= cutoff:
                    break
                self._seen.pop(first_nonce)
            if nonce in self._seen:
                raise SecurityError("replayed request")
            if len(self._seen) >= self._max_nonces:
                raise SecurityError("replay cache capacity reached")
            self._seen[nonce] = float(ts)


@dataclass(frozen=True)
class AuditEvent:
    timestamp: float
    action: str
    subject: str
    outcome: str
    details: tuple[tuple[str, str], ...]


class MemoryAuditSink:
    """Bounded append-only-in-process audit sink; never accepts secret fields."""
    _FORBIDDEN = {"token", "api_key", "secret", "password", "authorization",
                  "signature", "credential"}
    def __init__(self, capacity: int = 10_000,
                 clock: Callable[[], float] = time.time) -> None:
        if not 1 <= capacity <= 100_000:
            raise ValueError("capacity must be between 1 and 100000")
        self._capacity, self._clock = capacity, clock
        self._events: list[AuditEvent] = []
        self._lock = threading.Lock()

    def record(self, action: str, subject: str, outcome: str,
               details: dict[str, Any] | None = None) -> AuditEvent:
        for value, label, limit in ((action, "action", 64), (subject, "subject", 128),
                                    (outcome, "outcome", 32)):
            if not isinstance(value, str) or not value or len(value) > limit:
                raise ValueError(f"invalid audit {label}")
        safe = []
        for key, value in (details or {}).items():
            if not isinstance(key, str) or key.lower() in self._FORBIDDEN:
                raise ValueError("sensitive audit fields are forbidden")
            rendered = str(value)
            if len(key) > 64 or len(rendered) > 256:
                raise ValueError("audit detail exceeds limit")
            safe.append((key, rendered))
        event = AuditEvent(self._clock(), action, subject, outcome, tuple(sorted(safe)))
        with self._lock:
            if len(self._events) >= self._capacity:
                raise SecurityError("audit sink capacity reached")
            self._events.append(event)
        return event

    def events(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)
