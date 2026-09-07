"""Opaque keyset cursor helpers shared by durable store adapters."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from studio_orchestrator import Instant, JobId, JobState, RunId

_CURSOR_VERSION = 1
_MAX_CURSOR_BYTES = 1024


def encode_cursor(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    if not cursor or len(cursor.encode("utf-8")) > _MAX_CURSOR_BYTES:
        raise ValueError("invalid cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(decoded, dict):
        raise ValueError("invalid cursor")
    return decoded


def _job_state_value(state: JobState | None) -> str | None:
    return None if state is None else state.value


def encode_job_cursor(
    *,
    created_at: Instant,
    job_id: JobId,
    project_id: str | None,
    state: JobState | None,
) -> str:
    return encode_cursor(
        {
            "v": _CURSOR_VERSION,
            "kind": "jobs",
            "created_at": str(created_at),
            "job_id": str(job_id),
            "project_id": project_id,
            "state": _job_state_value(state),
        }
    )


def decode_job_cursor(
    cursor: str,
    *,
    project_id: str | None,
    state: JobState | None,
) -> tuple[Instant, JobId]:
    payload = decode_cursor(cursor)
    expected_keys = {"v", "kind", "created_at", "job_id", "project_id", "state"}
    if set(payload) != expected_keys or payload.get("v") != _CURSOR_VERSION:
        raise ValueError("invalid job cursor")
    if payload.get("kind") != "jobs":
        raise ValueError("invalid job cursor")
    if payload.get("project_id") != project_id or payload.get("state") != _job_state_value(state):
        raise ValueError("job cursor does not match filters")
    created_at = payload.get("created_at")
    job_id = payload.get("job_id")
    if not isinstance(created_at, str) or not isinstance(job_id, str) or not job_id:
        raise ValueError("invalid job cursor")
    try:
        return Instant(created_at), JobId(job_id)
    except ValueError as exc:
        raise ValueError("invalid job cursor") from exc


def encode_event_cursor(
    *,
    run_id: RunId,
    next_sequence: int,
    attempt_ordinal: int,
    attempt_sequence: int,
) -> str:
    return encode_cursor(
        {
            "v": _CURSOR_VERSION,
            "kind": "run-events",
            "run_id": str(run_id),
            "next_sequence": next_sequence,
            "attempt_ordinal": attempt_ordinal,
            "attempt_sequence": attempt_sequence,
        }
    )


def initial_event_cursor(run_id: RunId) -> str:
    return encode_event_cursor(
        run_id=run_id,
        next_sequence=0,
        attempt_ordinal=0,
        attempt_sequence=-1,
    )


def decode_event_cursor(cursor: str, *, run_id: RunId) -> tuple[int, int, int]:
    payload = decode_cursor(cursor)
    expected_keys = {
        "v",
        "kind",
        "run_id",
        "next_sequence",
        "attempt_ordinal",
        "attempt_sequence",
    }
    if set(payload) != expected_keys or payload.get("v") != _CURSOR_VERSION:
        raise ValueError("invalid event cursor")
    if payload.get("kind") != "run-events" or payload.get("run_id") != str(run_id):
        raise ValueError("event cursor does not match run")
    next_sequence = payload.get("next_sequence")
    attempt_ordinal = payload.get("attempt_ordinal")
    attempt_sequence = payload.get("attempt_sequence")
    if (
        not isinstance(next_sequence, int)
        or isinstance(next_sequence, bool)
        or next_sequence < 0
        or not isinstance(attempt_ordinal, int)
        or isinstance(attempt_ordinal, bool)
        or attempt_ordinal < 0
        or not isinstance(attempt_sequence, int)
        or isinstance(attempt_sequence, bool)
        or attempt_sequence < -1
        or (attempt_ordinal == 0 and attempt_sequence != -1)
        or (attempt_ordinal > 0 and attempt_sequence < 0)
    ):
        raise ValueError("invalid event cursor")
    return next_sequence, attempt_ordinal, attempt_sequence


def validate_limit(limit: int) -> None:
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")


__all__ = (
    "decode_cursor",
    "decode_event_cursor",
    "decode_job_cursor",
    "encode_cursor",
    "encode_event_cursor",
    "encode_job_cursor",
    "initial_event_cursor",
    "validate_limit",
)
