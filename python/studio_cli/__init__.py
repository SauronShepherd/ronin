"""HTTP-independent command-line foundation for local Ronin projects."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from studio_core import ProjectManifest
from studio_notebook import (
    NotebookDependencyAnalysis,
    NotebookDocument,
    analyze_notebook_dependencies,
)


class CliError(RuntimeError):
    """Expected user-facing CLI failure."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ronin",
        description="Ronin local-first execution tooling",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="check local prerequisites")
    doctor.add_argument(
        "--require",
        choices=("core", "all"),
        default="all",
        help="required check set: core excludes Docker; all is the default",
    )

    validate = commands.add_parser("validate", help="validate a local Ronin project")
    validate.add_argument("project", type=Path)

    plan = commands.add_parser("plan", help="print deterministic notebook execution order")
    plan.add_argument("project", type=Path)
    plan.add_argument("-t", "--target", required=True)
    return parser


def _project_dir(value: Path) -> Path:
    try:
        resolved = value.resolve(strict=True)
    except OSError as exc:
        raise CliError(f"project does not exist: {value}") from exc
    if not resolved.is_dir():
        raise CliError(f"project is not a directory: {value}")
    return resolved


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"cannot read {label}: {path}") from exc


def _load_manifest(project_dir: Path) -> ProjectManifest:
    path = project_dir / ".ronin" / "project.json"
    try:
        return ProjectManifest.from_json(_read_text(path, "project manifest"))
    except (TypeError, ValueError) as exc:
        raise CliError(f"invalid project manifest: {exc}") from exc


def _load_notebook(path: Path) -> NotebookDocument:
    try:
        return NotebookDocument.from_json(_read_text(path, "notebook"))
    except (TypeError, ValueError) as exc:
        raise CliError(f"invalid notebook {path}: {exc}") from exc


def _require_valid_dependencies(
    document: NotebookDocument,
    *,
    path: Path,
) -> NotebookDependencyAnalysis:
    analysis = analyze_notebook_dependencies(document.notebook)
    if analysis.violations:
        detail = "; ".join(violation.message for violation in analysis.violations)
        raise CliError(f"invalid notebook dependencies {path}: {detail}")
    return analysis


def _notebook_paths(project_dir: Path) -> tuple[Path, ...]:
    notebooks_dir = project_dir / "notebooks"
    if not notebooks_dir.is_dir():
        raise CliError(f"project notebooks directory does not exist: {notebooks_dir}")
    notebooks = tuple(sorted(notebooks_dir.rglob("*.ronin.json")))
    if not notebooks:
        raise CliError(f"project contains no *.ronin.json notebooks: {notebooks_dir}")
    return notebooks


def _resolve_target(project_dir: Path, target: str) -> Path:
    if not target or target != target.strip():
        raise CliError("target must be non-empty and trimmed")
    relative = Path(target)
    if relative.is_absolute():
        raise CliError("target must be relative to the project")
    candidate = (project_dir / relative).resolve(strict=False)
    if not candidate.is_relative_to(project_dir):
        raise CliError("target escapes the project directory")
    if not candidate.exists() and not str(candidate).endswith(".ronin.json"):
        candidate = Path(str(candidate) + ".ronin.json")
    if not candidate.is_file():
        raise CliError(f"notebook target does not exist: {target}")
    return candidate


def _doctor(require: str) -> int:
    git_path = shutil.which("git")
    docker_path = shutil.which("docker")
    checks = (
        (
            "python>=3.11",
            sys.hexversion >= 0x030B0000,
            f"{sys.version_info.major}.{sys.version_info.minor}",
            True,
        ),
        ("git", git_path is not None, git_path or "not found", True),
        ("docker", docker_path is not None, docker_path or "not found", require == "all"),
    )
    failed = False
    for name, ok, detail, required in checks:
        print(f"{name}: {'ok' if ok else 'fail'} ({detail})")
        failed = failed or (required and not ok)
    if failed:
        raise CliError(f"doctor required {require} checks failed")
    if require == "all":
        print("doctor: all checks passed")
    else:
        print("doctor: required core checks passed")
    return 0


def _validate(project: Path) -> int:
    project_dir = _project_dir(project)
    _load_manifest(project_dir)
    notebooks = _notebook_paths(project_dir)
    for notebook_path in notebooks:
        document = _load_notebook(notebook_path)
        _require_valid_dependencies(document, path=notebook_path)
    print(f"project: {project_dir}")
    print(f"notebooks: {len(notebooks)}")
    print("validate: ok")
    return 0


def _plan(project: Path, target: str) -> int:
    project_dir = _project_dir(project)
    _load_manifest(project_dir)
    target_path = _resolve_target(project_dir, target)
    document = _load_notebook(target_path)
    analysis = _require_valid_dependencies(document, path=target_path)
    references = {
        cell.id: identity.reference
        for cell, identity in zip(document.notebook.cells, document.cell_identities, strict=True)
    }
    print(f"target: {target_path.relative_to(project_dir)}")
    print("execution order:")
    for position, cell_id in enumerate(analysis.execution_order, start=1):
        print(f"  {position}. {references[cell_id]}")
    print("levels:")
    for level, cell_ids in enumerate(analysis.levels):
        print(f"  {level}: {', '.join(references[cell_id] for cell_id in cell_ids)}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run one bounded local CLI command and return a process exit code."""

    namespace = _parser().parse_args(argv)
    command = cast(str, namespace.command)
    try:
        if command == "doctor":
            return _doctor(cast(str, namespace.require))
        if command == "validate":
            return _validate(cast(Path, namespace.project))
        if command == "plan":
            return _plan(cast(Path, namespace.project), cast(str, namespace.target))
        raise CliError(f"unsupported command: {command}")
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


__all__ = ("CliError", "main")
