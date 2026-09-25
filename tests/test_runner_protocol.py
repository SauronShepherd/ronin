import json
from pathlib import Path

import pytest

from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.runner_protocol import (
    PROTOCOL,
    RunnerProtocolError,
    decode_envelope,
    negotiate_capabilities,
    validate_envelope,
)


def _envelope(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "protocol": PROTOCOL,
        "message_type": "dispatch",
        "request_id": "request-1",
        "execution_id": "execution-1",
        "attempt_id": "attempt-1",
        "payload": {"language": "python", "source": "1 + 1"},
    }
    value.update(overrides)
    return value


def test_runner_envelope_validates_and_decodes_canonical_json() -> None:
    payload = _envelope(capabilities=["cancel.cooperative", "execute.python"])
    assert validate_envelope(payload)["protocol"] == PROTOCOL
    assert (
        decode_envelope(
            b'{"message_type":"dispatch","payload":{},"protocol":"ronin/runner/v1",'
            b'"request_id":"request-1"}'
        )["message_type"]
        == "dispatch"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"protocol": "ronin/runner/v2"},
        {"message_type": "unknown"},
        {"request_id": " "},
        {"payload": []},
        {"unexpected": True},
        {"capabilities": ["z", "a"]},
    ],
)
def test_runner_envelope_rejects_unsafe_shape(change: dict[str, object]) -> None:
    with pytest.raises(RunnerProtocolError):
        validate_envelope(_envelope(**change))


def test_runner_envelope_rejects_noncanonical_json() -> None:
    with pytest.raises(RunnerProtocolError, match="canonical JSON"):
        decode_envelope(b'{"protocol":"ronin/runner/v1","protocol":"duplicate"}')


def test_runner_protocol_golden_fixtures_preserve_canonical_bytes() -> None:
    fixture_path = Path(__file__).parent / "golden" / "runner_protocol_v1.json"
    document = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert document["schema"] == "ronin.runner.protocol/v1"
    for fixture in document["fixtures"]:
        payload = fixture["payload"]
        assert encode_canonical_json(payload).decode("utf-8") == fixture["canonical"]
        validate_envelope(payload)


def test_runner_capability_negotiation_fails_closed_on_missing_required() -> None:
    assert negotiate_capabilities(
        ["cancel.cooperative", "execute.python"],
        ["cancel.cooperative", "execute.python", "resource.observation.v1"],
    ) == ("cancel.cooperative", "execute.python")
    with pytest.raises(RunnerProtocolError, match="unavailable"):
        negotiate_capabilities(["execute.rust"], ["execute.python"])


def test_runner_capability_negotiation_rejects_unordered_sets() -> None:
    with pytest.raises(RunnerProtocolError, match="sorted"):
        negotiate_capabilities(["z", "a"], ["a", "z"])


def test_runner_protocol_json_schema_matches_public_contract() -> None:
    schema_path = Path(__file__).parents[1] / "api" / "runner-protocol-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["protocol"]["const"] == PROTOCOL
    assert set(schema["required"]) == {"protocol", "message_type", "request_id", "payload"}
