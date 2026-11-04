from __future__ import annotations

import json
from math import nan
from pathlib import Path
from typing import Any

import pytest

from tools.pytest_slowest_selection import _load_tests, main


def _write_report(path: Path, tests: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps({"schema": "ronin.pytest-timing-evidence/v3", "tests": tests}),
        encoding="utf-8",
    )


def test_load_tests_rejects_duplicate_node_ids(tmp_path: Path) -> None:
    report = tmp_path / "timings.json"
    _write_report(
        report,
        [
            {
                "nodeid": "tests/test_a.py::test_case",
                "duration_seconds": 1.0,
                "outcome": "passed",
            },
            {
                "nodeid": "tests/test_a.py::test_case",
                "duration_seconds": 2.0,
                "outcome": "passed",
            },
        ],
    )

    with pytest.raises(ValueError, match="duplicate node ID"):
        _load_tests(report)


def test_load_tests_accepts_v4_collection_skip_reports(tmp_path: Path) -> None:
    report = tmp_path / "timings.json"
    report.write_text(
        json.dumps(
            {
                "schema": "ronin.pytest-timing-evidence/v4",
                "collection_skips": [
                    {
                        "nodeid": "tests/integration/test_optional_provider.py",
                        "outcome": "skipped",
                        "skip_reason": "provider is not configured",
                    }
                ],
                "tests": [
                    {
                        "nodeid": "tests/test_a.py::test_case",
                        "duration_seconds": 1.0,
                        "outcome": "passed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert _load_tests(report) == [
        {
            "nodeid": "tests/test_a.py::test_case",
            "duration_seconds": 1.0,
            "outcome": "passed",
        }
    ]


def test_load_tests_rejects_invalid_or_negative_duration(tmp_path: Path) -> None:
    report = tmp_path / "timings.json"
    _write_report(report, [{"nodeid": "tests/test_a.py::test_case", "duration_seconds": -1}])

    with pytest.raises(ValueError, match="invalid test duration"):
        _load_tests(report)


def test_load_tests_rejects_non_finite_duration(tmp_path: Path) -> None:
    report = tmp_path / "timings.json"
    _write_report(
        report,
        [{"nodeid": "tests/test_a.py::test_case", "duration_seconds": nan, "outcome": "passed"}],
    )

    with pytest.raises(ValueError, match="invalid test duration"):
        _load_tests(report)


def test_load_tests_rejects_unrepresentably_large_duration(tmp_path: Path) -> None:
    report = tmp_path / "timings.json"
    _write_report(
        report,
        [
            {
                "nodeid": "tests/test_a.py::test_case",
                "duration_seconds": 10**400,
                "outcome": "passed",
            }
        ],
    )

    with pytest.raises(ValueError, match="invalid test duration"):
        _load_tests(report)


def test_load_tests_rejects_non_text_outcome(tmp_path: Path) -> None:
    report = tmp_path / "timings.json"
    _write_report(
        report,
        [{"nodeid": "tests/test_a.py::test_case", "duration_seconds": 1.0, "outcome": []}],
    )

    with pytest.raises(ValueError, match="invalid test outcome"):
        _load_tests(report)


def test_main_writes_slowest_exact_node_ids_in_stable_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "timings.json"
    output = tmp_path / "selection.txt"
    _write_report(
        report,
        [
            {"nodeid": "tests/test_b.py::test_slow", "duration_seconds": 4.0, "outcome": "passed"},
            {"nodeid": "tests/test_a.py::test_tie", "duration_seconds": 4.0, "outcome": "passed"},
            {"nodeid": "tests/test_c.py::test_fast", "duration_seconds": 1.0, "outcome": "passed"},
            {
                "nodeid": "tests/test_d.py::test_skip",
                "duration_seconds": 99.0,
                "outcome": "skipped",
            },
        ],
    )
    monkeypatch.setattr(
        "sys.argv",
        ["pytest_slowest_selection", str(report), str(output), "--count", "2"],
    )

    assert main() == 0
    assert output.read_text(encoding="utf-8").splitlines() == [
        "tests/test_a.py::test_tie",
        "tests/test_b.py::test_slow",
    ]


def test_main_runs_exact_node_ids_as_individual_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "timings.json"
    output = tmp_path / "selection.txt"
    _write_report(
        report,
        [{"nodeid": "tests/test_a.py::test_one", "duration_seconds": 2.0, "outcome": "passed"}],
    )
    report.write_text(
        json.dumps(
            {
                "schema": "ronin.pytest-timing-evidence/v3",
                "execution": {
                    "mode": "local-only-diagnostic",
                    "service_profile": "none",
                    "coverage_enabled": "disabled",
                },
                "tests": [
                    {
                        "nodeid": "tests/test_a.py::test_one",
                        "duration_seconds": 2.0,
                        "outcome": "passed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "pytest_slowest_selection",
            str(report),
            str(output),
            "--run",
            "--checkout",
            str(tmp_path),
        ],
    )
    calls: list[tuple[list[str], dict[str, Any]]] = []

    class Result:
        returncode = 7

    def fake_run(command: list[str], **kwargs: Any) -> Result:
        calls.append((command, kwargs))
        return Result()

    monkeypatch.setattr("tools.pytest_slowest_selection.subprocess.run", fake_run)

    assert main() == 7
    command, kwargs = calls[0]
    assert command[-2:] == ["-q", "tests/test_a.py::test_one"]
    assert kwargs["cwd"] == tmp_path
    assert kwargs["check"] is False


def test_main_refuses_to_run_service_backed_timings_without_family_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "timings.json"
    output = tmp_path / "selection.txt"
    report.write_text(
        json.dumps(
            {
                "schema": "ronin.pytest-timing-evidence/v3",
                "execution": {
                    "mode": "postgres-diagnostic-or-full",
                    "service_profile": "isolated-postgres-16.4",
                    "coverage_enabled": "enabled",
                },
                "tests": [
                    {
                        "nodeid": "tests/integration/test_db.py::test_live",
                        "duration_seconds": 2.0,
                        "outcome": "passed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["pytest_slowest_selection", str(report), str(output), "--run"],
    )
    monkeypatch.setattr(
        "tools.pytest_slowest_selection.subprocess.run",
        lambda *_args, **_kwargs: pytest.fail(
            "service-backed tests must not run without their family runner"
        ),
    )

    with pytest.raises(SystemExit, match="2"):
        main()
