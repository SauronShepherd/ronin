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
        "big": 9007199254740991,
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
        with pytest.raises(ValueError, match="canonical JSON"):
            decode(payload)


def test_rejects_integers_outside_exact_cross_language_range() -> None:
    with pytest.raises(ValueError, match="exact cross-language"):
        encode({"x": 2**53})


def test_canonical_json_accepts_sequences_and_binary_input() -> None:
    encoded = encode(("a", 1))
    assert encoded == b'["a",1]'
    assert decode(encoded) == ["a", 1]
    assert decode(bytearray(encoded)) == ["a", 1]


def test_canonical_json_rejects_unsupported_binary_values_and_malformed_json() -> None:
    with pytest.raises(TypeError, match="unsupported"):
        encode({"x": b"bytes"})
    with pytest.raises(ValueError, match="canonical JSON payload is invalid"):
        decode('{"x":')


def test_published_golden_vectors() -> None:
    fixture = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for vector in fixture["vectors"]:
        decoded = decode(vector["source_json"])
        actual = encode(decoded)
        expected = vector["canonical_utf8"].encode("utf-8")
        assert actual == expected
        assert hashlib.sha256(actual).hexdigest() == vector["sha256"]
    for rejection in fixture["rejections"]:
        with pytest.raises(ValueError, match="canonical JSON"):
            decode(rejection["source_json"])


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (
            2**53,
            "canonical JSON integers must fit the exact cross-language range",
        ),
        (
            float("nan"),
            "canonical JSON numbers must be finite: Out of range float values",
        ),
        (
            {1: "x"},
            "canonical JSON object keys must be strings",
        ),
        (
            {"x": {1, 2}},
            "unsupported canonical JSON value type: set",
        ),
    ],
)
def test_encode_validation_messages_are_stable(value: object, message: str) -> None:
    with pytest.raises((TypeError, ValueError)) as error:
        encode(value)
    assert str(error.value) == message


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ('{"x":1,"x":2}', "duplicate canonical JSON object member: x"),
        ('{"x":NaN}', "non-finite canonical JSON number is not allowed: NaN"),
        ("{not-json}", "canonical JSON payload is invalid"),
    ],
)
def test_decode_validation_messages_are_stable(payload: str, message: str) -> None:
    with pytest.raises(ValueError, match=".") as error:
        decode(payload)
    assert str(error.value) == message
