from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.test_run_summary import main


def test_pytest_summary_prints_scope_selection_and_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "pytest-timings.json"
    junit = tmp_path / "pytest.xml"
    report.write_text(
        json.dumps(
            {
                "exit_status": 1,
                "execution": {
                    "mode": "postgres-diagnostic-or-full",
                    "selection": "path=tests/test_db.py",
                    "service_profile": "isolated-postgres-16.4",
                    "coverage_enabled": "disabled",
                    "source_commit": "abc123",
                    "worktree_clean": "False",
                    "qualification_mode": "DIRTY-WORKTREE DIAGNOSTIC",
                },
                "summary": {
                    "selected": 4,
                    "executed": 4,
                    "filtered_out": 50,
                    "outcomes": {"passed": 2, "skipped": 1, "failed": 1},
                },
                "timing": {
                    "pytest_session_body_seconds": 8.25,
                    "test_phase_seconds": 4.5,
                    "startup_and_collection_seconds": 2.0,
                },
                "slowest_tests": [
                    {
                        "nodeid": "tests/test_db.py::test_slow",
                        "duration_seconds": 3.0,
                        "outcome": "passed",
                    }
                ]
                + [
                    {
                        "nodeid": f"tests/test_db.py::test_slow_{index}",
                        "duration_seconds": 2.0 - index / 10,
                        "outcome": "passed",
                    }
                    for index in range(1, 6)
                ],
                "collection_skips": [
                    {
                        "nodeid": "tests/test_provider.py",
                        "skip_reason": "provider not configured",
                    }
                ],
                "tests": [{"nodeid": "tests/test_db.py::test_regression", "outcome": "failed"}],
            }
        ),
        encoding="utf-8",
    )
    junit.write_text(
        '<testsuites><testsuite tests="4"><testcase name="a" />'
        '<testcase name="b" /><testcase name="failed"><failure /></testcase>'
        '<testcase name="skip"><skipped /></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["test_run_summary", str(report), "--junit", str(junit)])

    assert main() == 1
    output = capsys.readouterr().out
    assert "path=tests/test_db.py" in output
    assert "isolated-postgres-16.4 / disabled" in output
    assert "4 / 4 / 50" in output
    assert "2 / 1 / 1" in output
    assert "3.00s tests/test_db.py::test_slow" in output
    assert "slowest cases:" in output
    assert "collection skips (1):" in output
    assert "provider not configured" in output
    assert "tests/test_db.py::test_regression [failed]" in output
    assert "JUnit reconciliation: MATCH" in output


def test_runner_summary_fails_when_cleanup_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "runner-timings.json"
    report.write_text(
        json.dumps({"cleanup_status": "failed", "total_wall_seconds": 12.0}), encoding="utf-8"
    )
    monkeypatch.setattr("sys.argv", ["test_run_summary", str(report)])

    assert main() == 1
    assert "cleanup status: failed" in capsys.readouterr().out


def test_postgres_runner_summary_fails_when_pytest_never_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "runner-timings.json"
    report.write_text(
        json.dumps(
            {
                "status": "failed",
                "test_exit_code": 1,
                "failure": "Could not start isolated PostgreSQL container.",
                "pytest_wall_seconds": None,
                "cleanup_status": "not-required",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["test_run_summary", str(report)])

    assert main() == 1
    output = capsys.readouterr().out
    assert "pytest did not complete successfully" in output
    assert "Could not start isolated PostgreSQL container" in output


def test_postgres_runner_summary_accepts_completed_passing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "runner-timings.json"
    report.write_text(
        json.dumps(
            {
                "status": "passed",
                "test_exit_code": 0,
                "pytest_wall_seconds": 4.2,
                "cleanup_status": "succeeded",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["test_run_summary", str(report)])

    assert main() == 0
    assert "pytest=4.20s" in capsys.readouterr().out


def test_live_summary_shows_real_api_log_and_route_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "qualification-summary.json"
    report.write_text(
        json.dumps(
            {
                "status": "passed",
                "testKind": "live-api-diagnostic",
                "candidate": "abc123",
                "worktree": "DIRTY-WORKTREE DIAGNOSTIC",
                "durationSeconds": 35.0,
                "playwright": {"executed": 1, "passed": 1, "skipped": 0, "failed": 0},
                "apiTraffic": {
                    "events": 7,
                    "correlatedHttpLogs": 7,
                    "uncorrelated": 0,
                    "outcomes": {"OK": 7},
                },
                "realServices": {"postgres": False, "kafka": False, "roninApi": True},
                "applicationLogLevels": {"WARN": 0, "ERROR": 0},
                "routeCoverage": {"audited": False, "activeRoutes": 25},
                "phaseDurationsSeconds": {"browser": 15.0},
                "evidenceDirectory": str(tmp_path),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["test_run_summary", str(report)])

    assert main() == 0
    output = capsys.readouterr().out
    assert "browser cases passed / total / skipped / failed: 1 / 1 / 0 / 0" in output
    assert "API events / correlated logs / uncorrelated: 7 / 7 / 0" in output
    assert "route audit / routes: False / 25" in output


def test_live_summary_fails_closed_when_browser_or_api_log_counts_disagree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "qualification-summary.json"
    report.write_text(
        json.dumps(
            {
                "status": "passed",
                "testKind": "live-api-diagnostic",
                "playwright": {"executed": 2, "passed": 1, "skipped": 0, "failed": 0},
                "apiTraffic": {
                    "events": 7,
                    "correlatedHttpLogs": 6,
                    "uncorrelated": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["test_run_summary", str(report)])

    assert main() == 1
    output = capsys.readouterr().out
    assert "INVALID browser case totals" in output
    assert "INVALID API/log correlation totals" in output


def test_summary_rejects_unknown_evidence_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "summary.json"
    report.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["test_run_summary", str(report)])

    with pytest.raises(SystemExit, match="2"):
        main()


def test_pytest_summary_fails_when_junit_counts_do_not_reconcile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    timing = tmp_path / "pytest-timings.json"
    timing.write_text(
        json.dumps(
            {
                "exit_status": 0,
                "execution": {},
                "summary": {
                    "selected": 1,
                    "executed": 1,
                    "filtered_out": 0,
                    "outcomes": {"passed": 1, "skipped": 0, "failed": 0},
                },
                "timing": {},
            }
        ),
        encoding="utf-8",
    )
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testsuite tests="2"><testcase name="passed" />'
        '<testcase name="collection-skip"><skipped /></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    monkeypatch.setattr("sys.argv", ["test_run_summary", str(timing), "--junit", str(junit)])

    assert main() == 1
    assert "JUnit reconciliation: MISMATCH" in capsys.readouterr().out
