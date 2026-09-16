from __future__ import annotations

import json
from pathlib import Path

import pytest

from studio_security import FileJwksProvider, JwksFileError


def test_file_jwks_provider_reads_valid_document_and_observes_rotation(tmp_path: Path) -> None:
    path = tmp_path / "jwks.json"
    first = {"keys": [{"kid": "one", "kty": "RSA"}]}
    second = {"keys": [{"kid": "two", "kty": "EC"}]}
    path.write_text(json.dumps(first), encoding="utf-8")
    provider = FileJwksProvider(path)

    assert provider.jwks() == first
    replacement = tmp_path / "jwks.next"
    replacement.write_text(json.dumps(second), encoding="utf-8")
    replacement.replace(path)
    assert provider.jwks() == second


def test_file_jwks_provider_rejects_oversize_content(tmp_path: Path) -> None:
    path = tmp_path / "jwks.json"
    path.write_text('{"keys":[]}', encoding="utf-8")
    provider = FileJwksProvider(path, max_bytes=8)

    with pytest.raises(JwksFileError, match="byte limit"):
        provider.jwks()


def test_file_jwks_provider_rejects_malformed_utf8_and_json(tmp_path: Path) -> None:
    path = tmp_path / "jwks.json"
    provider = FileJwksProvider(path)

    path.write_bytes(b"\xff\xfe")
    with pytest.raises(JwksFileError, match="UTF-8 JSON"):
        provider.jwks()

    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(JwksFileError, match="UTF-8 JSON"):
        provider.jwks()


@pytest.mark.parametrize(
    "payload,message",
    [
        ([], "JSON object"),
        ({}, "keys array"),
        ({"keys": {}}, "keys array"),
        ({"keys": ["not-an-object"]}, "only JSON objects"),
    ],
)
def test_file_jwks_provider_rejects_invalid_shapes(
    tmp_path: Path, payload: object, message: str
) -> None:
    path = tmp_path / "jwks.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(JwksFileError, match=message):
        FileJwksProvider(path).jwks()


def test_file_jwks_provider_rejects_missing_file_and_invalid_limit(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(JwksFileError, match="not readable"):
        FileJwksProvider(missing).jwks()

    with pytest.raises(ValueError, match="max_bytes"):
        FileJwksProvider(missing, max_bytes=0)

    with pytest.raises(ValueError, match="max_bytes"):
        FileJwksProvider(missing, max_bytes=1024 * 1024 + 1)
