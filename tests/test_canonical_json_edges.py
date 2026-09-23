from __future__ import annotations

import pytest
from studio_core.canonical_json import decode, encode


def test_canonical_json_accepts_exact_integer_boundary_and_all_sequence_forms() -> None:
    assert encode({"n": 2**53 - 1}) == b'{"n":9007199254740991}'
    assert encode((1, 2)) == b"[1,2]"
    assert decode(bytearray(b'{"b":[true,null]}')) == {"b": [True, None]}
    assert encode({"z": 1, "a": 2}) == b'{"a":2,"z":1}'


@pytest.mark.parametrize("value", [{1: "not-json"}, b"bytes", bytearray(b"bytes")])
def test_canonical_json_rejects_unsupported_values(value: object) -> None:
    with pytest.raises(TypeError):
        encode(value)


@pytest.mark.parametrize("value", [2**53, -(2**53)])
def test_canonical_json_rejects_out_of_range_integers(value: int) -> None:
    with pytest.raises(ValueError, match="exact cross-language range"):
        encode(value)


def test_canonical_json_rejects_duplicate_members_at_nested_depth() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        decode('{"outer":{"x":1,"x":2}}')


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        encode(value)


def test_canonical_json_rejects_invalid_payload_and_duplicate_top_level_member() -> None:
    with pytest.raises(ValueError, match="invalid"):
        decode("{not-json}")
    with pytest.raises(ValueError, match="duplicate"):
        decode('{"x":1,"x":2}')


def test_canonical_json_preserves_unicode_and_nested_sequence_order() -> None:
    value = {"text": "café", "items": (3, {"b": 2, "a": 1})}
    assert encode(value) == '{"items":[3,{"a":1,"b":2}],"text":"café"}'.encode()


def test_canonical_json_rejects_non_string_keys_even_when_key_is_bool() -> None:
    with pytest.raises(TypeError, match="object keys must be strings"):
        encode({True: "not-json"})
