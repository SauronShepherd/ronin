"""Deterministic benchmark and safe-promotion contracts."""

from __future__ import annotations

import hashlib
import platform
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass

from studio_core.canonical_json import encode as encode_canonical_json


@dataclass(frozen=True, slots=True)
class RuntimeBuildFingerprint:
    """Exact, non-secret identity required for cross-run comparisons."""

    engine: str
    version: str
    build_id: str
    image_digest: str = ""

    def __post_init__(self) -> None:
        for value, label in ((self.engine, "engine"), (self.version, "version"), (self.build_id, "build_id")):
            if not value or value != value.strip():
                raise ValueError(f"runtime fingerprint {label} must be non-empty and trimmed")

    def to_payload(self) -> dict[str, str]:
        payload = {"engine": self.engine, "version": self.version, "build_id": self.build_id}
        if self.image_digest:
            payload["image_digest"] = self.image_digest
        return payload

    @property
    def digest(self) -> str:
        return hashlib.sha256(encode_canonical_json(self.to_payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    name: str
    warmup_runs: int
    measured_runs: int
    durations_ms: tuple[float, ...]
    median_ms: float
    fingerprint: str
    runtime_build_fingerprint: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "warmup_runs": self.warmup_runs,
            "measured_runs": self.measured_runs,
            "durations_ms": list(self.durations_ms),
            "median_ms": self.median_ms,
            "fingerprint": self.fingerprint,
            **({"runtime_build_fingerprint": self.runtime_build_fingerprint} if self.runtime_build_fingerprint else {}),
        }


def benchmark(
    operation: Callable[[], object],
    *,
    name: str,
    warmup_runs: int = 1,
    measured_runs: int = 5,
    fingerprint_inputs: dict[str, object] | None = None,
    runtime_build_fingerprint: RuntimeBuildFingerprint | None = None,
) -> BenchmarkResult:
    if not name or name != name.strip():
        raise ValueError("benchmark name must be non-empty and trimmed")
    if warmup_runs < 0 or measured_runs < 1:
        raise ValueError("benchmark runs are invalid")
    for _ in range(warmup_runs):
        operation()
    durations: list[float] = []
    for _ in range(measured_runs):
        start = time.perf_counter_ns()
        operation()
        durations.append((time.perf_counter_ns() - start) / 1_000_000)
    inputs = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        **(fingerprint_inputs or {}),
    }
    if runtime_build_fingerprint is not None:
        inputs["runtime_build_fingerprint"] = runtime_build_fingerprint.to_payload()
    fingerprint = hashlib.sha256(encode_canonical_json(inputs)).hexdigest()
    return BenchmarkResult(
        name,
        warmup_runs,
        measured_runs,
        tuple(durations),
        statistics.median(durations),
        fingerprint,
        runtime_build_fingerprint.digest if runtime_build_fingerprint is not None else None,
    )


@dataclass(frozen=True, slots=True)
class OptimizationDecision:
    candidate_id: str
    promoted: bool
    reason: str
    baseline_median_ms: float
    candidate_median_ms: float

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "promoted": self.promoted,
            "reason": self.reason,
            "baseline_median_ms": self.baseline_median_ms,
            "candidate_median_ms": self.candidate_median_ms,
        }


def promotion_evidence(
    decision: OptimizationDecision,
    *,
    baseline: BenchmarkResult,
    candidate: BenchmarkResult,
    semantic_passed: bool,
    quality_passed: bool,
) -> dict[str, object]:
    """Build the canonical payload suitable for a Migration Run evidence cell."""
    return {
        "schema": "ronin.migration.optimization-evidence/v1",
        "decision": decision.to_payload(),
        "baseline": baseline.to_payload(),
        "candidate": candidate.to_payload(),
        "semantic_passed": semantic_passed,
        "quality_passed": quality_passed,
    }


def decide_promotion(
    candidate_id: str,
    *,
    baseline: BenchmarkResult,
    candidate: BenchmarkResult,
    semantic_passed: bool,
    quality_passed: bool,
    max_regression_ratio: float = 0.05,
) -> OptimizationDecision:
    if not candidate_id or candidate_id != candidate_id.strip():
        raise ValueError("candidate_id must be non-empty and trimmed")
    if max_regression_ratio < 0:
        raise ValueError("max_regression_ratio must be non-negative")
    if baseline.runtime_build_fingerprint != candidate.runtime_build_fingerprint:
        return OptimizationDecision(
            candidate_id,
            False,
            "runtime build fingerprints are incompatible",
            baseline.median_ms,
            candidate.median_ms,
        )
    if baseline.fingerprint != candidate.fingerprint:
        return OptimizationDecision(
            candidate_id,
            False,
            "benchmark fingerprints are incompatible",
            baseline.median_ms,
            candidate.median_ms,
        )
    if not semantic_passed:
        return OptimizationDecision(
            candidate_id,
            False,
            "semantic validation failed",
            baseline.median_ms,
            candidate.median_ms,
        )
    if not quality_passed:
        return OptimizationDecision(
            candidate_id, False, "quality gates failed", baseline.median_ms, candidate.median_ms
        )
    # Timer noise dominates very small local benchmarks. Keep the ratio gate
    # for meaningful workloads, but provide a small absolute floor so two
    # equivalent sub-millisecond candidates are not rejected by scheduler jitter.
    allowed = max(baseline.median_ms * (1.0 + max_regression_ratio), 0.1)
    promoted = candidate.median_ms <= allowed
    reason = (
        "candidate is semantically valid without blocking regression"
        if promoted
        else "performance regression exceeds threshold"
    )
    return OptimizationDecision(
        candidate_id, promoted, reason, baseline.median_ms, candidate.median_ms
    )


__all__ = (
    "BenchmarkResult",
    "RuntimeBuildFingerprint",
    "OptimizationDecision",
    "benchmark",
    "decide_promotion",
    "promotion_evidence",
)
