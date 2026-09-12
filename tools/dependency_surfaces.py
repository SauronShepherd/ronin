"""Fail-closed inventory of exact build-system and release-only dependency surfaces."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path

_EXACT_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^ \t\\;@\[\]]+)$")


class DependencySurfaceError(ValueError):
    """Raised when a dependency surface is ambiguous or not exactly pinned."""


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _exact_requirements(values: object, *, surface: str) -> dict[str, str]:
    if not isinstance(values, list) or not values:
        raise DependencySurfaceError(f"{surface} must contain at least one exact requirement")
    result: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str):
            raise DependencySurfaceError(f"{surface} requirements must be strings")
        match = _EXACT_REQUIREMENT.fullmatch(value)
        if match is None:
            raise DependencySurfaceError(
                f"{surface} must use exact name==version pins without URLs, markers, extras, or ranges: {value!r}"
            )
        name = _canonical_name(match.group(1))
        version = match.group(2)
        if name in result:
            if result[name] != version:
                raise DependencySurfaceError(
                    f"{surface} contains conflicting versions for {name}: {result[name]} vs {version}"
                )
            raise DependencySurfaceError(f"{surface} contains duplicate requirement for {name}")
        result[name] = version
    return dict(sorted(result.items()))


def build_system_requirements(root: Path) -> dict[str, str]:
    """Return one conflict-free exact PEP 517 build-system requirement map."""
    combined: dict[str, str] = {}
    for relative in (Path("pyproject.toml"), Path("packages/pyronin/pyproject.toml")):
        path = root / relative
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise DependencySurfaceError(f"cannot read build-system surface: {relative}") from exc
        build_system = data.get("build-system")
        if not isinstance(build_system, dict):
            raise DependencySurfaceError(f"missing build-system table: {relative}")
        requirements = _exact_requirements(
            build_system.get("requires"), surface=f"{relative}:build-system.requires"
        )
        for name, version in requirements.items():
            if name in combined and combined[name] != version:
                raise DependencySurfaceError(
                    f"build-system surfaces conflict for {name}: {combined[name]} vs {version}"
                )
            combined[name] = version
    return dict(sorted(combined.items()))


def release_tool_requirements(root: Path) -> dict[str, str]:
    """Return exact release-only tools from the committed v1 surface manifest."""
    path = root / "third_party/release-tools-v1.txt"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DependencySurfaceError("cannot read third_party/release-tools-v1.txt") from exc
    active = [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]
    return _exact_requirements(active, surface="release-tools-v1")


def dependency_surfaces(root: Path) -> dict[str, object]:
    """Return exact non-runtime surfaces that require separate license evidence."""
    return {
        "schema_version": 1,
        "build_system": build_system_requirements(root),
        "release_tools": release_tool_requirements(root),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    payload = dependency_surfaces(args.root.resolve())
    print(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
