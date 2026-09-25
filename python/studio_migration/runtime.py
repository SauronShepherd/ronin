"""Runtime preflight checks for Spark qualification."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SparkRuntimePreflight:
    driver_python: str
    worker_python: str | None
    compatible: bool
    message: str

    def to_payload(self) -> dict[str, object]:
        return {
            "driver_python": self.driver_python,
            "worker_python": self.worker_python,
            "compatible": self.compatible,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class SparkQualificationEvidence:
    status: str
    preflight: SparkRuntimePreflight
    message: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "ronin.migration.spark-qualification/v1",
            "status": self.status,
            "preflight": self.preflight.to_payload(),
            "message": self.message,
        }


def check_spark_python_runtime() -> SparkRuntimePreflight:
    worker = os.environ.get("PYSPARK_PYTHON") or os.environ.get("PYSPARK_DRIVER_PYTHON")
    driver_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if not worker:
        return SparkRuntimePreflight(
            driver_version, None, False, "PYSPARK_PYTHON or PYSPARK_DRIVER_PYTHON is not configured"
        )
    worker_path = worker.strip()
    if not worker_path:
        return SparkRuntimePreflight(
            driver_version, worker, False, "configured PySpark worker path is empty"
        )
    # The path can be validated by Spark itself; this preflight catches the
    # common Windows Store alias/default-python mismatch before a long job.
    worker_version = os.environ.get("RONIN_PYSPARK_WORKER_VERSION")
    if worker_version is not None and worker_version != driver_version:
        return SparkRuntimePreflight(
            driver_version,
            worker_path,
            False,
            f"driver Python {driver_version} differs from worker {worker_version}",
        )
    return SparkRuntimePreflight(
        driver_version,
        worker_path,
        True,
        "PySpark worker path configured; Spark will validate the executable",
    )


def qualify_spark_runtime(
    smoke_test: Callable[[], object] | None = None,
) -> SparkQualificationEvidence:
    """Run a runtime gate and preserve an explicit evidence record."""
    preflight = check_spark_python_runtime()
    if not preflight.compatible:
        return SparkQualificationEvidence("blocked_by_runtime", preflight, preflight.message)
    if smoke_test is None:
        return SparkQualificationEvidence(
            "review_required", preflight, "runtime preflight passed; no smoke test was supplied"
        )
    try:
        smoke_test()
    except Exception as exc:  # noqa: BLE001 - evidence must preserve runtime failure
        return SparkQualificationEvidence(
            "blocked_by_runtime", preflight, f"smoke test failed: {exc}"
        )
    return SparkQualificationEvidence("passed", preflight, "runtime smoke test passed")


def run_spark_smoke() -> SparkQualificationEvidence:
    """Execute a small native Spark validation and return portable evidence."""
    preflight = check_spark_python_runtime()
    if not preflight.compatible:
        return SparkQualificationEvidence("blocked_by_runtime", preflight, preflight.message)
    spark = None
    try:
        from pyspark.sql import SparkSession

        from .spark_validation import SparkValidationPlan

        spark = (
            SparkSession.builder.master("local[2]").appName("ronin-migration-smoke").getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")
        expected = spark.createDataFrame([(1, "a", 1.0), (2, "b", 2.0)], ["id", "value", "metric"])
        actual = spark.createDataFrame([(1, "a", 1.001), (2, "b", 2.0)], ["id", "value", "metric"])
        namespace: dict[str, object] = {"expected": expected, "actual": actual}
        code = SparkValidationPlan(
            "runtime-smoke", "full", ("schema", "counts", "keyed"), ("id",), (("metric", 0.01),)
        ).render()
        exec(code, namespace)  # noqa: S102 - generated validation plan is sandboxed
        result = namespace["validation_result"]
        return SparkQualificationEvidence(
            "passed", preflight, f"native validation passed: {result}"
        )
    except Exception as exc:  # noqa: BLE001 - runtime evidence must preserve failure
        return SparkQualificationEvidence(
            "blocked_by_runtime", preflight, f"native smoke failed: {exc}"
        )
    finally:
        if spark is not None:
            spark.stop()


__all__ = (
    "SparkQualificationEvidence",
    "SparkRuntimePreflight",
    "check_spark_python_runtime",
    "qualify_spark_runtime",
    "run_spark_smoke",
)
