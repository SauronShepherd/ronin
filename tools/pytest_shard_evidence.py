"""Compare full-suite and sharded pytest timing evidence without running tests."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from math import isfinite
from pathlib import Path
from statistics import median
from typing import Any

SCHEMA = "ronin.pytest-timing-evidence/v2"


def _load_report(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read timing evidence {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError(f"unsupported timing evidence schema in {path}")
    value["_path"] = str(path)
    return value


def _ci_value(report: dict[str, Any], key: str) -> str:
    ci = report.get("ci")
    value = ci.get(key) if isinstance(ci, dict) else None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{report['_path']} is missing CI metadata {key!r}")
    return value


def _nodeids(report: dict[str, Any], key: str) -> list[str]:
    values = report.get(key)
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f"{report['_path']} has invalid {key}")
    return values


def _duration(report: dict[str, Any]) -> float:
    timing = report.get("timing")
    session = timing.get("session_wall_seconds") if isinstance(timing, dict) else None
    session_body = (
        timing.get("pytest_session_body_seconds") if isinstance(timing, dict) else None
    )
    startup = (
        timing.get("startup_and_collection_seconds") if isinstance(timing, dict) else None
    )
    installation = timing.get("installation_seconds") if isinstance(timing, dict) else None
    if (
        isinstance(session, bool)
        or not isinstance(session, (int, float))
        or session < 0
        or isinstance(session_body, bool)
        or not isinstance(session_body, (int, float))
        or session_body < 0
        or isinstance(startup, bool)
        or not isinstance(startup, (int, float))
        or startup < 0
        or isinstance(installation, bool)
        or not isinstance(installation, (int, float))
        or installation < 0
    ):
        raise ValueError(f"{report['_path']} has invalid installation/session timing")
    try:
        session_seconds = float(session)
        session_body_seconds = float(session_body)
        startup_seconds = float(startup)
        installation_seconds = float(installation)
    except OverflowError as exc:
        raise ValueError(f"{report['_path']} has non-finite installation/session timing") from exc
    if not all(
        isfinite(value)
        for value in (
            session_seconds,
            session_body_seconds,
            startup_seconds,
            installation_seconds,
        )
    ):
        raise ValueError(f"{report['_path']} has non-finite installation/session timing")
    if session_body_seconds > session_seconds or startup_seconds > session_seconds:
        raise ValueError(f"{report['_path']} has inconsistent session timing phases")
    total = installation_seconds + session_seconds
    if not isfinite(total):
        raise ValueError(f"{report['_path']} has non-finite installation/session timing")
    return total


def _require_clean_run(reports: list[dict[str, Any]]) -> None:
    for report in reports:
        exit_status = report.get("exit_status")
        if not isinstance(exit_status, int) or isinstance(exit_status, bool) or exit_status != 0:
            raise ValueError(f"test run failed: {report['_path']}")
        tests = report.get("tests")
        if not isinstance(tests, list):
            raise ValueError(f"{report['_path']} has invalid per-test evidence")
        for item in tests:
            outcome = item.get("outcome") if isinstance(item, dict) else None
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("nodeid"), str)
                or not item["nodeid"]
                or not isinstance(item.get("flaky"), bool)
                or not isinstance(item.get("attempts"), int)
                or isinstance(item.get("attempts"), bool)
                or item["attempts"] < 1
                or not isinstance(item.get("failed_phase_count"), int)
                or isinstance(item.get("failed_phase_count"), bool)
                or item["failed_phase_count"] < 0
            ):
                raise ValueError(f"{report['_path']} has an invalid test record")
            if not isinstance(outcome, str) or outcome not in {
                "passed",
                "skipped",
                "xfailed",
                "xpassed",
            }:
                raise ValueError(f"{report['_path']} has an unsupported test outcome")
            phases = item.get("phases")
            if not isinstance(phases, list) or not phases:
                raise ValueError(f"{report['_path']} has missing phase evidence for {item['nodeid']}")
            phase_durations: list[float] = []
            setup_count = 0
            failed_phase_count = 0
            for phase in phases:
                phase_name = phase.get("phase") if isinstance(phase, dict) else None
                phase_outcome = phase.get("outcome") if isinstance(phase, dict) else None
                if (
                    not isinstance(phase, dict)
                    or not isinstance(phase_name, str)
                    or phase_name not in {"setup", "call", "teardown"}
                    or not isinstance(phase_outcome, str)
                    or phase_outcome not in {"passed", "failed", "skipped"}
                ):
                    raise ValueError(f"{report['_path']} has invalid phase evidence for {item['nodeid']}")
                duration = phase.get("duration_seconds")
                if (
                    isinstance(duration, bool)
                    or not isinstance(duration, (int, float))
                    or duration < 0
                ):
                    raise ValueError(f"{report['_path']} has invalid phase duration for {item['nodeid']}")
                try:
                    duration_seconds = float(duration)
                except OverflowError as exc:
                    raise ValueError(
                        f"{report['_path']} has invalid phase duration for {item['nodeid']}"
                    ) from exc
                if not isfinite(duration_seconds):
                    raise ValueError(f"{report['_path']} has non-finite phase duration for {item['nodeid']}")
                phase_durations.append(duration_seconds)
                setup_count += phase_name == "setup"
                failed_phase_count += phase_outcome == "failed"
            duration = item.get("duration_seconds")
            if (
                isinstance(duration, bool)
                or not isinstance(duration, (int, float))
                or duration < 0
            ):
                raise ValueError(f"{report['_path']} has invalid test duration for {item['nodeid']}")
            try:
                duration_seconds = float(duration)
            except OverflowError as exc:
                raise ValueError(
                    f"{report['_path']} has invalid test duration for {item['nodeid']}"
                ) from exc
            tolerance = 1e-9 * max(1.0, duration_seconds)
            if (
                not isfinite(duration_seconds)
                or setup_count != item["attempts"]
                or failed_phase_count != item["failed_phase_count"]
                or abs(sum(phase_durations) - duration_seconds) > tolerance
            ):
                raise ValueError(f"{report['_path']} has inconsistent test phase totals for {item['nodeid']}")
            expected_flaky = (
                failed_phase_count > 0
                and setup_count > 1
                and outcome != "failed"
            )
            if item["flaky"] != expected_flaky:
                raise ValueError(f"{report['_path']} has inconsistent flaky status for {item['nodeid']}")
            if item.get("flaky") is True or outcome in {"failed", "xpassed"}:
                raise ValueError(f"flaky or failed test {item['nodeid']} in {report['_path']}")


def _outcomes(report: dict[str, Any]) -> dict[str, str]:
    tests = report.get("tests")
    if not isinstance(tests, list):
        raise ValueError(f"{report['_path']} has invalid per-test evidence")
    results: dict[str, str] = {}
    for item in tests:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("nodeid"), str)
            or not isinstance(item.get("outcome"), str)
        ):
            raise ValueError(f"{report['_path']} has an invalid test outcome")
        nodeid = item["nodeid"]
        if nodeid in results:
            raise ValueError(f"{report['_path']} has duplicate test record {nodeid}")
        results[nodeid] = item["outcome"]
    return results


def analyze_reports(
    baseline_paths: list[Path], shard_paths: list[Path], *, minimum_runs: int = 3
) -> dict[str, object]:
    """Require complete, unique shard coverage and compare repeated wall times."""
    if minimum_runs < 1:
        raise ValueError("minimum_runs must be positive")
    baseline_reports = [_load_report(path) for path in baseline_paths]
    shard_reports = [_load_report(path) for path in shard_paths]
    baseline_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    shard_groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for report in baseline_reports:
        key = (
            _ci_value(report, "commit"),
            _ci_value(report, "python_version"),
            _ci_value(report, "run_id"),
            _ci_value(report, "run_attempt"),
        )
        if _ci_value(report, "shard") != "full":
            raise ValueError(f"baseline report is not a full-suite run: {report['_path']}")
        baseline_groups[key[:2]].append(report)
    for report in shard_reports:
        key = (
            _ci_value(report, "commit"),
            _ci_value(report, "python_version"),
            _ci_value(report, "run_id"),
            _ci_value(report, "run_attempt"),
        )
        if _ci_value(report, "shard") == "full":
            raise ValueError(f"shard report is marked full-suite: {report['_path']}")
        shard_groups[key].append(report)

    summaries: list[dict[str, object]] = []
    baseline_version_keys = set(baseline_groups)
    shard_version_keys = {(key[0], key[1]) for key in shard_groups}
    if baseline_version_keys != shard_version_keys:
        raise ValueError("baseline and shard reports contain different commit/Python groups")
    comparable_keys = sorted(baseline_version_keys)
    for commit, python_version in comparable_keys:
        baselines = baseline_groups[(commit, python_version)]
        groups = [
            reports
            for key, reports in shard_groups.items()
            if key[:2] == (commit, python_version)
        ]
        if len(baselines) < minimum_runs or len(groups) < minimum_runs:
            raise ValueError(
                f"{commit} Python {python_version} needs at least {minimum_runs} full and shard runs"
            )
        baseline_run_keys = [
            (_ci_value(report, "run_id"), _ci_value(report, "run_attempt"))
            for report in baselines
        ]
        if len(baseline_run_keys) != len(set(baseline_run_keys)):
            raise ValueError("full-suite timing reports contain duplicate run attempts")
        _require_clean_run(baselines)
        expected_nodeids = _nodeids(baselines[0], "collected_nodeids")
        if len(expected_nodeids) != len(set(expected_nodeids)):
            raise ValueError("full-suite baseline contains duplicate collected node IDs")
        expected_outcomes = _outcomes(baselines[0])
        if set(expected_outcomes) != set(expected_nodeids):
            raise ValueError("full-suite baseline is missing per-test outcomes")
        for report in baselines:
            collected_nodeids = _nodeids(report, "collected_nodeids")
            if (
                len(collected_nodeids) != len(set(collected_nodeids))
                or set(collected_nodeids) != set(expected_nodeids)
            ):
                raise ValueError("full-suite runs collected different node ID sets")
            if Counter(_nodeids(report, "executed_nodeids")) != Counter(expected_nodeids):
                raise ValueError("full-suite run did not execute every node ID exactly once")
            if _outcomes(report) != expected_outcomes:
                raise ValueError("test outcomes changed between full-suite runs")

        sharded_wall_times: list[float] = []
        for reports in groups:
            _require_clean_run(reports)
            shard_names = [_ci_value(report, "shard") for report in reports]
            if len(shard_names) != 2 or len(shard_names) != len(set(shard_names)):
                raise ValueError("each sharded run needs exactly two uniquely named shards")
            collected = [nodeid for report in reports for nodeid in _nodeids(report, "collected_nodeids")]
            executed = [nodeid for report in reports for nodeid in _nodeids(report, "executed_nodeids")]
            shard_outcomes: dict[str, str] = {}
            for report in reports:
                for nodeid, outcome in _outcomes(report).items():
                    if nodeid in shard_outcomes:
                        raise ValueError(f"test outcome appears in multiple shards: {nodeid}")
                    shard_outcomes[nodeid] = outcome
            if len(collected) != len(set(collected)):
                raise ValueError("node IDs were collected by more than one shard")
            if Counter(collected) != Counter(expected_nodeids):
                raise ValueError("shards do not cover the full-suite node ID set exactly once")
            if Counter(executed) != Counter(expected_nodeids):
                raise ValueError("shards did not execute every node ID exactly once")
            if shard_outcomes != expected_outcomes:
                raise ValueError("test outcomes differ between full-suite and shard runs")
            sharded_wall_times.append(max(_duration(report) for report in reports))

        full_median = median(_duration(report) for report in baselines)
        shard_median = median(sharded_wall_times)
        summaries.append(
            {
                "commit": commit,
                "python_version": python_version,
                "full_runs": len(baselines),
                "sharded_runs": len(groups),
                "node_ids": len(expected_nodeids),
                "median_full_seconds": full_median,
                "median_sharded_wall_seconds": shard_median,
                "median_savings_seconds": full_median - shard_median,
                "median_savings_percent": (
                    100 * (full_median - shard_median) / full_median if full_median else 0.0
                ),
                "coverage_thresholds": "not assessed by timing evidence",
            }
        )
    if not summaries:
        raise ValueError("no matching commit/Python groups found in the supplied reports")
    return {"schema": "ronin.pytest-shard-analysis/v1", "groups": summaries}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="append", type=Path, required=True)
    parser.add_argument("--shard", action="append", type=Path, required=True)
    parser.add_argument("--minimum-runs", type=int, default=3)
    args = parser.parse_args()
    try:
        result = analyze_reports(args.baseline, args.shard, minimum_runs=args.minimum_runs)
    except ValueError as exc:
        parser.error(str(exc))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
