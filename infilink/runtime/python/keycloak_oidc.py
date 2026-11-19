"""Keycloak OIDC access-token validation for INFILINK.

This adapter validates signed Keycloak access tokens and maps explicitly
configured Keycloak roles to INFILINK scopes. It does not implement browser
login, authorization-code exchange, or durable sessions.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from security import Principal, SecurityError

_SCOPE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


@dataclass(frozen=True)
class KeycloakOIDCConfig:
    issuer: str
    audience: str
    client_id: str
    jwks_url: str
    role_scope_map: dict[str, frozenset[str]] = field(default_factory=dict)
    algorithms: tuple[str, ...] = ("RS256",)

    def __post_init__(self) -> None:
        for name in ("issuer", "jwks_url"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.startswith("https://"):
                raise ValueError(f"{name} must be an HTTPS URL")
        for name in ("audience", "client_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise ValueError(f"{name} must contain 1..256 characters")
        if not self.algorithms or any(a != "RS256" for a in self.algorithms):
            raise ValueError("only the RS256 signing algorithm is supported")
        if not isinstance(self.role_scope_map, dict) or len(self.role_scope_map) > 256:
            raise ValueError("role_scope_map must be a bounded mapping")
        for role, scopes in self.role_scope_map.items():
            if not isinstance(role, str) or not role or len(role) > 128:
                raise ValueError("invalid Keycloak role name")
            if not isinstance(scopes, (set, frozenset)) or not scopes:
                raise ValueError("each mapped role must grant at least one scope")
            if any(not isinstance(s, str) or not _SCOPE.fullmatch(s) for s in scopes):
                raise ValueError("invalid INFILINK scope in role mapping")


class KeycloakOIDCVerifier:
    """Validate Keycloak JWT access tokens against issuer, audience and JWKS."""

    def __init__(self, config: KeycloakOIDCConfig) -> None:
        if not isinstance(config, KeycloakOIDCConfig):
            raise ValueError("KeycloakOIDCConfig is required")
        self.config = config
        try:
            import jwt
        except ImportError as exc:
            raise RuntimeError(
                "install the optional dependency: pip install -r requirements-oidc.txt"
            ) from exc
        self._jwt = jwt
        self._jwks = jwt.PyJWKClient(config.jwks_url, cache_jwk_set=True,
                                     lifespan=300)

    def verify_access_token(self, token: str) -> Principal:
        if not isinstance(token, str) or not token or len(token) > 16_384:
            raise SecurityError("invalid identity token")
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token).key
            claims = self._jwt.decode(
                token,
                signing_key,
                algorithms=list(self.config.algorithms),
                issuer=self.config.issuer,
                audience=self.config.audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"],
                         "verify_signature": True, "verify_exp": True,
                         "verify_iss": True, "verify_aud": True},
            )
            if not isinstance(claims, dict):
                raise ValueError("JWT claims must be an object")
            if claims.get("azp") != self.config.client_id:
                raise ValueError("unexpected authorized party")
            subject = claims.get("sub")
            expires = claims.get("exp")
            if not isinstance(subject, str) or not subject or len(subject) > 255:
                raise ValueError("invalid subject")
            if isinstance(expires, bool) or not isinstance(expires, (int, float)):
                raise ValueError("invalid expiry")
            scopes = self._map_scopes(claims)
            if not scopes:
                raise ValueError("token has no mapped INFILINK permissions")
            key_id = "oidc-" + hashlib.sha256(
                (self.config.issuer + "|" + subject).encode("utf-8")
            ).hexdigest()[:24]
            return Principal(key_id, subject, frozenset(scopes), float(expires))
        except Exception as exc:
            raise SecurityError("identity token validation failed") from exc

    def _map_scopes(self, claims: dict[str, Any]) -> set[str]:
        roles: set[str] = set()
        realm = claims.get("realm_access", {})
        if isinstance(realm, dict) and isinstance(realm.get("roles"), list):
            roles.update(r for r in realm["roles"] if isinstance(r, str))
        resources = claims.get("resource_access", {})
        if isinstance(resources, dict):
            client = resources.get(self.config.client_id, {})
            if isinstance(client, dict) and isinstance(client.get("roles"), list):
                roles.update(r for r in client["roles"] if isinstance(r, str))
        scopes: set[str] = set()
        for role in roles:
            scopes.update(self.config.role_scope_map.get(role, ()))
        return scopes
