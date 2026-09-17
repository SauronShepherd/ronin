"""Write diffable HTTP qualification evidence from measured samples."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from statistics import median


def percentile(samples_ms: list[float], fraction: float) -> float:
    if not samples_ms or not 0 < fraction <= 1:
        raise ValueError("samples must be non-empty and fraction must be in (0, 1]")
    ordered = sorted(samples_ms)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction + 0.999999) - 1))
    return ordered[index]


def build_artifact(samples: dict[str, list[float]], *, sha: str, measured_at: str) -> dict[str, object]:
    if not sha or len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
        raise ValueError("sha must be a 40-character lowercase Git SHA")
    metrics: dict[str, object] = {}
    for name, values in sorted(samples.items()):
        if not values or any(value < 0 for value in values):
            raise ValueError(f"{name} samples must be non-empty and non-negative")
        duration = sum(values)
        metrics[name] = {
            "sample_count": len(values),
            "p50_ms": round(percentile(values, 0.50), 3),
            "p95_ms": round(percentile(values, 0.95), 3),
            "max_ms": round(max(values), 3),
            "throughput_per_second": round(len(values) / duration, 3) if duration else None,
        }
    return {
        "schema": "ronin.http-performance/v1",
        "source_sha": sha,
        "measured_at": measured_at,
        "environment": {"platform": platform.platform(), "python": platform.python_version()},
        "metrics": metrics,
        "resources": {"cpu": None, "memory_bytes": None, "io_bytes": None},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", type=Path, help="JSON object mapping metric names to seconds")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=Path.cwd(), capture_output=True, text=True, check=True
    ).stdout.strip()
    raw = json.loads(args.samples.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not all(isinstance(values, list) for values in raw.values()):
        raise SystemExit("samples must be a JSON object of arrays")
    artifact = build_artifact(raw, sha=sha, measured_at=datetime.now(UTC).isoformat(timespec="seconds"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
