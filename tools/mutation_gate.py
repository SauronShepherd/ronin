"""Validate exported mutmut CI/CD statistics against Ronin's mutation policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final

MUTATION_THRESHOLD: Final[float] = 90.0
_FAILURE_KEYS: Final[tuple[str, ...]] = (
    "survived",
    "no_tests",
    "suspicious",
    "timeout",
    "check_was_interrupted_by_user",
    "segfault",
)


def mutation_score(stats: dict[str, int]) -> float:
    total = stats["total"]
    skipped = stats["skipped"]
    tested = total - skipped
    if tested <= 0:
        return 0.0
    return (stats["killed"] / tested) * 100.0


def validate_stats(stats: dict[str, int], threshold: float = MUTATION_THRESHOLD) -> None:
    required = {"killed", "total", "skipped", *_FAILURE_KEYS}
    missing = sorted(required - stats.keys())
    if missing:
        raise ValueError(f"mutation stats missing keys: {', '.join(missing)}")
    if any(not isinstance(stats[key], int) or isinstance(stats[key], bool) for key in required):
        raise TypeError("mutation stats values must be integers")
    if any(stats[key] < 0 for key in required):
        raise ValueError("mutation stats values must be non-negative")
    if stats["killed"] + stats["skipped"] + sum(stats[key] for key in _FAILURE_KEYS) != stats["total"]:
        raise ValueError("mutation stats totals are inconsistent")

    score = mutation_score(stats)
    failures = {key: stats[key] for key in _FAILURE_KEYS if stats[key]}
    if score < threshold or failures:
        details = ", ".join(f"{key}={value}" for key, value in sorted(failures.items())) or "none"
        raise ValueError(
            f"mutation gate failed: score={score:.2f}% threshold={threshold:.2f}% unresolved={details}"
        )


def load_stats(path: Path) -> dict[str, int]:
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise TypeError("mutation stats must be a JSON object with string keys")
    return {key: value for key, value in raw.items() if isinstance(value, int) and not isinstance(value, bool)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--threshold", type=float, default=MUTATION_THRESHOLD)
    args = parser.parse_args()
    stats = load_stats(args.path)
    validate_stats(stats, args.threshold)
    print(f"mutation score {mutation_score(stats):.2f}% meets policy")


if __name__ == "__main__":
    main()
