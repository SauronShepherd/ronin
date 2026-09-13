from __future__ import annotations

import json
from typing import cast
from urllib.error import URLError
from urllib.request import OpenerDirector

import pytest

from studio_security import HttpsOidcJwksProvider, OidcDiscoveryError

_ISSUER = "https://issuer.example/tenant"
_DISCOVERY = _ISSUER + "/.well-known/openid-configuration"
_JWKS = "https://keys.example/jwks.json"


class _Response:
    def __init__(self, payload: object, *, content_length: str | None = None, raw: bytes | None = None):
        self._data = json.dumps(payload).encode("utf-8") if raw is None else raw
        self.headers = {} if content_length is None else {"Content-Length": content_length}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    def read(self, limit: int) -> bytes:
        return self._data[:limit]


class _Opener:
    def __init__(self, *items: object) -> None:
        self.items = list(items)
        self.calls: list[tuple[str, float]] = []

    def open(self, request, *, timeout: float):
        self.calls.append((request.full_url, timeout))
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _provider(opener: _Opener, **kwargs) -> HttpsOidcJwksProvider:
    return HttpsOidcJwksProvider(
        _ISSUER,
        opener=cast(OpenerDirector, opener),
        **kwargs,
    )


def test_https_oidc_provider_fetches_discovery_and_jwks_with_timeout() -> None:
    opener = _Opener(
        _Response({"issuer": _ISSUER, "jwks_uri": _JWKS}),
        _Response({"keys": [{"kid": "one", "kty": "RSA"}]}),
    )
    provider = _provider(opener, timeout_seconds=2.5)

    assert provider.discovery_url == _DISCOVERY
    assert provider.jwks() == {"keys": [{"kid": "one", "kty": "RSA"}]}
    assert opener.calls == [(_DISCOVERY, 2.5), (_JWKS, 2.5)]


def test_https_oidc_provider_refetches_to_observe_key_rotation() -> None:
    opener = _Opener(
        _Response({"issuer": _ISSUER, "jwks_uri": _JWKS}),
        _Response({"keys": [{"kid": "one"}]}),
        _Response({"issuer": _ISSUER, "jwks_uri": _JWKS}),
        _Response({"keys": [{"kid": "two"}]}),
    )
    provider = _provider(opener)

    assert provider.jwks()["keys"] == [{"kid": "one"}]
    assert provider.jwks()["keys"] == [{"kid": "two"}]
    assert len(opener.calls) == 4


@pytest.mark.parametrize(
    "issuer,message",
    [
        ("http://issuer.example", "HTTPS"),
        ("https://user:pass@issuer.example", "credentials"),
        ("https://issuer.example?tenant=x", "query or fragment"),
        ("https://issuer.example#fragment", "query or fragment"),
    ],
)
def test_https_oidc_provider_rejects_unsafe_issuer_urls(issuer: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        HttpsOidcJwksProvider(issuer)


def test_https_oidc_provider_rejects_discovery_issuer_mismatch() -> None:
    provider = _provider(
        _Opener(_Response({"issuer": "https://other.example", "jwks_uri": _JWKS}))
    )
    with pytest.raises(OidcDiscoveryError, match="does not match"):
        provider.jwks()


@pytest.mark.parametrize(
    "jwks_uri,message",
    [
        ("http://keys.example/jwks", "HTTPS"),
        ("https://user:pass@keys.example/jwks", "forbidden"),
        ("https://keys.example/jwks#fragment", "forbidden"),
    ],
)
def test_https_oidc_provider_rejects_unsafe_jwks_uri(jwks_uri: str, message: str) -> None:
    provider = _provider(_Opener(_Response({"issuer": _ISSUER, "jwks_uri": jwks_uri})))
    with pytest.raises(OidcDiscoveryError, match=message):
        provider.jwks()


def test_https_oidc_provider_rejects_declared_and_actual_oversize_responses() -> None:
    declared = _provider(
        _Opener(_Response({}, content_length="100")),
        max_response_bytes=10,
    )
    with pytest.raises(OidcDiscoveryError, match="byte limit"):
        declared.jwks()

    actual = _provider(
        _Opener(_Response({}, raw=b"x" * 11)),
        max_response_bytes=10,
    )
    with pytest.raises(OidcDiscoveryError, match="byte limit"):
        actual.jwks()


def test_https_oidc_provider_rejects_malformed_metadata_and_jwks_shape() -> None:
    malformed = _provider(_Opener(_Response({}, raw=b"{not-json")))
    with pytest.raises(OidcDiscoveryError, match="valid UTF-8 JSON"):
        malformed.jwks()

    non_object = _provider(_Opener(_Response([], raw=b"[]")))
    with pytest.raises(OidcDiscoveryError, match="JSON object"):
        non_object.jwks()

    missing_keys = _provider(
        _Opener(
            _Response({"issuer": _ISSUER, "jwks_uri": _JWKS}),
            _Response({}),
        )
    )
    with pytest.raises(OidcDiscoveryError, match="keys array"):
        missing_keys.jwks()

    invalid_key = _provider(
        _Opener(
            _Response({"issuer": _ISSUER, "jwks_uri": _JWKS}),
            _Response({"keys": ["invalid"]}),
        )
    )
    with pytest.raises(OidcDiscoveryError, match="only JSON objects"):
        invalid_key.jwks()


def test_https_oidc_provider_hides_transport_error_details() -> None:
    provider = _provider(_Opener(URLError("sensitive upstream detail")))
    with pytest.raises(OidcDiscoveryError) as failed:
        provider.jwks()
    assert str(failed.value) == "OIDC discovery request failed"
    assert "sensitive" not in str(failed.value)


def test_https_oidc_provider_validates_transport_configuration() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        HttpsOidcJwksProvider(_ISSUER, timeout_seconds=0)
    with pytest.raises(ValueError, match="max_response_bytes"):
        HttpsOidcJwksProvider(_ISSUER, max_response_bytes=0)
    with pytest.raises(ValueError, match="max_response_bytes"):
        HttpsOidcJwksProvider(_ISSUER, max_response_bytes=1024 * 1024 + 1)
