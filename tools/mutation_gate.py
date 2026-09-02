"""Validate exported mutmut CI/CD statistics against Ronin's mutation policy."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

MUTATION_THRESHOLD: Final[float] = 90.0
_SCORE_KEYS: Final[tuple[str, ...]] = (
    "killed",
    "survived",
    "no_tests",
    "suspicious",
    "timeout",
    "check_was_interrupted_by_user",
    "segfault",
)
_INVALID_EVIDENCE_KEYS: Final[tuple[str, ...]] = (
    "no_tests",
    "suspicious",
    "timeout",
    "check_was_interrupted_by_user",
    "segfault",
)
_REQUIRED_KEYS: Final[frozenset[str]] = frozenset((*_SCORE_KEYS, "total", "skipped"))


def mutation_score(stats: Mapping[str, int]) -> float:
    tested = stats["total"] - stats["skipped"]
    if tested <= 0:
        return 0.0
    return (stats["killed"] / tested) * 100.0


def validate_stats(stats: Mapping[str, object], threshold: float = MUTATION_THRESHOLD) -> None:
    missing = sorted(_REQUIRED_KEYS - stats.keys())
    if missing:
        raise ValueError(f"mutation stats missing keys: {', '.join(missing)}")
    if not 0.0 <= threshold <= 100.0:
        raise ValueError("mutation threshold must be between 0 and 100")
    if any(not isinstance(stats[key], int) or isinstance(stats[key], bool) for key in _REQUIRED_KEYS):
        raise TypeError("mutation stats values must be integers")

    counts = cast(Mapping[str, int], stats)
    if any(counts[key] < 0 for key in _REQUIRED_KEYS):
        raise ValueError("mutation stats values must be non-negative")
    accounted = counts["skipped"] + sum(counts[key] for key in _SCORE_KEYS)
    if accounted != counts["total"]:
        raise ValueError("mutation stats totals are inconsistent")

    invalid = {key: counts[key] for key in _INVALID_EVIDENCE_KEYS if counts[key]}
    score = mutation_score(counts)
    if invalid:
        details = ", ".join(f"{key}={value}" for key, value in sorted(invalid.items()))
        raise ValueError(f"mutation gate has invalid evidence: {details}")
    if score < threshold:
        raise ValueError(f"mutation score {score:.2f}% is below threshold {threshold:.2f}%")


def load_stats(path: Path) -> Mapping[str, object]:
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
        raise TypeError("mutation stats must be a JSON object with string keys")
    return cast(Mapping[str, object], raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--threshold", type=float, default=MUTATION_THRESHOLD)
    args = parser.parse_args()
    stats = load_stats(args.path)
    validate_stats(stats, args.threshold)
    print(f"mutation score {mutation_score(cast(Mapping[str, int], stats)):.2f}% meets policy")


if __name__ == "__main__":
    main()
