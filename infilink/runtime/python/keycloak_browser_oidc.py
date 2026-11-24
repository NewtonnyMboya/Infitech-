"""Server-side Keycloak Authorization Code + PKCE flow for INFILINK.

The flow uses one-time state/nonce/PKCE transactions and validates the ID token
through KeycloakOIDCVerifier. The included transaction store is process-local;
production deployments must inject a durable, shared, atomic one-time store.
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from keycloak_oidc import KeycloakOIDCVerifier
from security import Principal, SecurityError


class OIDCFlowError(SecurityError):
    """Rejected or failed OIDC browser authentication."""


@dataclass(frozen=True)
class LoginTransaction:
    nonce: str
    code_verifier: str
    expires_at: float


class LoginTransactionStore:
    """Bounded process-local one-time state store for development/testing.

    Implementations supplied in production must make consume() atomic across
    workers and persist records securely until expiry.
    """
    def __init__(self, max_entries: int = 10_000,
                 clock: Callable[[], float] = time.time) -> None:
        if not 1 <= max_entries <= 100_000:
            raise ValueError("max_entries must be between 1 and 100000")
        self.max_entries = max_entries
        self.clock = clock
        self._records: dict[str, LoginTransaction] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(state: str) -> str:
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    def put(self, state: str, transaction: LoginTransaction) -> None:
        if not state or not isinstance(transaction, LoginTransaction):
            raise ValueError("valid state and transaction are required")
        with self._lock:
            now = self.clock()
            self._records = {k: v for k, v in self._records.items()
                             if v.expires_at > now}
            if len(self._records) >= self.max_entries:
                raise OIDCFlowError("login transaction capacity reached")
            key = self._key(state)
            if key in self._records:
                raise OIDCFlowError("duplicate login state")
            self._records[key] = transaction

    def consume(self, state: str) -> LoginTransaction:
        if not isinstance(state, str) or not 32 <= len(state) <= 256:
            raise OIDCFlowError("invalid or expired login state")
        with self._lock:
            record = self._records.pop(self._key(state), None)
        if record is None or self.clock() >= record.expires_at:
            raise OIDCFlowError("invalid or expired login state")
        return record


@dataclass(frozen=True)
class OIDCLoginResult:
    principal: Principal
    access_token: str
    expires_in: int


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post_form(url: str, form: dict[str, str], timeout: float) -> dict[str, Any]:
    body = urllib.parse.urlencode(form).encode("ascii")
    request = urllib.request.Request(
        url, data=body,
        headers={"Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                raise OIDCFlowError("OIDC token endpoint rejected the request")
            raw = response.read(65_537)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OIDCFlowError("OIDC token endpoint is unavailable") from exc
    if len(raw) > 65_536:
        raise OIDCFlowError("OIDC token response exceeds the size limit")
    import json
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise OIDCFlowError("OIDC token endpoint returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise OIDCFlowError("OIDC token endpoint returned an invalid response")
    return result


class KeycloakAuthorizationCodeFlow:
    """Build authorization URLs and exchange one-time PKCE authorization codes.

    Discovery is intentionally not performed implicitly. Endpoint URLs must be
    copied from the trusted HTTPS realm discovery document and checked against
    the configured issuer by deployment configuration.
    """
    def __init__(
        self, *, issuer: str, authorization_endpoint: str, token_endpoint: str,
        client_id: str, redirect_uri: str, verifier: KeycloakOIDCVerifier,
        transactions: LoginTransactionStore | Any | None = None,
        post_form: Callable[[str, dict[str, str], float], dict[str, Any]] = _post_form,
        transaction_ttl: int = 300, timeout: float = 8.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        for name, value in (("issuer", issuer),
                            ("authorization_endpoint", authorization_endpoint),
                            ("token_endpoint", token_endpoint),
                            ("redirect_uri", redirect_uri)):
            if not isinstance(value, str) or not value.startswith("https://"):
                raise ValueError(f"{name} must be an HTTPS URL")
        if not isinstance(client_id, str) or not client_id or len(client_id) > 256:
            raise ValueError("client_id must contain 1..256 characters")
        if not 60 <= transaction_ttl <= 900 or not 0 < timeout <= 30:
            raise ValueError("invalid OIDC timeout configuration")
        if not callable(post_form) or not isinstance(verifier, KeycloakOIDCVerifier):
            raise ValueError("a token transport and KeycloakOIDCVerifier are required")
        if verifier.config.issuer != issuer or verifier.config.client_id != client_id:
            raise ValueError("OIDC flow and token verifier configuration must match")
        self.issuer = issuer
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.verifier = verifier
        self.transactions = transactions or LoginTransactionStore(clock=clock)
        if not callable(getattr(self.transactions, "put", None)) or not callable(
            getattr(self.transactions, "consume", None)
        ):
            raise ValueError("transactions must implement atomic put() and consume()")
        self.post_form = post_form
        self.transaction_ttl = transaction_ttl
        self.timeout = timeout
        self.clock = clock

    def begin_login(self, scopes: tuple[str, ...] = ("openid", "profile")) -> str:
        if not scopes or "openid" not in scopes or len(scopes) > 16:
            raise ValueError("OIDC scopes must include openid and contain at most 16 items")
        if any(not isinstance(s, str) or not s or len(s) > 64 for s in scopes):
            raise ValueError("invalid OIDC scope")
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        challenge = secrets.base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self.transactions.put(
            state, LoginTransaction(nonce, code_verifier,
                                    self.clock() + self.transaction_ttl)
        )
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        separator = "&" if "?" in self.authorization_endpoint else "?"
        return self.authorization_endpoint + separator + urllib.parse.urlencode(params)

    def complete_login(self, *, code: str, state: str) -> OIDCLoginResult:
        # Consume before network I/O: a failed exchange requires a fresh login,
        # and the same callback can never replay this authorization transaction.
        transaction = self.transactions.consume(state)
        if not isinstance(code, str) or not code or len(code) > 4096:
            raise OIDCFlowError("invalid authorization code")
        token_response = self.post_form(self.token_endpoint, {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": transaction.code_verifier,
        }, self.timeout)
        access_token = token_response.get("access_token")
        id_token = token_response.get("id_token")
        expires_in = token_response.get("expires_in", 0)
        if (not isinstance(access_token, str) or not access_token or
            len(access_token) > 16_384 or not isinstance(id_token, str) or
            not id_token or len(id_token) > 16_384 or
            isinstance(expires_in, bool) or not isinstance(expires_in, int) or
            not 1 <= expires_in <= 86_400):
            raise OIDCFlowError("OIDC token response is incomplete or invalid")
        principal = self.verifier.verify_id_token(id_token, nonce=transaction.nonce)
        return OIDCLoginResult(principal, access_token, expires_in)
