"""Build a fail-closed changed-surface manifest for PR/release review."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

SUBSYSTEMS = {
    "packaging": ("pyproject.toml", "requirements", "package.json", "package-lock.json"),
    "runtime": ("python/studio_runtime", "python/studio_worker", "python/studio_kernel"),
    "plugin": ("python/studio_plugin", "python/studio_core/plugins.py", "packages/"),
    "data-engineering": ("python/studio_data_engineering", "tests/test_data_engineering"),
    "ml": ("python/studio_ml", "tests/test_ml", "python/studio_ai_studio"),
    "migration": ("python/studio_migration", "tests/test_migration"),
    "ui": (
        "web/",
        "tools/browser",
        "tools/installed_studio",
        "tests/test_web",
        "package",
    ),
    "qualification": (
        "tools/release",
        "tools/mutation",
        "tools/coverage",
        "tools/changed_surface",
        "tests/test_release",
        "tests/test_docker",
        ".github/workflows",
    ),
    "documentation": ("docs/", ".md"),
}


def classify(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    matches = [
        name
        for name, prefixes in SUBSYSTEMS.items()
        if any(normalized == prefix or normalized.startswith(prefix) for prefix in prefixes)
    ]
    if normalized.endswith(".md") and "documentation" not in matches:
        matches.append("documentation")
    if len(matches) != 1:
        return matches[0] if len(matches) == 1 else None
    return matches[0]


def changed_files(base: str, head: str) -> list[str]:
    result = subprocess.run(  # noqa: S603, S607 - trusted git command and explicit arguments
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", base, head],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(path for path in result.stdout.splitlines() if path)


def build_manifest(paths: list[str], *, base: str, head: str) -> dict[str, object]:
    groups: dict[str, list[str]] = {name: [] for name in SUBSYSTEMS}
    unclassified: list[str] = []
    for path in paths:
        subsystem = classify(path)
        if subsystem is None:
            unclassified.append(path)
        else:
            groups[subsystem].append(path)
    if unclassified:
        raise ValueError("unclassified changed paths: " + ", ".join(unclassified))
    return {
        "schema": "ronin.changed-surface/v1",
        "base": base,
        "head": head,
        "files": len(paths),
        "subsystems": {name: files for name, files in groups.items() if files},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = build_manifest(changed_files(args.base, args.head), base=args.base, head=args.head)
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
