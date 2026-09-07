"""Command-line entry points for local and served execution."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from studio_core import ProjectManifest
from studio_notebook import NotebookDependencyAnalysis, NotebookDocument, analyze_notebook_dependencies


class CliError(RuntimeError):
    """Raised for user-facing CLI validation failures."""


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def _run_command(executable: str, args: tuple[str, ...]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(  # noqa: S603
            (executable, *args),
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, output or f"exit {completed.returncode}"


def _tool_check(name: str, args: tuple[str, ...]) -> DoctorCheck:
    executable = shutil.which(name)
    if executable is None:
        return DoctorCheck(name, False, "not found on PATH")
    ok, detail = _run_command(executable, args)
    return DoctorCheck(name, ok, detail)


def _doctor_checks() -> tuple[DoctorCheck, ...]:
    python_ok = sys.version_info >= (3, 11)
    python_detail = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    docker = shutil.which("docker")
    if docker is None:
        docker_engine = DoctorCheck("docker-engine", False, "docker not found on PATH")
    else:
        ok, detail = _run_command(docker, ("info", "--format", "{{.ServerVersion}}"))
        docker_engine = DoctorCheck("docker-engine", ok, detail)
    return (
        DoctorCheck("python", python_ok, python_detail),
        _tool_check("git", ("--version",)),
        _tool_check("docker", ("--version",)),
        docker_engine,
    )


def _doctor() -> int:
    checks = _doctor_checks()
    for check in checks:
        print(f"{'PASS' if check.ok else 'FAIL'} {check.name}: {check.detail}")
    if all(check.ok for check in checks):
        print(f"all checks passed ({len(checks)}/{len(checks)})")
        return 0
    failed = sum(not check.ok for check in checks)
    print(f"doctor failed: {failed} check(s) failed", file=sys.stderr)
    return 1


def _project_root(value: Path) -> Path:
    try:
        root = value.resolve(strict=True)
    except OSError as exc:
        raise CliError(f"project path does not exist: {value}") from exc
    if not root.is_dir():
        raise CliError(f"project path is not a directory: {value}")
    return root


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CliError(f"cannot read {label}: {path}") from exc


def _load_manifest(root: Path) -> ProjectManifest:
    path = root / ".ronin" / "project.json"
    try:
        return ProjectManifest.from_json(_read_text(path, "project manifest"))
    except (TypeError, ValueError) as exc:
        raise CliError(f"invalid project manifest {path}: {exc}") from exc


def _load_notebook(path: Path) -> NotebookDocument:
    try:
        return NotebookDocument.from_json(_read_text(path, "notebook"))
    except (TypeError, ValueError) as exc:
        raise CliError(f"invalid notebook {path}: {exc}") from exc


def _analysis(document: NotebookDocument, path: Path) -> NotebookDependencyAnalysis:
    analysis = analyze_notebook_dependencies(document.notebook)
    if analysis.violations:
        details = "; ".join(violation.message for violation in analysis.violations)
        raise CliError(f"invalid notebook DAG {path}: {details}")
    return analysis


def _notebook_paths(root: Path) -> tuple[Path, ...]:
    try:
        paths = tuple(sorted(root.rglob("*.ronin.json")))
    except OSError as exc:
        raise CliError(f"cannot enumerate notebooks under {root}") from exc
    safe: list[Path] = []
    for path in paths:
        if path.is_symlink():
            raise CliError(f"notebook path may not be a symlink: {path}")
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise CliError(f"notebook path escapes project root or is not a file: {path}")
        safe.append(resolved)
    return tuple(safe)


def _validate(project: Path) -> int:
    root = _project_root(project)
    manifest = _load_manifest(root)
    notebook_paths = _notebook_paths(root)
    if not notebook_paths:
        raise CliError(f"no *.ronin.json notebooks found under {root}")
    executable_cells = 0
    for path in notebook_paths:
        executable_cells += len(_analysis(_load_notebook(path), path).execution_order)
    print(
        f"valid project {manifest.project.id.value}: "
        f"notebooks={len(notebook_paths)} executable_cells={executable_cells}"
    )
    return 0


def _resolve_target(root: Path, target: str) -> Path:
    requested = Path(target)
    candidates = (requested,) if target.endswith(".ronin.json") else (requested, Path(f"{target}.ronin.json"))
    for relative in candidates:
        candidate = root / relative
        if candidate.is_symlink():
            raise CliError(f"notebook target may not be a symlink: {relative}")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if not resolved.is_relative_to(root):
            raise CliError(f"notebook target escapes project root: {target}")
        if resolved.is_file():
            return resolved
    raise CliError(f"notebook target not found: {target}")


def _cell_names(document: NotebookDocument) -> dict[str, str]:
    return {
        str(cell.id): identity.reference
        for cell, identity in zip(document.notebook.cells, document.cell_identities, strict=True)
    }


def _plan(project: Path, target: str) -> int:
    root = _project_root(project)
    manifest = _load_manifest(root)
    path = _resolve_target(root, target)
    document = _load_notebook(path)
    analysis = _analysis(document, path)
    names = _cell_names(document)
    print(f"project: {manifest.project.id.value}")
    print(f"target: {path.relative_to(root)}")
    print("execution order:")
    for position, cell_id in enumerate(analysis.execution_order, start=1):
        print(f"  {position}. {names[str(cell_id)]} [{cell_id}]")
    print("levels:")
    for index, level in enumerate(analysis.levels):
        rendered = ", ".join(names[str(cell_id)] for cell_id in level)
        print(f"  {index}: {rendered}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ronin", description="Ronin local-first execution CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="check local v0.1 prerequisites")

    validate = subparsers.add_parser("validate", help="validate a Ronin project and notebook DAGs")
    validate.add_argument("project", type=Path)

    plan = subparsers.add_parser("plan", help="print deterministic notebook execution order and levels")
    plan.add_argument("project", type=Path)
    plan.add_argument("-t", "--target", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the currently supported Ronin CLI surface."""

    args = _parser().parse_args(argv)
    command = cast(str, args.command)
    try:
        if command == "doctor":
            return _doctor()
        if command == "validate":
            return _validate(cast(Path, args.project))
        if command == "plan":
            return _plan(cast(Path, args.project), cast(str, args.target))
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {command}")


__all__ = ("CliError", "DoctorCheck", "main")
