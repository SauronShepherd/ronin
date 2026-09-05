from __future__ import annotations

from pathlib import Path

import pytest

from tools.v01_acceptance_gate import (
    EXPECTED_STEP_NAMES,
    AcceptanceGateError,
    evaluate_junit,
    require_strict_success,
)


def _write_report(path: Path, cases: list[str]) -> Path:
    body = "\n".join(cases)
    path.write_text(f'<testsuite tests="{len(cases)}">{body}</testsuite>', encoding="utf-8")
    return path


def _case(name: str, child: str = "") -> str:
    return f'<testcase classname="tests.e2e.test_v01_journey" name="{name}">{child}</testcase>'


def test_strict_gate_accepts_exactly_all_fifteen_passing_steps(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "passing.xml", [_case(name) for name in EXPECTED_STEP_NAMES])

    counts = evaluate_junit(report)

    require_strict_success(counts)
    assert counts.passed == 15
    assert counts.live == 15
    assert counts.skipped == 0
    assert counts.xfailed == 0
    assert counts.missing == 0
    assert counts.unexpected == 0


def test_strict_gate_rejects_one_skipped_required_step(tmp_path: Path) -> None:
    cases = [_case(name) for name in EXPECTED_STEP_NAMES]
    cases[6] = _case(EXPECTED_STEP_NAMES[6], '<skipped message="not live"/>')
    report = _write_report(tmp_path / "skipped.xml", cases)

    counts = evaluate_junit(report)

    assert counts.passed == 14
    assert counts.live == 14
    assert counts.skipped == 1
    with pytest.raises(AcceptanceGateError, match="incomplete"):
        require_strict_success(counts)


def test_strict_gate_rejects_missing_and_renamed_steps(tmp_path: Path) -> None:
    cases = [_case(name) for name in EXPECTED_STEP_NAMES[:-1]]
    cases.append(_case("test_step_15_renamed_sdk_contract"))
    report = _write_report(tmp_path / "renamed.xml", cases)

    counts = evaluate_junit(report)

    assert counts.missing == 1
    assert counts.unexpected == 1
    with pytest.raises(AcceptanceGateError, match="incomplete"):
        require_strict_success(counts)


def test_strict_gate_rejects_xfailed_required_step(tmp_path: Path) -> None:
    cases = [_case(name) for name in EXPECTED_STEP_NAMES]
    cases[0] = _case(EXPECTED_STEP_NAMES[0], '<skipped type="pytest.xfail" message="known defect"/>')
    report = _write_report(tmp_path / "xfailed.xml", cases)

    counts = evaluate_junit(report)

    assert counts.xfailed == 1
    assert counts.live == 14
    with pytest.raises(AcceptanceGateError, match="incomplete"):
        require_strict_success(counts)


def test_strict_gate_rejects_duplicate_result(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path / "duplicate.xml",
        [_case(EXPECTED_STEP_NAMES[0]), _case(EXPECTED_STEP_NAMES[0])],
    )

    with pytest.raises(AcceptanceGateError, match="duplicate"):
        evaluate_junit(report)


def test_strict_gate_rejects_invalid_report(tmp_path: Path) -> None:
    report = tmp_path / "invalid.xml"
    report.write_text("<testsuite>", encoding="utf-8")

    with pytest.raises(AcceptanceGateError, match="missing or invalid"):
        evaluate_junit(report)
