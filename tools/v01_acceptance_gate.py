"""Fail-closed qualification for the frozen Ronin v0.1 acceptance journey."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree

EXPECTED_STEP_NAMES: tuple[str, ...] = tuple(
    f"test_step_{index:02d}_{suffix}"
    for index, suffix in enumerate(
        (
            "compose_reaches_healthy_within_60s",
            "doctor_reports_all_checks_passing",
            "validate_accepts_demo_project",
            "plan_prints_order_and_levels",
            "submit_returns_queued_job",
            "worker_claims_and_executes_first_cells",
            "kill_worker_orphans_lease",
            "restart_waits_for_lease_expiry",
            "reclaimed_attempt_resumes_at_cell_four",
            "job_reaches_succeeded",
            "events_contiguous_across_attempts_with_terminal",
            "evidence_present_for_all_six_cells",
            "replayed_idempotency_key_returns_same_job",
            "cancel_removes_container",
            "sdk_round_trip_matches_cli",
        ),
        start=1,
    )
)


class AcceptanceGateError(ValueError):
    """Raised when strict v0.1 acceptance evidence is incomplete or invalid."""


@dataclass(frozen=True, slots=True)
class AcceptanceCounts:
    """Machine-readable summary of the frozen acceptance-step outcomes."""

    live: int
    passed: int
    skipped: int
    xfailed: int
    failed: int
    errors: int
    missing: int
    unexpected: int

    @property
    def total_expected(self) -> int:
        return len(EXPECTED_STEP_NAMES)

    @property
    def is_strict_success(self) -> bool:
        return self.passed == self.total_expected and all(
            value == 0
            for value in (
                self.skipped,
                self.xfailed,
                self.failed,
                self.errors,
                self.missing,
                self.unexpected,
            )
        )

    def to_evidence(self) -> dict[str, int | bool]:
        return {
            **asdict(self),
            "total_expected": self.total_expected,
            "strict_success": self.is_strict_success,
        }


def evaluate_junit(report_path: Path) -> AcceptanceCounts:
    """Evaluate pytest JUnit XML against the exact frozen v0.1 step manifest."""
    try:
        root = ElementTree.parse(report_path).getroot()
    except (ElementTree.ParseError, OSError) as exc:
        raise AcceptanceGateError("v0.1 acceptance report is missing or invalid") from exc

    outcomes: dict[str, str] = {}
    unexpected = 0
    expected = set(EXPECTED_STEP_NAMES)
    for testcase in root.iter("testcase"):
        name = testcase.attrib.get("name", "")
        if not name.startswith("test_step_"):
            continue
        if name not in expected:
            unexpected += 1
            continue
        if name in outcomes:
            raise AcceptanceGateError(f"duplicate acceptance result for {name}")
        if testcase.find("failure") is not None:
            outcomes[name] = "failed"
        elif testcase.find("error") is not None:
            outcomes[name] = "errors"
        else:
            skipped = testcase.find("skipped")
            if skipped is None:
                outcomes[name] = "passed"
            elif skipped.attrib.get("type") == "pytest.xfail":
                outcomes[name] = "xfailed"
            else:
                outcomes[name] = "skipped"

    missing = len(expected - outcomes.keys())
    passed = sum(outcome == "passed" for outcome in outcomes.values())
    skipped_count = sum(outcome == "skipped" for outcome in outcomes.values())
    xfailed = sum(outcome == "xfailed" for outcome in outcomes.values())
    failed = sum(outcome == "failed" for outcome in outcomes.values())
    errors = sum(outcome == "errors" for outcome in outcomes.values())
    live = passed + failed + errors
    return AcceptanceCounts(
        live=live,
        passed=passed,
        skipped=skipped_count,
        xfailed=xfailed,
        failed=failed,
        errors=errors,
        missing=missing,
        unexpected=unexpected,
    )


def require_strict_success(counts: AcceptanceCounts) -> None:
    """Reject any non-passing, missing, renamed, skipped, or xfailed required step."""
    if not counts.is_strict_success:
        raise AcceptanceGateError("strict v0.1 acceptance qualification is incomplete")


def _format_counts(counts: AcceptanceCounts) -> str:
    return (
        "v0.1 acceptance: "
        f"live={counts.live} passed={counts.passed} skipped={counts.skipped} "
        f"xfailed={counts.xfailed} failed={counts.failed} errors={counts.errors} "
        f"missing={counts.missing} unexpected={counts.unexpected} "
        f"total={counts.total_expected} strict_success={str(counts.is_strict_success).lower()}"
    )


def _write_evidence(path: Path, counts: AcceptanceCounts) -> None:
    path.write_text(
        json.dumps(counts.to_evidence(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_report", type=Path)
    parser.add_argument("--evidence-json", type=Path)
    parser.add_argument("--progress-only", action="store_true")
    args = parser.parse_args()
    try:
        counts = evaluate_junit(args.junit_report)
        print(_format_counts(counts))
        if args.evidence_json is not None:
            _write_evidence(args.evidence_json, counts)
        if not args.progress_only:
            require_strict_success(counts)
    except AcceptanceGateError as exc:
        print(f"v0.1 acceptance gate failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
