"""Bounded HTTPS OIDC discovery + JWKS adapter for the shared server profile."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, OpenerDirector, Request, build_opener

_MAX_RESPONSE_BYTES = 1024 * 1024
_DEFAULT_TIMEOUT_SECONDS = 5.0


class OidcDiscoveryError(RuntimeError):
    """Raised when trusted OIDC metadata/JWKS cannot be fetched or validated."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        del req, fp, code, msg, headers, newurl
        return None


def _issuer_url(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("OIDC issuer must be non-empty and trimmed")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname is None:
        raise ValueError("OIDC issuer must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("OIDC issuer must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("OIDC issuer must not contain query or fragment components")
    return value


def _jwks_url(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OidcDiscoveryError("OIDC discovery jwks_uri must be a non-empty string")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname is None:
        raise OidcDiscoveryError("OIDC discovery jwks_uri must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise OidcDiscoveryError("OIDC discovery jwks_uri contains forbidden URL components")
    return value


class HttpsOidcJwksProvider:
    """Fetch fresh OIDC discovery metadata and JWKS under one bounded HTTPS policy."""

    def __init__(
        self,
        issuer: str,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
        opener: OpenerDirector | None = None,
    ) -> None:
        self._issuer = _issuer_url(issuer)
        if timeout_seconds <= 0:
            raise ValueError("OIDC discovery timeout_seconds must be positive")
        if not 1 <= max_response_bytes <= _MAX_RESPONSE_BYTES:
            raise ValueError(
                f"OIDC discovery max_response_bytes must be between 1 and {_MAX_RESPONSE_BYTES}"
            )
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._opener = opener or build_opener(_RejectRedirects())

    @property
    def issuer(self) -> str:
        return self._issuer

    @property
    def discovery_url(self) -> str:
        return self._issuer.rstrip("/") + "/.well-known/openid-configuration"

    def _fetch_json_object(self, url: str, *, label: str) -> dict[str, object]:
        request = Request(  # noqa: S310
            url,
            headers={"Accept": "application/json", "User-Agent": "ronin-oidc/1"},
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                length_header = response.headers.get("Content-Length")
                if length_header is not None:
                    try:
                        declared_length = int(length_header)
                    except ValueError as exc:
                        raise OidcDiscoveryError(f"{label} response has invalid Content-Length") from exc
                    if declared_length < 0 or declared_length > self._max_response_bytes:
                        raise OidcDiscoveryError(f"{label} response exceeds configured byte limit")
                raw = response.read(self._max_response_bytes + 1)
        except OidcDiscoveryError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise OidcDiscoveryError(f"{label} request failed") from exc
        if len(raw) > self._max_response_bytes:
            raise OidcDiscoveryError(f"{label} response exceeds configured byte limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OidcDiscoveryError(f"{label} response must contain valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise OidcDiscoveryError(f"{label} response must be a JSON object")
        return payload

    def jwks(self) -> dict[str, object]:
        discovery = self._fetch_json_object(self.discovery_url, label="OIDC discovery")
        discovered_issuer = discovery.get("issuer")
        if discovered_issuer != self._issuer:
            raise OidcDiscoveryError("OIDC discovery issuer does not match configured issuer")
        jwks_uri = _jwks_url(discovery.get("jwks_uri"))
        jwks = self._fetch_json_object(jwks_uri, label="OIDC JWKS")
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            raise OidcDiscoveryError("OIDC JWKS document must contain a keys array")
        if not all(isinstance(item, dict) for item in keys):
            raise OidcDiscoveryError("OIDC JWKS keys array must contain only JSON objects")
        return jwks


__all__ = ("HttpsOidcJwksProvider", "OidcDiscoveryError")
