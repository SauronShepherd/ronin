"""Print a compact, scope-aware summary of Ronin test-run evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from defusedxml import ElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read evidence file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"evidence file {path} must contain a JSON object")
    return value


def _format_seconds(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "unknown"
    return f"{value:.2f}s"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _junit_counts(path: Path) -> dict[str, int]:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError, DefusedXmlException) as exc:
        raise ValueError(f"cannot read JUnit report {path}: {exc}") from exc
    cases = root.findall(".//testcase")
    skipped = sum(case.find("skipped") is not None for case in cases)
    failed = sum(
        case.find("failure") is not None or case.find("error") is not None for case in cases
    )
    return {
        "executed": len(cases),
        "passed": len(cases) - skipped - failed,
        "skipped": skipped,
        "failed": failed,
    }


def _print_pytest(path: Path, junit_path: Path | None = None) -> int:
    evidence = _read_json(path)
    summary = evidence.get("summary")
    timing = evidence.get("timing")
    execution = evidence.get("execution")
    if (
        not isinstance(summary, dict)
        or not isinstance(timing, dict)
        or not isinstance(execution, dict)
    ):
        raise ValueError(f"{path} is missing summary, timing, or execution metadata")
    outcomes = summary.get("outcomes", {})
    if not isinstance(outcomes, dict):
        raise ValueError(f"{path} has invalid outcome counts")
    print("Pytest evidence")
    print(
        "  mode / qualification: "
        f"{execution.get('mode', 'unknown')} / {execution.get('qualification_mode', 'unknown')}"
    )
    print(
        "  source / clean: "
        f"{execution.get('source_commit', 'unknown')} / "
        f"{execution.get('worktree_clean', 'unknown')}"
    )
    print(f"  selection: {execution.get('selection', 'unknown')}")
    print(
        "  service / coverage: "
        f"{execution.get('service_profile', 'unknown')} / "
        f"{execution.get('coverage_enabled', 'unknown')}"
    )
    print(
        "  selected / executed / deselected: "
        f"{summary.get('selected', 'unknown')} / {summary.get('executed', 'unknown')} / "
        f"{summary.get('filtered_out', 'unknown')}"
    )
    print(
        "  passed / skipped / failed / xfailed / xpassed / unknown: "
        + " / ".join(
            str(outcomes.get(key, 0))
            for key in ("passed", "skipped", "failed", "xfailed", "xpassed", "unknown")
        )
    )
    print(
        "  pytest body / test phases / collection: "
        f"{_format_seconds(timing.get('pytest_session_body_seconds'))} / "
        f"{_format_seconds(timing.get('test_phase_seconds'))} / "
        f"{_format_seconds(timing.get('startup_and_collection_seconds'))}"
    )
    exit_status = int(evidence.get("exit_status", 1))
    if junit_path is not None:
        junit = _junit_counts(junit_path)
        timing_counts = {
            "executed": summary.get("executed"),
            "passed": outcomes.get("passed", 0),
            "skipped": outcomes.get("skipped", 0),
            "failed": outcomes.get("failed", 0),
        }
        matches = timing_counts == junit
        print(f"  JUnit reconciliation: {'MATCH' if matches else 'MISMATCH'}")
        print(f"    timing JSON: {timing_counts}")
        print(f"    JUnit XML:   {junit}")
        if not matches:
            exit_status = 1
    slowest = evidence.get("slowest_tests", [])
    if isinstance(slowest, list) and slowest:
        print("  slowest cases:")
        for item in slowest[:5]:
            if isinstance(item, dict):
                nodeid = item.get("nodeid", "unknown")
                outcome = item.get("outcome", "unknown")
                duration = _format_seconds(item.get("duration_seconds"))
                print(f"    {duration} {nodeid} [{outcome}]")
    collection_skips = evidence.get("collection_skips", [])
    if isinstance(collection_skips, list) and collection_skips:
        print(f"  collection skips ({len(collection_skips)}):")
        for item in collection_skips[:10]:
            if isinstance(item, dict):
                reason = item.get("skip_reason", item.get("reason", "unknown reason"))
                print(f"    {item.get('nodeid', 'unknown')}: {reason}")
        if len(collection_skips) > 10:
            print(f"    … {len(collection_skips) - 10} more; see the JSON receipt")
    tests = evidence.get("tests", [])
    if isinstance(tests, list):
        failures = [
            item
            for item in tests
            if isinstance(item, dict) and item.get("outcome") in {"failed", "xpassed"}
        ]
        if failures:
            exit_status = 1
            print(f"  failed/XPASS node IDs ({len(failures)}):")
            for item in failures[:20]:
                print(f"    {item.get('nodeid', 'unknown')} [{item.get('outcome')}]")
            if len(failures) > 20:
                print(f"    … {len(failures) - 20} more; see the JSON receipt")
    return exit_status


def _print_runner(path: Path) -> int:
    evidence = _read_json(path)
    print("Runner evidence")
    if "testKind" in evidence:
        playwright = _mapping(evidence.get("playwright"))
        traffic = _mapping(evidence.get("apiTraffic"))
        services = _mapping(evidence.get("realServices"))
        logs = _mapping(evidence.get("applicationLogLevels"))
        live_phases = _mapping(evidence.get("phaseDurationsSeconds"))
        print(
            "  candidate / worktree: "
            f"{evidence.get('candidate', 'unknown')} / {evidence.get('worktree', 'unknown')}"
        )
        print(
            "  status / journey: "
            f"{evidence.get('status', 'unknown')} / {evidence.get('testKind', 'unknown')}"
        )
        print(
            "  browser cases passed / total / skipped / failed: "
            f"{playwright.get('passed', 'unknown')} / {playwright.get('executed', 'unknown')} / "
            f"{playwright.get('skipped', 'unknown')} / {playwright.get('failed', 'unknown')}"
        )
        print(
            "  API events / correlated logs / uncorrelated: "
            f"{traffic.get('events', 'unknown')} / "
            f"{traffic.get('correlatedHttpLogs', 'unknown')} / "
            f"{traffic.get('uncorrelated', 'unknown')}; outcomes={traffic.get('outcomes', {})}"
        )
        print(
            "  services postgres / kafka / Ronin API / worker image: "
            f"{services.get('postgres', 'unknown')} / {services.get('kafka', 'unknown')} / "
            f"{services.get('roninApi', 'unknown')} / {services.get('workerImage', 'none')}"
        )
        print(f"  application log levels: {logs}")
        print(
            "  route audit / routes: "
            f"{_mapping(evidence.get('routeCoverage')).get('audited', 'unknown')} / "
            f"{_mapping(evidence.get('routeCoverage')).get('activeRoutes', 'unknown')}"
        )
        print(f"  phases: {live_phases}")
        print(f"  elapsed: {_format_seconds(evidence.get('durationSeconds'))}")
        print(f"  evidence: {evidence.get('evidenceDirectory', path.parent)}")
        browser_counts_valid = (
            isinstance(playwright.get("executed"), int)
            and isinstance(playwright.get("passed"), int)
            and isinstance(playwright.get("skipped"), int)
            and isinstance(playwright.get("failed"), int)
            and playwright["executed"]
            == playwright["passed"] + playwright["skipped"] + playwright["failed"]
        )
        traffic_counts_valid = (
            isinstance(traffic.get("events"), int)
            and isinstance(traffic.get("correlatedHttpLogs"), int)
            and isinstance(traffic.get("uncorrelated"), int)
            and traffic["events"] == traffic["correlatedHttpLogs"] + traffic["uncorrelated"]
        )
        if not browser_counts_valid:
            print("  evidence consistency: INVALID browser case totals")
        if not traffic_counts_valid:
            print("  evidence consistency: INVALID API/log correlation totals")
        if traffic_counts_valid and traffic["uncorrelated"]:
            print("  evidence consistency: API events lack correlated HTTP logs")
        return (
            1
            if (
                evidence.get("status") != "passed"
                or not browser_counts_valid
                or not traffic_counts_valid
                or bool(traffic.get("uncorrelated"))
            )
            else 0
        )
    for label, key in (
        ("candidate", "source_commit"),
        ("worktree clean", "worktree_clean"),
        ("qualification", "qualification_mode"),
        ("selection", "selection"),
        ("service profile", "service_profile"),
        ("coverage", "coverage_enabled"),
    ):
        if key in evidence:
            print(f"  {label}: {evidence[key]}")
    phase_keys = (
        ("Python environment", "python_environment_seconds"),
        ("service startup", "postgres_startup_seconds"),
        ("pytest", "pytest_wall_seconds"),
        ("cleanup", "cleanup_seconds"),
        ("total", "total_wall_seconds"),
    )
    runner_phases = [(label, evidence.get(key)) for label, key in phase_keys if key in evidence]
    if runner_phases:
        print(
            "  phases: "
            + ", ".join(f"{label}={_format_seconds(value)}" for label, value in runner_phases)
        )
    if "cleanup_status" in evidence:
        print(f"  cleanup status: {evidence['cleanup_status']}")
    if "status" in evidence:
        print(f"  status: {evidence['status']}")
    if evidence.get("failure"):
        print(f"  failure: {evidence['failure']}")
    postgres_pytest_runner = "pytest_wall_seconds" in evidence
    incomplete_pytest = postgres_pytest_runner and (
        not isinstance(evidence.get("pytest_wall_seconds"), (int, float))
        or evidence.get("status") != "passed"
        or evidence.get("test_exit_code") != 0
    )
    if incomplete_pytest:
        print("  evidence consistency: pytest did not complete successfully")
    return (
        1
        if (
            evidence.get("cleanup_status") == "failed"
            or evidence.get("status") == "failed"
            or incomplete_pytest
        )
        else 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "evidence",
        type=Path,
        help="pytest-timings.json, runner-timings.json, or qualification-summary.json",
    )
    parser.add_argument(
        "--junit",
        type=Path,
        help="optional JUnit XML to reconcile with pytest timing counts",
    )
    args = parser.parse_args()
    try:
        name = args.evidence.name
        if name == "pytest-timings.json":
            return _print_pytest(args.evidence, args.junit)
        if args.junit is not None:
            parser.error("--junit is supported only with pytest-timings.json")
        if name in {"runner-timings.json", "qualification-summary.json"}:
            return _print_runner(args.evidence)
        parser.error(
            "expected pytest-timings.json, runner-timings.json, or qualification-summary.json"
        )
    except ValueError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
