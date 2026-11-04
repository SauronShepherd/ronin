"""Write exact pytest node IDs for the slowest cases in one timing report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from math import isfinite
from pathlib import Path
from typing import Any


def _load_report(report_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read pytest timing report {report_path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") not in {
        "ronin.pytest-timing-evidence/v3",
        "ronin.pytest-timing-evidence/v4",
    }:
        raise ValueError(f"unsupported pytest timing report schema in {report_path}")
    return payload


def _load_tests(report_path: Path) -> list[dict[str, Any]]:
    payload = _load_report(report_path)
    tests = payload.get("tests")
    if not isinstance(tests, list):
        raise ValueError(f"pytest timing report {report_path} has no valid tests list")

    valid_tests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in tests:
        if not isinstance(item, dict):
            raise ValueError(f"pytest timing report {report_path} contains an invalid test record")
        nodeid = item.get("nodeid")
        duration = item.get("duration_seconds")
        outcome = item.get("outcome")
        if not isinstance(nodeid, str) or not nodeid or nodeid in seen:
            raise ValueError(
                f"pytest timing report {report_path} contains an invalid or duplicate node ID"
            )
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError(
                f"pytest timing report {report_path} contains an invalid test duration"
            )
        try:
            duration_seconds = float(duration)
        except OverflowError as exc:
            raise ValueError(
                f"pytest timing report {report_path} contains an invalid test duration"
            ) from exc
        if not isfinite(duration_seconds) or duration_seconds < 0:
            raise ValueError(
                f"pytest timing report {report_path} contains an invalid test duration"
            )
        if not isinstance(outcome, str) or outcome not in {
            "passed",
            "failed",
            "skipped",
            "xfailed",
            "xpassed",
            "unknown",
        }:
            raise ValueError(f"pytest timing report {report_path} contains an invalid test outcome")
        seen.add(nodeid)
        valid_tests.append(item)
    return valid_tests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="pytest-timings.json from a prior diagnostic run")
    parser.add_argument("output", type=Path, help="file to receive exact pytest node IDs")
    parser.add_argument("--count", type=int, default=20, help="number of slow tests to select")
    parser.add_argument(
        "--run",
        action="store_true",
        help=(
            "run the selected node IDs now with the current Python interpreter "
            "and forward pytest output"
        ),
    )
    parser.add_argument(
        "--checkout",
        type=Path,
        default=Path.cwd(),
        help="repository root from which to run the selected tests (default: current directory)",
    )
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    try:
        timing_report = _load_report(args.report)
        tests = _load_tests(args.report)
        if not tests:
            raise ValueError(f"pytest timing report {args.report} contains no executed tests")
        slowest = sorted(
            (item for item in tests if item["outcome"] != "skipped"),
            key=lambda item: (-float(item["duration_seconds"]), item["nodeid"]),
        )[: args.count]
        if not slowest:
            raise ValueError(f"pytest timing report {args.report} contains no non-skipped tests")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            "\n".join(item["nodeid"] for item in slowest) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        f"Wrote {len(slowest)} exact pytest node IDs to {args.output}; "
        "this diagnostic subset is not full-suite evidence."
    )
    if args.run:
        execution = timing_report.get("execution")
        if (
            not isinstance(execution, dict)
            or execution.get("mode") != "local-only-diagnostic"
            or execution.get("service_profile") != "none"
            or execution.get("coverage_enabled") != "disabled"
        ):
            parser.error(
                "--run is restricted to timings recorded by a local-only, no-service, "
                "no-coverage run; "
                "use the matching family runner for service-backed tests"
            )
        try:
            # Validated node IDs are argv items; no shell or command string is used.
            completed = subprocess.run(  # noqa: S603
                [sys.executable, "-m", "pytest", "-q", *[item["nodeid"] for item in slowest]],
                cwd=args.checkout,
                check=False,
            )
        except OSError as exc:
            parser.error(f"could not start pytest in checkout {args.checkout}: {exc}")
        return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
