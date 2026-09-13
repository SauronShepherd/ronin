"""OIDC JWT validation against an injected JWKS provider.

Network discovery is deliberately outside this module. The validator owns the
security-critical issuer/audience/algorithm/claim checks while a deployment
adapter may supply refreshed JWKS documents from its trusted OIDC discovery path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .contracts import Principal


class OidcDependencyError(RuntimeError):
    """Raised when optional JWT validation dependencies are unavailable."""


class OidcAuthenticationError(PermissionError):
    """Raised when an OIDC token cannot be authenticated fail-closed."""


def _jwt() -> Any:
    try:
        import jwt
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise OidcDependencyError(
            "OIDC support requires the optional Ronin security dependencies"
        ) from exc
    return jwt


@dataclass(frozen=True, slots=True)
class OidcConfig:
    issuer: str
    audience: str
    allowed_algorithms: tuple[str, ...] = ("RS256", "ES256")
    leeway_seconds: int = 30

    def __post_init__(self) -> None:
        if not self.issuer or self.issuer != self.issuer.strip():
            raise ValueError("OIDC issuer must be non-empty and trimmed")
        if not self.audience or self.audience != self.audience.strip():
            raise ValueError("OIDC audience must be non-empty and trimmed")
        algorithms = tuple(sorted(set(self.allowed_algorithms)))
        if not algorithms or any(value not in {"RS256", "ES256"} for value in algorithms):
            raise ValueError("OIDC allowed_algorithms must be a non-empty RS256/ES256 subset")
        object.__setattr__(self, "allowed_algorithms", algorithms)
        if self.leeway_seconds < 0 or self.leeway_seconds > 300:
            raise ValueError("OIDC leeway_seconds must be between 0 and 300")


@dataclass(frozen=True, slots=True)
class OidcClaims:
    issuer: str
    subject: str
    audience: tuple[str, ...]
    display_name: str | None = None
    email: str | None = None


@runtime_checkable
class JwksProvider(Protocol):
    def jwks(self) -> dict[str, object]: ...


@runtime_checkable
class OidcPrincipalStore(Protocol):
    def find_principal(self, issuer: str, subject: str) -> Principal | None: ...


class OidcTokenValidator:
    """Validate signature and mandatory OIDC claims against configured trust."""

    def __init__(self, config: OidcConfig, keys: JwksProvider) -> None:
        self._config = config
        self._keys = keys

    def authenticate_claims(self, token: str) -> OidcClaims:
        if not token or token != token.strip() or "\n" in token or "\r" in token:
            raise OidcAuthenticationError("OIDC token must be non-empty, trimmed, and single-line")
        jwt = _jwt()
        try:
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise OidcAuthenticationError("OIDC token has invalid JOSE header") from exc
        if not isinstance(header, dict):
            raise OidcAuthenticationError("OIDC token JOSE header has invalid shape")
        algorithm = header.get("alg")
        key_id = header.get("kid")
        if algorithm not in self._config.allowed_algorithms:
            raise OidcAuthenticationError("OIDC token uses a disallowed signing algorithm")
        if not isinstance(key_id, str) or not key_id:
            raise OidcAuthenticationError("OIDC token is missing key id")

        jwks = self._keys.jwks()
        raw_keys = jwks.get("keys")
        if not isinstance(raw_keys, list):
            raise OidcAuthenticationError("OIDC JWKS has invalid keys collection")
        candidates = [
            key
            for key in raw_keys
            if isinstance(key, dict) and key.get("kid") == key_id
        ]
        if len(candidates) != 1:
            raise OidcAuthenticationError("OIDC signing key id is missing or ambiguous")
        try:
            key = jwt.PyJWK.from_dict(candidates[0])
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(self._config.allowed_algorithms),
                audience=self._config.audience,
                issuer=self._config.issuer,
                leeway=self._config.leeway_seconds,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
        except Exception as exc:
            raise OidcAuthenticationError("OIDC token validation failed") from exc
        if not isinstance(claims, dict):
            raise OidcAuthenticationError("OIDC claims have invalid shape")
        issuer = claims.get("iss")
        subject = claims.get("sub")
        audience_raw = claims.get("aud")
        if not isinstance(issuer, str) or not isinstance(subject, str):
            raise OidcAuthenticationError("OIDC claims are missing issuer/subject")
        if isinstance(audience_raw, str):
            audience = (audience_raw,)
        elif isinstance(audience_raw, list) and all(isinstance(value, str) for value in audience_raw):
            audience = tuple(audience_raw)
        else:
            raise OidcAuthenticationError("OIDC audience claim has invalid shape")
        name = claims.get("name")
        email = claims.get("email")
        return OidcClaims(
            issuer,
            subject,
            tuple(sorted(audience)),
            name if isinstance(name, str) else None,
            email if isinstance(email, str) else None,
        )

    def authenticate_principal(self, token: str, store: OidcPrincipalStore) -> Principal:
        claims = self.authenticate_claims(token)
        principal = store.find_principal(claims.issuer, claims.subject)
        if principal is None:
            raise OidcAuthenticationError("OIDC subject is not provisioned in Ronin")
        if not principal.active:
            raise OidcAuthenticationError("OIDC principal is inactive")
        return principal


__all__ = (
    "JwksProvider",
    "OidcAuthenticationError",
    "OidcClaims",
    "OidcConfig",
    "OidcDependencyError",
    "OidcPrincipalStore",
    "OidcTokenValidator",
)
