from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_kernel import (
    ExecutionAttemptId,
    ExecutionEvent,
    ExecutionEventId,
    JsonlExecutionEventSink,
)


def _event_line(attempt_id: object, sequence: object, **overrides: object) -> str:
    payload: dict[str, object] = {
        "attempt_id": attempt_id,
        "sequence": sequence,
        "kind": "session.started",
        "cell_id": None,
        "message": "",
    }
    payload.update(overrides)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def test_jsonl_sink_recovers_existing_attempt_and_next_sequence(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        _event_line("attempt-1", 0)
        + "\n"
        + _event_line("attempt-1", 1, kind="cell.started", cell_id="cell-1")
        + "\n",
        encoding="utf-8",
    )

    sink = JsonlExecutionEventSink(path)
    sink.append(
        ExecutionEvent(
            ExecutionEventId(ExecutionAttemptId("attempt-1"), 2),
            "session.completed",
        )
    )

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [event["sequence"] for event in events] == [0, 1, 2]

    with pytest.raises(ValueError, match="only one execution attempt"):
        sink.append(
            ExecutionEvent(
                ExecutionEventId(ExecutionAttemptId("attempt-2"), 3),
                "session.completed",
            )
        )


def test_jsonl_sink_accepts_existing_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("", encoding="utf-8")
    sink = JsonlExecutionEventSink(path)
    sink.append(
        ExecutionEvent(
            ExecutionEventId(ExecutionAttemptId("attempt-1"), 0),
            "session.started",
        )
    )
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_jsonl_sink_rejects_partial_existing_event(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(_event_line("attempt-1", 0), encoding="utf-8")
    with pytest.raises(ValueError, match="partial event"):
        JsonlExecutionEventSink(path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not-json\n", "invalid JSON"),
        (json.dumps([]) + "\n", "invalid event shape"),
        (
            json.dumps(
                {
                    "attempt_id": "attempt-1",
                    "sequence": 0,
                    "kind": "session.started",
                    "cell_id": None,
                }
            )
            + "\n",
            "invalid event shape",
        ),
        (_event_line(123, 0) + "\n", "invalid attempt identity"),
        (_event_line("attempt-1", "0") + "\n", "invalid event sequence"),
        (_event_line("attempt-1", True) + "\n", "invalid event sequence"),
        (_event_line("attempt-1", -1) + "\n", "invalid event sequence"),
        (_event_line("attempt-1", 0, kind=123) + "\n", "invalid event kind"),
        (_event_line("attempt-1", 0, cell_id=123) + "\n", "invalid cell identity"),
        (_event_line("attempt-1", 0, message=123) + "\n", "invalid event message"),
        (_event_line("attempt-1", 0, kind="not-an-event") + "\n", "invalid event semantics"),
        (_event_line("attempt-1", 0, message="bad\x00message") + "\n", "invalid event semantics"),
        (
            _event_line("attempt-1", 0) + "\n" + _event_line("attempt-2", 1) + "\n",
            "mixes execution attempts",
        ),
        (
            _event_line("attempt-1", 0) + "\n" + _event_line("attempt-1", 2) + "\n",
            "sequence is not contiguous",
        ),
    ],
)
def test_jsonl_sink_fails_closed_on_corrupt_existing_ledger(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        JsonlExecutionEventSink(path)
