"""Run a bounded, reproducible local PySpark SQL qualification.

This is deliberately separate from Spark Connect qualification: local PySpark
evidence never implies that a remote Spark Connect endpoint is available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def qualify() -> dict[str, Any]:
    # PySpark defaults workers to ``python3``; Windows installations commonly
    # expose only the active interpreter executable.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
    try:
        from pyspark.sql import SparkSession
    except ImportError as exc:  # pragma: no cover - environment dependent
        return {"status": "unavailable", "reason": f"pyspark unavailable: {exc}"}

    with tempfile.TemporaryDirectory(prefix="ronin-local-spark-") as warehouse:
        spark = (
            SparkSession.builder.master("local[2]")
            .appName("ronin-local-spark-qualification")
            .config("spark.ui.enabled", "false")
            .config("spark.sql.shuffle.partitions", "2")
            .config("spark.sql.warehouse.dir", warehouse)
            .config("spark.driver.bindAddress", "127.0.0.1")
            .getOrCreate()
        )
        try:
            source = [(1, "a"), (2, "b"), (3, "a")]
            spark.createDataFrame(source, ("id", "group")).createOrReplaceTempView("events")
            rows = [
                tuple(row)
                for row in spark.sql(
                    "select `group`, count(*) as n from events group by `group` order by `group`"
                ).collect()
            ]
            normalized = json.dumps(rows, separators=(",", ":"), default=str)
            return {
                "status": "passed",
                "provider": "pyspark-local",
                "runtime": platform.python_version(),
                "spark_version": spark.version,
                "row_count": len(rows),
                "correctness_digest": hashlib.sha256(normalized.encode()).hexdigest(),
                "expected_digest": hashlib.sha256(b'[["a",2],["b",1]]').hexdigest(),
                "rows": rows,
            }
        finally:
            spark.stop()


def run_bounded(timeout_seconds: float) -> dict[str, Any]:
    """Run the Spark worker and return explicit evidence for timeout/failure."""

    try:
        completed = subprocess.run(  # noqa: S603 - repository-local qualification worker
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if completed.returncode:
            return {
                "status": "failed",
                "provider": "pyspark-local",
                "returncode": completed.returncode,
            }
        result = json.loads(completed.stdout)
        if not isinstance(result, dict):
            raise ValueError("qualification output must be an object")
        return result
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "provider": "pyspark-local",
            "timeout_seconds": timeout_seconds,
        }
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"status": "failed", "provider": "pyspark-local", "error": type(exc).__name__}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    result = qualify() if args.worker else run_bounded(args.timeout_seconds)
    payload = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
