"""Emit per-node timing and execution evidence for local diagnostic runs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from time import monotonic
from typing import Any

_plugin_loaded_at = monotonic()
_collected_nodeids: list[str] = []
_deselected_nodeids: list[str] = []
_collection_skips: list[dict[str, Any]] = []
_reports: dict[str, dict[str, Any]] = {}
_session_started: float | None = None
_collection_finished: float | None = None


def _test_summary(
    tests: list[dict[str, Any]],
    selected_count: int,
    filtered_out_count: int,
    collection_skips: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    """Summarize the selected test items and their final outcomes."""
    collection_skips = collection_skips or []
    outcomes = dict.fromkeys(("passed", "failed", "skipped", "xfailed", "xpassed", "unknown"), 0)
    for test in tests:
        outcome = test.get("outcome")
        if isinstance(outcome, str) and outcome in outcomes:
            outcomes[outcome] += 1
        else:
            outcomes["unknown"] = outcomes["unknown"] + 1
    outcomes["skipped"] += len(collection_skips)
    executed_count = len(tests) + len(collection_skips)
    return {
        "selected": selected_count + len(collection_skips),
        "selected_test_items": selected_count,
        "collection_skipped": len(collection_skips),
        "filtered_out": filtered_out_count,
        "executed": executed_count,
        "not_executed": max(0, selected_count - len(tests)),
        "outcomes": outcomes,
    }


def _skip_reason(report: Any) -> str | None:
    """Return pytest's reason for a skipped or expected-failure phase."""
    if report.outcome != "skipped":
        return None
    expected_failure = getattr(report, "wasxfail", None)
    if expected_failure:
        return str(expected_failure)
    reason = getattr(report, "longrepr", None)
    if reason is None:
        return "pytest reported a skip without a reason"
    rendered = str(reason).strip()
    return rendered or "pytest reported a skip without a reason"


def _collection_skip_reason(report: Any) -> str:
    """Extract pytest's module-level skip text without embedding absolute paths."""
    reason = getattr(report, "longrepr", None)
    if isinstance(reason, tuple) and len(reason) >= 3:
        rendered = str(reason[2]).strip()
    else:
        rendered = str(reason).strip() if reason is not None else ""
    if rendered.startswith("Skipped: "):
        rendered = rendered.removeprefix("Skipped: ").strip()
    return rendered or "pytest collection skipped without a reason"


def pytest_sessionstart(session: Any) -> None:  # noqa: ARG001 - pytest hook signature
    """Mark the start of the configured pytest session body."""
    global _collection_finished, _session_started
    _collected_nodeids.clear()
    _deselected_nodeids.clear()
    _collection_skips.clear()
    _reports.clear()
    _collection_finished = None
    _session_started = monotonic()


def pytest_collection_finish(session: Any) -> None:
    """Keep the exact selected node IDs, including duplicates, for audit evidence."""
    global _collection_finished
    _collection_finished = monotonic()
    _collected_nodeids.extend(item.nodeid for item in session.items)


def pytest_deselected(items: list[Any]) -> None:
    """Record tests excluded by explicit paths, markers or keyword filters."""
    _deselected_nodeids.extend(item.nodeid for item in items)


def pytest_collectreport(report: Any) -> None:
    """Keep module/collector skips that never become pytest test items."""
    if report.outcome != "skipped":
        return
    _collection_skips.append(
        {
            "nodeid": report.nodeid,
            "outcome": "skipped",
            "skip_reason": _collection_skip_reason(report),
        }
    )


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
            "skip_reason": None,
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
    if report.outcome == "skipped":
        record["skip_reason"] = _skip_reason(report)
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
    target = Path(os.environ.get("RONIN_PYTEST_TIMINGS_PATH", "pytest-timings.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    tests = [_reports[nodeid] for nodeid in sorted(_reports)]
    payload = {
        "schema": "ronin.pytest-timing-evidence/v4",
        "execution": {
            "mode": os.environ.get("RONIN_TEST_EXECUTION_MODE", "unspecified"),
            "selection": os.environ.get("RONIN_TEST_SELECTION", "full-or-unrecorded"),
            "coverage_enabled": os.environ.get("RONIN_TEST_COVERAGE", "unknown"),
            "service_profile": os.environ.get("RONIN_TEST_SERVICE_PROFILE", "unknown"),
            "source_commit": os.environ.get("RONIN_TEST_SOURCE_COMMIT", "unknown"),
            "worktree_clean": os.environ.get("RONIN_TEST_WORKTREE_CLEAN", "unknown"),
            "qualification_mode": os.environ.get("RONIN_TEST_QUALIFICATION_MODE", "unknown"),
        },
        "exit_status": int(exitstatus),
        "timing": {
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
        "selected_nodeids": _collected_nodeids,
        "filtered_out_nodeids": _deselected_nodeids,
        "collection_skips": _collection_skips,
        "executed_nodeids": [
            record["nodeid"] for record in tests for _ in range(record["attempts"])
        ],
        "summary": _test_summary(
            tests,
            len(_collected_nodeids),
            len(_deselected_nodeids),
            _collection_skips,
        ),
        "tests": tests,
        "slowest_tests": sorted(
            (
                {
                    "nodeid": record["nodeid"],
                    "duration_seconds": record["duration_seconds"],
                    "outcome": record["outcome"],
                }
                for record in tests
            ),
            key=lambda record: (-record["duration_seconds"], record["nodeid"]),
        )[:25],
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
