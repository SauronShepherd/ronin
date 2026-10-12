from __future__ import annotations

import pytest
from studio_core import canonical_json


def test_canonical_validation_keeps_exact_integer_and_float_diagnostics() -> None:
    with pytest.raises(ValueError, match=".") as integer_error:
        canonical_json._validate(2**53)
    assert str(integer_error.value) == (
        "canonical JSON integers must fit the exact cross-language range"
    )

    with pytest.raises(ValueError, match=".") as float_error:
        canonical_json._validate(float("inf"))
    assert str(float_error.value) == (
        "canonical JSON numbers must be finite: Out of range float values"
    )


def test_canonical_validation_rejects_bad_keys_and_nested_unsupported_values() -> None:
    with pytest.raises(TypeError, match=".") as key_error:
        canonical_json._validate({1: "value"})
    assert str(key_error.value) == "canonical JSON object keys must be strings"

    with pytest.raises(TypeError, match=".") as value_error:
        canonical_json._validate(["ok", object()])
    assert str(value_error.value) == "unsupported canonical JSON value type: object"


def test_canonical_encode_preserves_all_identity_options() -> None:
    payload = {"z": "café", "a": [1, True]}
    assert canonical_json.encode(payload) == b'{"a":[1,true],"z":"caf\xc3\xa9"}'


def test_canonical_decode_requires_duplicate_detection_and_validation() -> None:
    with pytest.raises(ValueError, match=".") as duplicate_error:
        canonical_json.decode('{"x":1,"x":2}')
    assert str(duplicate_error.value) == "duplicate canonical JSON object member: x"

    with pytest.raises(ValueError, match=".") as nonfinite_error:
        canonical_json.decode("{\"x\":NaN}")
    assert str(nonfinite_error.value) == "non-finite canonical JSON number is not allowed: NaN"
