"""Emit per-node timing and execution evidence for CI shard analysis."""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import monotonic
from typing import Any

_plugin_loaded_at = monotonic()
_collected_nodeids: list[str] = []
_reports: dict[str, dict[str, Any]] = {}
_session_started: float | None = None
_collection_finished: float | None = None


def pytest_sessionstart(session: Any) -> None:  # noqa: ARG001 - pytest hook signature
    """Mark the start of the configured pytest session body."""
    global _collection_finished, _session_started
    _collected_nodeids.clear()
    _reports.clear()
    _collection_finished = None
    _session_started = monotonic()


def pytest_collection_finish(session: Any) -> None:
    """Keep the full collection, including duplicate node IDs, for shard audits."""
    global _collection_finished
    _collection_finished = monotonic()
    _collected_nodeids.extend(item.nodeid for item in session.items)


def pytest_runtest_logreport(report: Any) -> None:
    """Record each phase so retries and duplicate executions remain visible."""
    record = _reports.setdefault(
        report.nodeid,
        {
            "nodeid": report.nodeid,
            "attempts": 0,
            "duration_seconds": 0.0,
            "failed_phase_count": 0,
            "phases": [],
            "outcome": "unknown",
            "flaky": False,
        },
    )
    if report.when == "setup":
        record["attempts"] += 1
    record["duration_seconds"] += float(report.duration)
    record["phases"].append(
        {
            "phase": report.when,
            "outcome": report.outcome,
            "duration_seconds": float(report.duration),
        }
    )
    if report.outcome in {"failed", "skipped"} or report.when == "call":
        outcome = report.outcome
        if hasattr(report, "wasxfail"):
            outcome = "xfailed" if report.outcome == "skipped" else "xpassed"
        record["outcome"] = outcome
    if report.outcome == "failed":
        record["failed_phase_count"] += 1
    record["flaky"] = (
        record["failed_phase_count"] > 0
        and record["attempts"] > 1
        and record["outcome"] != "failed"
    )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:  # noqa: ARG001 - pytest hook signature
    """Write a stable JSON evidence file, even when the test session fails."""
    finished = monotonic()
    raw_installation_seconds = os.environ.get("RONIN_CI_INSTALL_SECONDS")
    try:
        installation_seconds = (
            float(raw_installation_seconds) if raw_installation_seconds is not None else None
        )
    except ValueError:
        installation_seconds = None
    target = Path(os.environ.get("RONIN_PYTEST_TIMINGS_PATH", "pytest-timings.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    tests = [_reports[nodeid] for nodeid in sorted(_reports)]
    payload = {
        "schema": "ronin.pytest-timing-evidence/v2",
        "ci": {
            "commit": os.environ.get("RONIN_CI_COMMIT"),
            "run_id": os.environ.get("RONIN_CI_RUN_ID"),
            "run_attempt": os.environ.get("RONIN_CI_RUN_ATTEMPT"),
            "python_version": os.environ.get("RONIN_CI_PYTHON_VERSION"),
            "shard": os.environ.get("RONIN_CI_TEST_SHARD", "unspecified"),
        },
        "exit_status": int(exitstatus),
        "timing": {
            "installation_seconds": installation_seconds,
            "session_wall_seconds": (finished - _plugin_loaded_at),
            "pytest_session_body_seconds": (
                finished - _session_started if _session_started is not None else None
            ),
            "startup_and_collection_seconds": (
                _collection_finished - _plugin_loaded_at
                if _collection_finished is not None
                else None
            ),
            "test_phase_seconds": sum(record["duration_seconds"] for record in tests),
        },
        "collected_nodeids": _collected_nodeids,
        "executed_nodeids": [
            record["nodeid"] for record in tests for _ in range(record["attempts"])
        ],
        "tests": tests,
    }
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
