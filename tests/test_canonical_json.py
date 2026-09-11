from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from studio_core.canonical_json import decode, encode


GOLDEN = Path(__file__).parent / "golden" / "canonical_json_v1.json"


def test_encode_preserves_legacy_v1_bytes() -> None:
    payload = {
        "z": None,
        "unicode": "café",
        "nested": {"b": False, "a": [True, 2, -0.0]},
        "big": 9007199254740993,
    }
    expected = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert encode(payload) == expected
    assert b"-0.0" in expected


def test_encode_rejects_invalid_identity_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        encode({"x": float("nan")})
    with pytest.raises(ValueError, match="finite"):
        encode({"x": float("inf")})
    with pytest.raises(TypeError, match="keys"):
        encode({1: "x"})
    with pytest.raises(TypeError, match="unsupported"):
        encode({"x": {1, 2}})


def test_decode_rejects_duplicate_and_nonfinite_numbers() -> None:
    invalid = (
        '{"a":1,"a":2}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":-Infinity}',
        '{"x":1e9999}',
    )
    for payload in invalid:
        with pytest.raises(ValueError):
            decode(payload)


def test_published_golden_vectors() -> None:
    fixture = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for vector in fixture["vectors"]:
        decoded = decode(vector["source_json"])
        actual = encode(decoded)
        expected = vector["canonical_utf8"].encode("utf-8")
        assert actual == expected
        assert hashlib.sha256(actual).hexdigest() == vector["sha256"]
    for rejection in fixture["rejections"]:
        with pytest.raises(ValueError):
            decode(rejection["source_json"])
