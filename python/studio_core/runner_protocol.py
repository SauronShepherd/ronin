"""Pure validation for the provider-neutral ``ronin/runner/v1`` envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from .canonical_json import JSONValue
from .canonical_json import decode as decode_canonical_json

PROTOCOL: Final = "ronin/runner/v1"
MESSAGE_TYPES: Final = frozenset(
    {"capabilities", "dispatch", "heartbeat", "cancel", "result", "error"}
)
_REQUIRED_FIELDS: Final = frozenset({"protocol", "message_type", "request_id", "payload"})
_MAX_REQUEST_ID: Final = 256


class RunnerProtocolError(ValueError):
    """Raised when an envelope cannot be safely interpreted by a v1 peer."""


def negotiate_capabilities(required: object, offered: object) -> tuple[str, ...]:
    """Return the usable required capabilities or fail closed on incompatibility."""

    def normalize(value: object, label: str) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise RunnerProtocolError(f"runner {label} capabilities are invalid")
        result = tuple(value)
        if result != tuple(sorted(set(result))):
            raise RunnerProtocolError(f"runner {label} capabilities must be sorted and unique")
        return result

    required_values = normalize(required, "required")
    offered_values = set(normalize(offered, "offered"))
    missing = tuple(item for item in required_values if item not in offered_values)
    if missing:
        raise RunnerProtocolError(
            "runner required capability is unavailable: " + ", ".join(missing)
        )
    return required_values


def validate_envelope(payload: object) -> dict[str, JSONValue]:
    """Validate and return one neutral runner envelope without provider semantics."""

    if not isinstance(payload, Mapping):
        raise RunnerProtocolError("runner envelope must be a JSON object")
    keys = set(payload)
    if not keys.issubset(_REQUIRED_FIELDS | {"execution_id", "attempt_id", "capabilities"}):
        raise RunnerProtocolError("runner envelope contains unknown fields")
    if not _REQUIRED_FIELDS.issubset(keys):
        raise RunnerProtocolError("runner envelope is missing required fields")
    if payload["protocol"] != PROTOCOL:
        raise RunnerProtocolError("runner protocol version is unsupported")
    message_type = payload["message_type"]
    if not isinstance(message_type, str) or message_type not in MESSAGE_TYPES:
        raise RunnerProtocolError("runner message type is unsupported")
    request_id = payload["request_id"]
    if (
        not isinstance(request_id, str)
        or not request_id.strip()
        or len(request_id) > _MAX_REQUEST_ID
    ):
        raise RunnerProtocolError("runner request id is invalid")
    if not isinstance(payload["payload"], Mapping):
        raise RunnerProtocolError("runner envelope payload must be an object")
    for field in ("execution_id", "attempt_id"):
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise RunnerProtocolError(f"runner {field} is invalid")
    if "capabilities" in payload:
        capabilities = payload["capabilities"]
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) or not item.strip() for item in capabilities
        ):
            raise RunnerProtocolError("runner capabilities must be a string array")
        if capabilities != sorted(set(capabilities)):
            raise RunnerProtocolError("runner capabilities must be sorted and unique")
    return cast(dict[str, JSONValue], dict(payload))


def decode_envelope(payload: str | bytes | bytearray) -> dict[str, JSONValue]:
    """Decode canonical JSON and validate one runner envelope."""

    try:
        decoded = decode_canonical_json(payload)
    except ValueError as exc:
        raise RunnerProtocolError("runner envelope is not canonical JSON") from exc
    return validate_envelope(decoded)


__all__ = (
    "PROTOCOL",
    "RunnerProtocolError",
    "decode_envelope",
    "negotiate_capabilities",
    "validate_envelope",
)
