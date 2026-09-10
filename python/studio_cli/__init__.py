"""Supported Ronin command-line surface for local projects and the v0.1 control plane."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from studio_core import GrantSet, ProjectManifest
from studio_execution import DurableExecutionService
from studio_notebook import (
    NotebookDependencyAnalysis,
    NotebookDocument,
    analyze_notebook_dependencies,
)
from studio_orchestrator import Instant
from studio_server import RoninHTTPServer
from studio_storage import SqliteJobStore
from studio_worker import LocalWorkerRuntime, LocalWorkerRuntimeConfig, WorkerPaths

from .network import TERMINAL_STATES, ControlPlaneClient, ControlPlaneError


class CliError(RuntimeError):
    """Expected user-facing CLI failure."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ronin", description="Ronin local-first execution tooling"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="check local prerequisites")
    doctor.add_argument("--require", choices=("core", "all"), default="all")
    validate = commands.add_parser("validate", help="validate a local Ronin project")
    validate.add_argument("project", type=Path)
    plan = commands.add_parser("plan", help="print deterministic notebook execution order")
    plan.add_argument("project", type=Path)
    plan.add_argument("-t", "--target", required=True)
    commands.add_parser("serve", help="run the local Ronin HTTP control plane")
    commands.add_parser("worker", help="run the local durable Docker worker")

    submit = commands.add_parser("submit", help="submit a project notebook for execution")
    submit.add_argument("project")
    submit.add_argument("-t", "--target", required=True)
    submit.add_argument("--idempotency-key")
    submit.add_argument("--param", action="append", default=[], metavar="KEY=VALUE")
    submit.add_argument("--json", action="store_true")

    status = commands.add_parser("status", help="show durable job status")
    status.add_argument("job_id")
    status.add_argument("--wait", action="store_true")
    status.add_argument("--json", action="store_true")

    logs = commands.add_parser("logs", help="show durable Run-global events")
    logs.add_argument("job_id")
    logs.add_argument("--since")
    logs.add_argument("--follow", action="store_true")
    logs.add_argument("--json", action="store_true")

    jobs = commands.add_parser("jobs", help="list jobs newest first")
    jobs.add_argument("--project")
    jobs.add_argument(
        "--state",
        choices=("queued", "running", "cancelling", "cancelled", "succeeded", "failed"),
    )
    jobs.add_argument("--limit", type=int, default=50)
    jobs.add_argument("--cursor")
    jobs.add_argument("--json", action="store_true")

    cancel = commands.add_parser("cancel", help="request durable job cancellation")
    cancel.add_argument("job_id")
    cancel.add_argument("--json", action="store_true")
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
    document: NotebookDocument, *, path: Path
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
    print(
        "doctor: all checks passed" if require == "all" else "doctor: required core checks passed"
    )
    return 0


def _validate(project: Path) -> int:
    project_dir = _project_dir(project)
    _load_manifest(project_dir)
    notebooks = _notebook_paths(project_dir)
    for notebook_path in notebooks:
        _require_valid_dependencies(_load_notebook(notebook_path), path=notebook_path)
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


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or not value or value != value.strip():
        raise CliError(f"{name} must be set to a non-empty trimmed value")
    return value


def _token() -> str:
    token_file = os.environ.get("RONIN_TOKEN_FILE")
    value = (
        _read_text(Path(token_file), "token file").strip() if token_file else _env("RONIN_TOKEN")
    )
    if not value or value != value.strip() or "\n" in value or "\r" in value:
        raise CliError("Ronin token must be non-empty, trimmed, and single-line")
    return value


def _token_grants() -> GrantSet:
    """Load the canonical v1 grant set associated with the static bearer token."""
    try:
        grants = GrantSet.from_json(_env("RONIN_TOKEN_SCOPES"))
    except ValueError as exc:
        raise CliError(f"invalid RONIN_TOKEN_SCOPES: {exc}") from exc
    if not grants.grants:
        raise CliError("RONIN_TOKEN_SCOPES must contain at least one typed grant")
    return grants


def _client() -> ControlPlaneClient:
    return ControlPlaneClient(_env("RONIN_URL", "http://127.0.0.1:8080"), _token())


def _parse_params(values: Sequence[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in values:
        key, separator, raw = value.partition("=")
        if not separator or not key or key != key.strip() or key in result:
            raise CliError(
                "--param values must be unique KEY=VALUE pairs with non-empty trimmed keys"
            )
        try:
            parsed: object = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        result[key] = parsed
    return result


def _emit_job(job: dict[str, object], *, as_json: bool, default_field: str = "state") -> None:
    if as_json:
        print(json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    else:
        print(job[default_field])


def _submit(namespace: argparse.Namespace) -> int:
    job = _client().submit(
        project=cast(str, namespace.project),
        target=cast(str, namespace.target),
        parameters=_parse_params(cast(Sequence[str], namespace.param)),
        idempotency_key=cast(str | None, namespace.idempotency_key),
    )
    _emit_job(job, as_json=cast(bool, namespace.json), default_field="id")
    return 0


def _status(namespace: argparse.Namespace) -> int:
    client = _client()
    job_id = cast(str, namespace.job_id)
    job = client.status(job_id)
    delay = 0.1
    while cast(bool, namespace.wait) and job["state"] not in TERMINAL_STATES:
        time.sleep(delay)
        delay = min(delay * 2, 2.0)
        job = client.status(job_id)
    _emit_job(job, as_json=cast(bool, namespace.json))
    return 0


def _logs(namespace: argparse.Namespace) -> int:
    client = _client()
    job_id = cast(str, namespace.job_id)
    since = cast(str | None, namespace.since)
    while True:
        page = client.events(job_id, since=since)
        items = cast(list[dict[str, object]], page["items"])
        for event in items:
            if cast(bool, namespace.json):
                print(json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            else:
                print(
                    f"{event['sequence']}\t{event['attempt_id']}:{event['attempt_sequence']}\t{event['kind']}\t{event['message']}"
                )
        since = cast(str, page["next_since"])
        if not cast(bool, namespace.follow):
            return 0
        if client.status(job_id)["state"] in TERMINAL_STATES and not items:
            return 0
        time.sleep(0.2)


def _jobs(namespace: argparse.Namespace) -> int:
    page = _client().jobs(
        project=cast(str | None, namespace.project),
        state=cast(str | None, namespace.state),
        limit=cast(int, namespace.limit),
        cursor=cast(str | None, namespace.cursor),
    )
    if cast(bool, namespace.json):
        print(json.dumps(page, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    else:
        for job in cast(list[dict[str, object]], page["items"]):
            print(f"{job['id']}\t{job['state']}")
        if page["next_cursor"] is not None:
            print(f"next_cursor\t{page['next_cursor']}")
    return 0


def _cancel(namespace: argparse.Namespace) -> int:
    job = _client().cancel(cast(str, namespace.job_id))
    _emit_job(job, as_json=cast(bool, namespace.json))
    return 0


def _now() -> Instant:
    return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _database() -> Path:
    return Path(_env("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()


def _serve() -> int:
    try:
        port = int(_env("RONIN_PORT", "8080"))
    except ValueError as exc:
        raise CliError("RONIN_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise CliError("RONIN_PORT must be between 1 and 65535")
    database = _database()
    database.parent.mkdir(parents=True, exist_ok=True)
    service = DurableExecutionService(SqliteJobStore(database, migration_now=_now()))
    server = RoninHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), port),
        service,
        token=_token(),
        grants=_token_grants(),
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


def _worker() -> int:
    database = _database()
    workspace = Path(_env("RONIN_WORKSPACE", ".")).expanduser().resolve()
    config = LocalWorkerRuntimeConfig(
        paths=WorkerPaths(workspace, database.parent),
        owner=_env("RONIN_WORKER_OWNER", f"worker-{os.getpid()}"),
        image=_env("RONIN_IMAGE"),
        database_name=database.name,
    )

    async def run() -> None:
        async with LocalWorkerRuntime(config, migration_now=_now()) as runtime:
            await runtime.run_until_signalled()

    asyncio.run(run())
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run one bounded CLI command and return a process exit code."""

    namespace = _parser().parse_args(argv)
    command = cast(str, namespace.command)
    try:
        if command == "doctor":
            return _doctor(cast(str, namespace.require))
        if command == "validate":
            return _validate(cast(Path, namespace.project))
        if command == "plan":
            return _plan(cast(Path, namespace.project), cast(str, namespace.target))
        if command == "serve":
            return _serve()
        if command == "worker":
            return _worker()
        if command == "submit":
            return _submit(namespace)
        if command == "status":
            return _status(namespace)
        if command == "logs":
            return _logs(namespace)
        if command == "jobs":
            return _jobs(namespace)
        if command == "cancel":
            return _cancel(namespace)
        raise CliError(f"unsupported command: {command}")
    except (CliError, ControlPlaneError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


__all__ = ("CliError", "main")
