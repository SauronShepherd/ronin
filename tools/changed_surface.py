"""Build a fail-closed changed-surface manifest for PR/release review."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

SUBSYSTEMS = {
    "packaging": (
        ".dockerignore",
        ".env.example",
        ".gitignore",
        ".ruff-global.txt",
        "Makefile",
        "pyproject.toml",
        "requirements",
        "package.json",
        "package-lock.json",
    ),
    "runtime": (
        "python/studio_runtime",
        "python/studio_worker",
        "python/studio_kernel",
        "python/studio_core",
        "python/studio_execution",
        "python/studio_storage",
        "python/studio_orchestrator",
        "python/studio_runners",
        "python/studio_runner_broker",
        "python/studio_vcs",
        "python/studio_notebook",
        "python/studio_server",
        "python/studio_sql",
        "python/studio_semantic",
        "python/studio_quality",
        "python/studio_lakehouse",
        "python/studio_connectors",
        "python/studio_streaming",
        "python/studio_synthetic_data",
        "python/studio_observability",
        "python/studio_finops",
    ),
    "plugin": (
        "python/studio_plugin",
        "python/studio_plugin_observability",
        "python/studio_plugin_sdk",
        "python/studio_plugin_testkit",
        "python/studio_plugin_workspaces",
        "agent-skills/",
        "packages/",
    ),
    "data-engineering": (
        "python/studio_data_engineering",
        "tests/test_data_engineering",
        "tests/integration/test_data_engineering",
        "tools/data_engineering",
    ),
    "ml": (
        "python/studio_ml",
        "tests/test_ml",
        "tests/integration/test_ml",
    ),
    "migration": (
        "python/studio_migration",
        "tests/test_migration",
        "tests/integration/test_migration",
        "tools/migration",
    ),
    "ui": (
        "web/",
        "tools/browser",
        "tools/installed_studio",
        "tests/test_web",
        "tests/test_studio",
        "tests/test_browser",
        "tests/integration/test_studio",
        "web-tests/",
    ),
    "qualification": (
        "tools/release",
        "tools/mutation",
        "tools/coverage",
        "tools/changed_surface",
        "tests/test_release",
        "tests/test_docker",
        ".github/workflows",
        "api/",
        "compose.yaml",
        "config/",
        "deploy/",
        "docker/",
        "examples/",
        "third_party/",
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
    # Broad fallbacks are deliberately applied only after all product-specific
    # prefixes.  This keeps the manifest total for repository configuration and
    # tests while retaining the narrower gate for product code.
    if not matches and normalized.startswith("python/"):
        matches = ["runtime"]
    if not matches and normalized.startswith("tests/"):
        matches = ["qualification"]
    if not matches and normalized.startswith("tools/"):
        matches = ["qualification"]
    if not matches and normalized.endswith(".md"):
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
