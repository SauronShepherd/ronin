"""Validate and report the autonomous daily build/test ledger.

The ledger deliberately keeps implementation, family qualification, and release
gates separate. This prevents a green focused test or a historical receipt from
inflating Public v1 progress.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path("docs/product/ronin-daily-progress.json")
FAMILY_STATUSES = {"not_started", "in_progress", "candidate_ready", "qualified", "blocked"}
DAY_STATUSES = {"pending", "in_progress", "pass", "fail", "blocked"}
GATE_STATUSES = {"pending", "pass", "fail", "blocked", "pending-human-review"}
EXPECTED_FAMILY_IDS = [
    "P1",
    "P2",
    "P3",
    "P4",
    "P5",
    "P6",
    "P7",
    "P8",
    "P10",
    "P11",
    "P12",
    "P13",
    "P14",
]


def load_ledger(path: Path = DEFAULT_LEDGER) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("ledger root must be an object")
    return value


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError
    return float(value)


def validate_ledger(ledger: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    scope = ledger.get("scope")
    if not isinstance(scope, dict):
        return ["scope must be an object"]
    family_ids = scope.get("family_ids")
    if family_ids != EXPECTED_FAMILY_IDS:
        errors.append(f"scope.family_ids must be {EXPECTED_FAMILY_IDS!r}")
    if scope.get("families_total") != len(EXPECTED_FAMILY_IDS):
        errors.append("scope.families_total must be 13")
    if "P9" in (family_ids or []):
        errors.append("P9 must not be in the Public v1 denominator")

    policy = ledger.get("operating_policy")
    if not isinstance(policy, dict):
        errors.append("operating_policy must be an object")
    else:
        for key in (
            "main_only",
            "branches_allowed",
            "worktrees_allowed",
            "hosted_workflows_allowed",
        ):
            if key not in policy:
                errors.append(f"operating_policy.{key} is required")
        if policy.get("main_only") is not True:
            errors.append("main_only must remain true")
        if policy.get("branches_allowed") is not False:
            errors.append("branches_allowed must remain false")
        if policy.get("worktrees_allowed") is not False:
            errors.append("worktrees_allowed must remain false")
        if policy.get("hosted_workflows_allowed") is not False:
            errors.append("hosted_workflows_allowed must remain false")

    families = ledger.get("families")
    if not isinstance(families, list):
        errors.append("families must be a list")
        families = []
    seen_family_ids: list[str] = []
    qualified_count = 0
    for family in families:
        if not isinstance(family, dict):
            errors.append("every family must be an object")
            continue
        family_id = family.get("id")
        seen_family_ids.append(family_id)
        status = family.get("qualification")
        if status not in FAMILY_STATUSES:
            errors.append(f"{family_id}: invalid qualification status {status!r}")
        if status == "qualified":
            qualified_count += 1
            if not family.get("receipt"):
                errors.append(f"{family_id}: qualified family needs a receipt")
            if not family.get("candidate_sha"):
                errors.append(f"{family_id}: qualified family needs candidate_sha")
    if seen_family_ids != EXPECTED_FAMILY_IDS:
        errors.append("families must contain the 13 expected IDs exactly once and in order")

    gates = ledger.get("release_gates")
    if not isinstance(gates, list) or len(gates) != 10:
        errors.append("release_gates must contain exactly 10 gates")
        gates = []
    gate_pass_count = 0
    for gate in gates:
        if not isinstance(gate, dict):
            errors.append("every release gate must be an object")
            continue
        status = gate.get("status")
        if status not in GATE_STATUSES:
            errors.append(f"{gate.get('id')}: invalid gate status {status!r}")
        if status == "pass":
            gate_pass_count += 1
            if not gate.get("receipt"):
                errors.append(f"{gate.get('id')}: passed gate needs a receipt")

    days = ledger.get("days")
    if not isinstance(days, list) or len(days) != 39:
        errors.append("days must contain exactly 39 daily entries")
        days = []
    day_ids: list[str] = []
    passed_days = 0
    for day in days:
        if not isinstance(day, dict):
            errors.append("every day must be an object")
            continue
        day_ids.append(day.get("id"))
        if day.get("status") not in DAY_STATUSES:
            errors.append(f"{day.get('id')}: invalid day status {day.get('status')!r}")
        if day.get("status") == "pass":
            passed_days += 1
            if not day.get("evidence"):
                errors.append(f"{day.get('id')}: PASS day needs evidence")
            if not day.get("commit_sha"):
                errors.append(f"{day.get('id')}: PASS day needs commit_sha")
    expected_day_ids = [f"D{index:02d}" for index in range(39)]
    if day_ids != expected_day_ids:
        errors.append("days must contain D00 through D38 in order")

    metrics = ledger.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("metrics must be an object")
    else:
        for key, expected in (
            ("families_qualified", qualified_count),
            ("families_total", 13),
            ("days_passed", passed_days),
            ("days_total", 39),
            ("release_gates_passed", gate_pass_count),
            ("release_gates_total", 10),
        ):
            if metrics.get(key) != expected:
                errors.append(f"metrics.{key} must be {expected!r}, got {metrics.get(key)!r}")
        for count_key, total_key, percent_key in (
            ("families_qualified", "families_total", "families_percent"),
            ("days_passed", "days_total", "days_percent"),
            ("release_gates_passed", "release_gates_total", "release_gates_percent"),
        ):
            try:
                total = _number(metrics[total_key])
                count = _number(metrics[count_key])
                actual = round((count / total) * 100, 2)
                reported = _number(metrics[percent_key])
            except (KeyError, TypeError, ZeroDivisionError):
                errors.append(f"metrics.{percent_key} is not numeric")
            else:
                if reported != actual:
                    errors.append(f"metrics.{percent_key} must be {actual}, got {reported}")
        if metrics.get("implementation_tasks_total") is not None:
            total = metrics.get("implementation_tasks_total")
            verified = metrics.get("implementation_tasks_verified")
            if not isinstance(total, int) or total <= 0:
                errors.append(
                    "implementation_tasks_total must be a positive integer once baselined"
                )
            elif not isinstance(verified, int) or not 0 <= verified <= total:
                errors.append("implementation_tasks_verified must be between zero and total")
            else:
                expected = round((verified / total) * 100, 2)
                if metrics.get("implementation_percent") != expected:
                    errors.append(
                        f"metrics.implementation_percent must be {expected}, "
                        f"got {metrics.get('implementation_percent')!r}"
                    )
        elif metrics.get("implementation_percent") is not None:
            errors.append("implementation_percent must be null before the D01 baseline")

    if (
        qualified_count == len(EXPECTED_FAMILY_IDS)
        and ledger.get("metrics", {}).get("release_status") == "NO-GO"
    ):
        # This is valid while human review is still pending, but it must be
        # explicit rather than silently turning into a GO.
        review = ledger.get("human_review", {})
        if not isinstance(review, dict) or review.get("required_before_final_go") is not True:
            errors.append("a NO-GO after 13/13 needs explicit human review metadata")

    return errors


def render_report(ledger: dict[str, Any]) -> str:
    metrics = ledger["metrics"]
    families = ledger["families"]
    open_families = [family["id"] for family in families if family["qualification"] != "qualified"]
    if metrics["implementation_tasks_total"] is None:
        implementation = "not baselined"
    else:
        implementation = (
            f"{metrics['implementation_tasks_verified']}/"
            f"{metrics['implementation_tasks_total']} "
            f"({metrics['implementation_percent']:.2f}%)"
        )
    return "\n".join(
        [
            f"RONIN daily progress - {ledger['updated_on']}",
            f"Repository: {ledger['repository']['branch']}@{ledger['repository']['base_sha']}",
            f"Release: {metrics['release_status']}",
            "Families: "
            f"{metrics['families_qualified']}/{metrics['families_total']} "
            f"({metrics['families_percent']:.2f}%)",
            "Days: "
            f"{metrics['days_passed']}/{metrics['days_total']} "
            f"({metrics['days_percent']:.2f}%)",
            "Release gates: "
            f"{metrics['release_gates_passed']}/{metrics['release_gates_total']} "
            f"({metrics['release_gates_percent']:.2f}%)",
            f"Implementation tasks: {implementation}",
            "Open families: " + (", ".join(open_families) if open_families else "none"),
            "Policy: main only; no branches; no worktrees; no hosted workflows",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument(
        "--check", action="store_true", help="validate the ledger and fail on inconsistency"
    )
    parser.add_argument(
        "--report", action="store_true", help="print the human-readable progress report"
    )
    args = parser.parse_args(argv)

    try:
        ledger = load_ledger(args.ledger)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load ledger: {exc}")
        return 1

    errors = validate_ledger(ledger)
    if args.check or not args.report:
        if errors:
            for error in errors:
                print(f"ERROR: {error}")
            return 1
        print("OK: daily progress ledger is internally consistent")
    if args.report:
        print(render_report(ledger))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
