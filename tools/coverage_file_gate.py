"""Fail closed when safety-critical package files regress below coverage policy."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

DEFAULT_THRESHOLD: Final[float] = 80.0


def load_coverage(path: Path) -> Mapping[str, object]:
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise TypeError("coverage evidence must be a JSON object")
    files = raw.get("files")
    if not isinstance(files, dict) or not all(isinstance(key, str) for key in files):
        raise TypeError("coverage evidence must contain a files object")
    return cast(Mapping[str, object], raw)


def _percent(entry: object, *, path: str) -> float:
    if not isinstance(entry, dict):
        raise TypeError(f"coverage entry for {path} must be an object")
    summary = entry.get("summary")
    if not isinstance(summary, dict):
        raise TypeError(f"coverage entry for {path} must contain a summary object")
    percent = summary.get("percent_covered")
    if not isinstance(percent, (int, float)) or isinstance(percent, bool):
        raise TypeError(f"coverage percent for {path} must be numeric")
    value = float(percent)
    if not 0.0 <= value <= 100.0:
        raise ValueError(f"coverage percent for {path} must be between 0 and 100")
    return value


def validate_package_files(
    coverage: Mapping[str, object],
    source_root: Path,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    baselines: Mapping[str, float] | None = None,
) -> dict[str, float]:
    if not 0.0 <= threshold <= 100.0:
        raise ValueError("coverage threshold must be between 0 and 100")
    baselines = {} if baselines is None else baselines
    for relative, baseline in baselines.items():
        if not 0.0 <= baseline <= 100.0:
            raise ValueError(f"coverage baseline for {relative} must be between 0 and 100")
        if baseline > threshold:
            raise ValueError(f"coverage baseline for {relative} cannot exceed default threshold")

    files = coverage.get("files")
    if not isinstance(files, dict):
        raise TypeError("coverage evidence must contain a files object")

    expected = sorted(path for path in source_root.rglob("*.py") if path.is_file())
    if not expected:
        raise ValueError(f"no Python source files found under {source_root}")

    measured: dict[str, float] = {}
    failures: list[str] = []
    normalized_entries = {Path(name).as_posix(): value for name, value in files.items()}
    root_parts = source_root.as_posix().rstrip("/")

    for source_path in expected:
        relative = source_path.relative_to(source_root).as_posix()
        key = source_path.as_posix()
        entry = normalized_entries.get(key)
        if entry is None:
            suffix = f"/{root_parts}/{relative}"
            matches = [value for name, value in normalized_entries.items() if name.endswith(suffix)]
            if len(matches) != 1:
                failures.append(f"{relative}: missing coverage evidence")
                continue
            entry = matches[0]
        percent = _percent(entry, path=relative)
        measured[relative] = percent
        required = baselines.get(relative, threshold)
        if percent + 1e-9 < required:
            failures.append(f"{relative}: {percent:.2f}% < required {required:.2f}%")

    unknown_baselines = sorted(set(baselines) - {path.relative_to(source_root).as_posix() for path in expected})
    if unknown_baselines:
        raise ValueError("coverage baselines reference missing files: " + ", ".join(unknown_baselines))
    if failures:
        raise ValueError("per-file coverage gate failed: " + "; ".join(failures))
    return measured


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage_json", type=Path)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--baseline",
        action="append",
        default=[],
        metavar="RELATIVE_PATH=PERCENT",
        help="explicit non-regression baseline for a legacy file below the default floor",
    )
    args = parser.parse_args()
    baselines: dict[str, float] = {}
    for item in args.baseline:
        try:
            relative, raw_percent = item.rsplit("=", 1)
            percent = float(raw_percent)
        except ValueError as exc:
            raise SystemExit(f"invalid baseline {item!r}; expected RELATIVE_PATH=PERCENT") from exc
        if not relative or relative in baselines:
            raise SystemExit(f"invalid or duplicate baseline path: {relative!r}")
        baselines[relative] = percent

    measured = validate_package_files(
        load_coverage(args.coverage_json),
        args.source_root,
        threshold=args.threshold,
        baselines=baselines,
    )
    print(
        f"per-file coverage policy passed for {len(measured)} files "
        f"(default >= {args.threshold:.2f}%)"
    )


if __name__ == "__main__":
    main()
