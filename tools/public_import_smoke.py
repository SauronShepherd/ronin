"""Fail-closed import smoke for every public package declared by the project."""

from __future__ import annotations

import argparse
import importlib
import json
import tomllib
from pathlib import Path


def declared_packages(pyproject: Path) -> tuple[str, ...]:
    with pyproject.open("rb") as stream:
        data = tomllib.load(stream)
    packages = data.get("tool", {}).get("mypy", {}).get("packages")
    if (
        not isinstance(packages, list)
        or not packages
        or not all(isinstance(package, str) and package.strip() for package in packages)
    ):
        raise ValueError("pyproject tool.mypy.packages must contain public package names")
    result = tuple(packages)
    if len(result) != len(set(result)):
        raise ValueError("pyproject tool.mypy.packages contains duplicate names")
    return result


def import_packages(packages: tuple[str, ...]) -> dict[str, object]:
    failures: dict[str, str] = {}
    imported: list[str] = []
    for package in packages:
        try:
            importlib.import_module(package)
        except Exception as exc:  # pragma: no cover - exercised by subprocess smoke
            failures[package] = f"{type(exc).__name__}: {exc}"
        else:
            imported.append(package)
    return {"packages": list(packages), "imported": imported, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    args = parser.parse_args()
    result = import_packages(declared_packages(args.pyproject))
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["failures"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
