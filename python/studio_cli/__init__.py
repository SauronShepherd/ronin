"""Supported Ronin command-line surface for local projects and the v0.1 control plane."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from studio_core import GrantSet, ProjectManifest
from studio_core.canonical_json import decode as decode_canonical_json
from studio_data_engineering import (
    PostgresQueryEvidenceReferenceStore,
    PostgresQueryFluxExecutionStore,
    QueryEngineRuntimeProvider,
    QueryFluxWorkerRunner,
    SqliteQueryEvidenceReferenceStore,
    SqliteQueryFluxExecutionStore,
)
from studio_execution import DurableExecutionService
from studio_migration import (
    IICS_ADAPTER_VERSION,
    BenchmarkResult,
    GeneratedProgram,
    GeneratedProject,
    MigrationUnit,
    SourceArtifact,
    SourceInventory,
    analyze_pyspark,
    decide_promotion,
    discover_databricks,
    discover_dataiku,
    discover_fabric,
    discover_foundry,
    discover_iics_zip,
    export_migration_script,
    extract_blueprint,
    generate_project,
    promotion_evidence,
    qualify_spark_runtime,
    render_validation_html,
    render_validation_markdown,
    run_spark_smoke,
    select_all,
    select_scope,
    validate_results,
)
from studio_notebook import (
    NotebookDependencyAnalysis,
    NotebookDocument,
    analyze_notebook_dependencies,
)
from studio_orchestrator import Instant, JobStore
from studio_query_engine import (
    DiscoveredEngine,
    EngineCapabilities,
    EngineHandshake,
    QueryExecutionPolicy,
    QueryFluxTrinoTransport,
)
from studio_server import RoninHTTPServer
from studio_sql import DuckDbDependencyError, DuckDbSqlEngine
from studio_storage import (
    LocalArtifactStore,
    PostgresJobReadPort,
    PostgresMetadataStore,
    SqliteJobStore,
)
from studio_storage.migration_registry import MigrationStatusError, migration_status
from studio_worker import LocalWorkerRuntime, LocalWorkerRuntimeConfig, WorkerPaths

from .agent_skills import (
    default_skill_root,
    discover_skills,
    install_skill,
    package_skill,
    render_skills_json,
    uninstall_skill,
)
from .network import TERMINAL_STATES, ControlPlaneClient, ControlPlaneError
from .retention import run_artifact_retention


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
    artifacts = commands.add_parser("artifacts", help="inspect or collect local artifacts")
    artifact_commands = artifacts.add_subparsers(dest="artifacts_command", required=True)
    retention = artifact_commands.add_parser(
        "retention", help="preview or explicitly collect unreferenced artifacts"
    )
    retention.add_argument("mode", choices=("preview", "collect"))
    retention.add_argument("--confirm", action="store_true")
    retention.add_argument("--allow-empty-live-set", action="store_true")
    retention.add_argument("--page-size", type=int, default=500)
    retention.add_argument("--max-objects", type=int, default=10_000)
    retention.add_argument("--max-pages", type=int, default=1_000)
    connectors = commands.add_parser("connectors", help="inspect and plan connector ingestion")
    connectors.add_argument(
        "connectors_command",
        choices=(
            "capabilities",
            "discover",
            "preview",
            "plan",
            "checkpoint-health",
            "sync-submit",
            "sync-status",
            "sync-cancel",
        ),
    )
    connectors.add_argument("--connector-id")
    connectors.add_argument("--connection-ref")
    connectors.add_argument("--cursor")
    connectors.add_argument("--page-size", type=int)
    connectors.add_argument("--asset-ref")
    connectors.add_argument("--destination-ref")
    connectors.add_argument("--checkpoint-identity")
    connectors.add_argument("--mode", choices=("snapshot", "incremental"), default="snapshot")
    connectors.add_argument("--workspace-id", default=os.environ.get("RONIN_WORKSPACE_ID"))
    connectors.add_argument("--project-id")
    connectors.add_argument("--job-id")
    connectors.add_argument("--definition-file", type=Path)
    connectors.add_argument("--idempotency-key")
    workspaces = commands.add_parser("workspaces", help="manage control-plane workspaces")
    workspace_commands = workspaces.add_subparsers(dest="workspaces_command", required=True)
    workspace_list = workspace_commands.add_parser("list", help="list visible workspaces")
    workspace_list.add_argument("--limit", type=int, default=100)
    workspace_list.add_argument("--cursor")
    workspace_list.add_argument("--json", action="store_true")
    workspace_get = workspace_commands.add_parser("get", help="show one workspace")
    workspace_get.add_argument("workspace_id")
    workspace_get.add_argument("--json", action="store_true")
    workspace_create = workspace_commands.add_parser("create", help="create a workspace")
    workspace_create.add_argument("workspace_id")
    workspace_create.add_argument("--name", required=True)
    workspace_create.add_argument("--description")
    workspace_create.add_argument("--idempotency-key", required=True)
    workspace_create.add_argument("--json", action="store_true")
    workspace_archive = workspace_commands.add_parser("archive", help="archive a workspace")
    workspace_archive.add_argument("workspace_id")
    workspace_archive.add_argument("--json", action="store_true")

    projects = commands.add_parser("projects", help="manage control-plane projects")
    project_commands = projects.add_subparsers(dest="projects_command", required=True)
    project_list = project_commands.add_parser("list", help="list projects in a workspace")
    project_list.add_argument("workspace_id")
    project_list.add_argument("--limit", type=int, default=100)
    project_list.add_argument("--cursor")
    project_list.add_argument("--json", action="store_true")
    project_get = project_commands.add_parser("get", help="show one project")
    project_get.add_argument("workspace_id")
    project_get.add_argument("project_id")
    project_get.add_argument("--json", action="store_true")
    project_create = project_commands.add_parser("create", help="register a project manifest")
    project_create.add_argument("workspace_id")
    project_create.add_argument("manifest", type=Path)
    project_create.add_argument("--idempotency-key")
    project_create.add_argument("--json", action="store_true")
    project_update = project_commands.add_parser("update", help="replace a project manifest")
    project_update.add_argument("workspace_id")
    project_update.add_argument("project_id")
    project_update.add_argument("manifest", type=Path)
    project_update.add_argument("--if-match")
    project_update.add_argument("--json", action="store_true")
    project_archive = project_commands.add_parser("archive", help="archive a project")
    project_archive.add_argument("workspace_id")
    project_archive.add_argument("project_id")
    project_archive.add_argument("--idempotency-key", required=True)
    project_archive.add_argument("--json", action="store_true")
    project_delete = project_commands.add_parser("delete", help="unregister a project")
    project_delete.add_argument("workspace_id")
    project_delete.add_argument("project_id")
    project_delete.add_argument("--json", action="store_true")
    project_bundle_export = project_commands.add_parser(
        "bundle-export", help="export a project manifest or Bundle archive"
    )
    project_bundle_export.add_argument("workspace_id")
    project_bundle_export.add_argument("project_id")
    project_bundle_export.add_argument(
        "--format", choices=("manifest", "archive"), default="archive"
    )
    project_bundle_export.add_argument("--output", type=Path)
    project_bundle_export.add_argument("--json", action="store_true")
    project_bundle_import = project_commands.add_parser(
        "bundle-import", help="import a project Bundle archive"
    )
    project_bundle_import.add_argument("workspace_id")
    project_bundle_import.add_argument("project_id")
    project_bundle_import.add_argument("archive", type=Path)
    project_bundle_import.add_argument("--idempotency-key", required=True)
    project_bundle_import.add_argument("--json", action="store_true")
    catalog = commands.add_parser("catalog", help="inspect governed catalog data")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_assets = catalog_commands.add_parser("assets", help="list visible catalog assets")
    catalog_assets.add_argument("workspace_id")
    catalog_assets.add_argument("--query")
    catalog_assets.add_argument("--limit", type=int, default=100)
    catalog_assets.add_argument("--cursor")
    catalog_assets.add_argument("--json", action="store_true")
    catalog_lineage = catalog_commands.add_parser("lineage", help="inspect catalog lineage")
    catalog_lineage.add_argument("workspace_id")
    catalog_lineage.add_argument("asset_id")
    catalog_lineage.add_argument("version")
    catalog_lineage.add_argument(
        "--direction", choices=("upstream", "downstream"), default="upstream"
    )
    catalog_lineage.add_argument("--limit", type=int, default=100)
    catalog_lineage.add_argument("--json", action="store_true")
    catalog_revisions = catalog_commands.add_parser(
        "revisions", help="list catalog asset revisions"
    )
    catalog_revisions.add_argument("workspace_id")
    catalog_revisions.add_argument("asset_id")
    catalog_revisions.add_argument("--json", action="store_true")
    catalog_revision = catalog_commands.add_parser(
        "revision", help="read one catalog asset revision"
    )
    catalog_revision.add_argument("workspace_id")
    catalog_revision.add_argument("asset_id")
    catalog_revision.add_argument("version")
    catalog_revision.add_argument("--json", action="store_true")
    ontology = commands.add_parser("ontology", help="inspect published ontology schemas")
    ontology_commands = ontology.add_subparsers(dest="ontology_command", required=True)
    ontology_versions = ontology_commands.add_parser("versions", help="list ontology versions")
    ontology_versions.add_argument("workspace_id")
    ontology_versions.add_argument("ontology_id")
    ontology_versions.add_argument("--json", action="store_true")
    ontology_schema = ontology_commands.add_parser("schema", help="read one ontology schema")
    ontology_schema.add_argument("workspace_id")
    ontology_schema.add_argument("ontology_id")
    ontology_schema.add_argument("version")
    ontology_schema.add_argument("--json", action="store_true")
    graphs = commands.add_parser("graphs", help="query workspace-scoped knowledge graphs")
    graph_commands = graphs.add_subparsers(dest="graphs_command", required=True)
    graph_query = graph_commands.add_parser("query", help="run a bounded read-only graph query")
    graph_query.add_argument("workspace_id")
    graph_query.add_argument("graph_id")
    graph_query.add_argument("query")
    graph_query.add_argument("--max-limit", type=int, default=1000)
    graph_query.add_argument("--json", action="store_true")
    graph_objects = graph_commands.add_parser("objects", help="list graph objects by type")
    graph_objects.add_argument("workspace_id")
    graph_objects.add_argument("graph_id")
    graph_objects.add_argument("object_type")
    graph_objects.add_argument("--limit", type=int, default=100)
    graph_objects.add_argument("--json", action="store_true")
    graph_neighbors = graph_commands.add_parser("neighbors", help="list graph neighbors")
    graph_neighbors.add_argument("workspace_id")
    graph_neighbors.add_argument("graph_id")
    graph_neighbors.add_argument("object_type")
    graph_neighbors.add_argument("key_json", help="object key as a JSON array")
    graph_neighbors.add_argument("--limit", type=int, default=100)
    graph_neighbors.add_argument("--json", action="store_true")
    quality = commands.add_parser("quality", help="govern data-quality contracts and evidence")
    quality_commands = quality.add_subparsers(dest="quality_command", required=True)
    quality_contract = quality_commands.add_parser("contract", help="read or replace a contract")
    quality_contract_commands = quality_contract.add_subparsers(
        dest="quality_contract_command", required=True
    )
    quality_contract_get = quality_contract_commands.add_parser(
        "get", help="read one versioned quality contract"
    )
    quality_contract_get.add_argument("workspace_id")
    quality_contract_get.add_argument("asset_id")
    quality_contract_get.add_argument("version")
    quality_contract_get.add_argument("--json", action="store_true")
    quality_contract_put = quality_contract_commands.add_parser(
        "put", help="replace one versioned quality contract"
    )
    quality_contract_put.add_argument("workspace_id")
    quality_contract_put.add_argument("asset_id")
    quality_contract_put.add_argument("version")
    quality_contract_put.add_argument("contract", type=Path)
    quality_contract_put.add_argument("--json", action="store_true")
    quality_run = quality_commands.add_parser("run", help="execute a quality contract")
    quality_run.add_argument("workspace_id")
    quality_run.add_argument("request", type=Path, help="quality run request JSON")
    quality_run.add_argument("--json", action="store_true")
    quality_history = quality_commands.add_parser("history", help="list durable quality runs")
    quality_history.add_argument("workspace_id")
    quality_history.add_argument("asset_id")
    quality_history.add_argument("version")
    quality_history.add_argument("--json", action="store_true")
    quality_state = quality_commands.add_parser("state", help="read the latest quality state")
    quality_state.add_argument("workspace_id")
    quality_state.add_argument("asset_id")
    quality_state.add_argument("version")
    quality_state.add_argument("--json", action="store_true")
    plugins = commands.add_parser("plugins", help="inspect installed Ronin plugins")
    plugins.add_argument(
        "plugins_command", choices=("list", "surfaces", "validate", "lock", "rollback")
    )
    plugins.add_argument("snapshot", type=Path, nargs="?", help="lock snapshot used by rollback")
    plugins.add_argument(
        "--file",
        type=Path,
        default=Path(".ronin/plugin-lock.json"),
        help="plugin lock path (default: .ronin/plugin-lock.json)",
    )

    skills = commands.add_parser("skills", help="discover and package coding-agent skills")
    skills_commands = skills.add_subparsers(dest="skills_command", required=True)
    skills_list = skills_commands.add_parser("list", help="list available agent skills")
    skills_list.add_argument("--root", type=Path, help="skill directory (default: agent-skills)")
    skills_list.add_argument("--json", action="store_true")
    skills_validate = skills_commands.add_parser("validate", help="validate agent skill bundles")
    skills_validate.add_argument("name", nargs="?", help="validate one skill by directory name")
    skills_validate.add_argument(
        "--root", type=Path, help="skill directory (default: agent-skills)"
    )
    skills_validate.add_argument("--json", action="store_true")
    skills_package = skills_commands.add_parser(
        "package", help="write deterministic skill ZIP files"
    )
    skills_package.add_argument("--root", type=Path, help="skill directory (default: agent-skills)")
    skills_package.add_argument(
        "--output", type=Path, help="output directory (default: agent-skills/dist)"
    )
    skills_package.add_argument("--name", help="package one skill by directory name")
    skills_install = skills_commands.add_parser(
        "install", help="install one validated skill without overwriting user files"
    )
    skills_install.add_argument("name")
    skills_install.add_argument("--root", type=Path, help="skill directory (default: agent-skills)")
    skills_install.add_argument("--destination", type=Path, required=True)
    skills_install.add_argument("--dry-run", action="store_true")
    skills_uninstall = skills_commands.add_parser(
        "uninstall", help="remove only files recorded by the managed-skill manifest"
    )
    skills_uninstall.add_argument("name")
    skills_uninstall.add_argument("--destination", type=Path, required=True)
    skills_uninstall.add_argument("--dry-run", action="store_true")

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

    evidence = commands.add_parser("evidence", help="show portable job evidence")
    evidence.add_argument("job_id")
    evidence.add_argument("--json", action="store_true")

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
    migrate = commands.add_parser("migrate", help="inspect a vendor project export")
    migrate_commands = migrate.add_subparsers(dest="migrate_command", required=True)
    inventory = migrate_commands.add_parser(
        "inventory", help="generate a canonical migration report"
    )
    inventory.add_argument("platform", choices=("databricks", "fabric", "dataiku", "foundry"))
    inventory.add_argument("source", type=Path)
    inventory.add_argument("--source-version", default="unknown")
    inventory.add_argument("--output", type=Path)
    migrate_commands.add_parser("adapters", help="list supported Migration Studio adapters")
    artifact_migration = migrate_commands.add_parser(
        "artifact", help="inspect a source artifact without executing it"
    )
    artifact_migration.add_argument("name")
    artifact_migration.add_argument("source", type=Path)
    artifact_migration.add_argument("--media-type", default="application/octet-stream")
    artifact_migration.add_argument("--output", type=Path)
    iics = migrate_commands.add_parser(
        "iics-discover", help="discover IICS ZIP artifacts and emit Migration Studio inventory"
    )
    iics.add_argument("archive", type=Path, nargs="+", help="one or more IICS ZIP exports")
    iics.add_argument("--select", action="append", default=[], metavar="UNIT_KEY")
    iics.add_argument("--output", type=Path)
    validate_migration = migrate_commands.add_parser(
        "validate", help="compare expected and actual result JSON rows"
    )
    validate_migration.add_argument("asset_id")
    validate_migration.add_argument("expected", type=Path)
    validate_migration.add_argument("actual", type=Path)
    validate_migration.add_argument("--level", choices=("simple", "full"), default="simple")
    validate_migration.add_argument(
        "--mode",
        action="append",
        choices=("schema", "counts", "multiset", "keyed"),
        default=[],
    )
    promote_migration = migrate_commands.add_parser(
        "promote", help="evaluate safe promotion from measured benchmark JSON"
    )
    promote_migration.add_argument("candidate_id")
    promote_migration.add_argument("baseline", type=Path)
    promote_migration.add_argument("candidate", type=Path)
    promote_migration.add_argument("--semantic-passed", action="store_true")
    promote_migration.add_argument("--quality-passed", action="store_true")
    promote_migration.add_argument("--max-regression-ratio", type=float, default=0.05)
    promote_migration.add_argument("--output", type=Path)
    validate_migration.add_argument("--key", action="append", default=[])
    validate_migration.add_argument(
        "--tolerance", action="append", default=[], metavar="COLUMN=VALUE"
    )
    validate_migration.add_argument("--output", type=Path)
    validate_migration.add_argument(
        "--format",
        choices=("json", "markdown", "html"),
        default="json",
        help="report format (default: json)",
    )
    analyze_migration = migrate_commands.add_parser(
        "analyze", help="run deterministic static analysis on PySpark source"
    )
    analyze_migration.add_argument("source", type=Path)
    analyze_migration.add_argument("--output", type=Path)
    spark_preflight = migrate_commands.add_parser(
        "spark-preflight", help="check the local Spark Python runtime and emit evidence"
    )
    spark_preflight.add_argument("--output", type=Path)
    spark_smoke = migrate_commands.add_parser(
        "spark-smoke", help="run a native Spark validation smoke test and emit evidence"
    )
    spark_smoke.add_argument("--output", type=Path)
    generate_migration = migrate_commands.add_parser(
        "generate", help="generate a deterministic PySpark candidate project"
    )
    generate_migration.add_argument("inventory", type=Path)
    generate_migration.add_argument("output", type=Path)
    generate_migration.add_argument("--select", action="append", default=[])
    generate_migration.add_argument("--blueprint", type=Path)
    qualify_migration = migrate_commands.add_parser(
        "qualify", help="qualify a generated PySpark candidate project"
    )
    qualify_migration.add_argument("project", type=Path)
    qualify_migration.add_argument("--output", type=Path)
    export_migration = migrate_commands.add_parser(
        "export", help="export a standalone PySpark migration script"
    )
    export_migration.add_argument("project", type=Path)
    export_migration.add_argument("--output", type=Path, required=True)
    import_migration = migrate_commands.add_parser(
        "import", help="validate a generated project and emit canonical import evidence"
    )
    import_migration.add_argument("project", type=Path)
    import_migration.add_argument("--target", required=True)
    import_migration.add_argument("--output", type=Path)
    migration_status_command = migrate_commands.add_parser(
        "status", help="show local storage migration status"
    )
    migration_status_command.add_argument("--database", type=Path)
    migration_status_command.add_argument("--json", action="store_true")
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
    print(f"target: {target_path.relative_to(project_dir).as_posix()}")
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


def _control_plane_client() -> ControlPlaneClient:
    return ControlPlaneClient(_env("RONIN_CONTROL_PLANE_URL", "http://127.0.0.1:8081"), _token())


def _parse_params(values: Sequence[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in values:
        key, separator, raw = value.partition("=")
        if not separator or not key or key != key.strip() or key in result:
            raise CliError(
                "--param values must be unique KEY=VALUE pairs with non-empty trimmed keys"
            )
        try:
            json.loads(raw)
        except json.JSONDecodeError:
            parsed: object = raw
        else:
            try:
                parsed = decode_canonical_json(raw)
            except (TypeError, ValueError) as exc:
                raise CliError("--param JSON values must use canonical finite JSON") from exc
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


def _evidence(namespace: argparse.Namespace) -> int:
    items = _client().evidence(cast(str, namespace.job_id))
    for item in items:
        if cast(bool, namespace.json):
            print(json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            continue
        digest = item["digest"]
        digest_text = "-" if digest is None else str(digest)[:12]
        size = item["size_bytes"]
        print(
            f"{item['cell_id']}\t{item['role']}\t{item['availability']}\t"
            f"{digest_text}\t{size if size is not None else '-'}"
        )
    return 0


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


def _emit_control_result(result: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return
    items = result.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                identifier = item.get("id", item.get("project_id", ""))
                label = item.get("name", item.get("status", ""))
                print(f"{identifier}\t{label}")
        if result.get("next_cursor") is not None:
            print(f"next_cursor\t{result['next_cursor']}")
        return
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def _read_json_object_file(path: Path, label: str) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise CliError(f"{label} is not a file: {resolved}")
    if resolved.stat().st_size > 8 * 1024 * 1024:
        raise CliError(f"{label} exceeds the 8 MiB CLI limit: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CliError(f"{label} must contain valid UTF-8 JSON: {resolved}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"{label} must contain a JSON object: {resolved}")
    return payload


def _write_new_file(path: Path, content: bytes, label: str) -> Path:
    target = path.resolve()
    if target.exists():
        raise CliError(f"refusing to overwrite {label}: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(content)
    except OSError as exc:
        raise CliError(f"cannot write {label}: {target}") from exc
    return target


def _workspaces(namespace: argparse.Namespace) -> int:
    client = _control_plane_client()
    command = cast(str, namespace.workspaces_command)
    if command == "list":
        result = client.list_workspaces(limit=cast(int, namespace.limit), cursor=namespace.cursor)
    elif command == "get":
        result = client.get_workspace(cast(str, namespace.workspace_id))
    elif command == "create":
        result = client.create_workspace(
            cast(str, namespace.workspace_id),
            cast(str, namespace.name),
            cast(str | None, namespace.description),
            idempotency_key=cast(str, namespace.idempotency_key),
        )
    elif command == "archive":
        result = client.archive_workspace(cast(str, namespace.workspace_id))
    else:
        raise CliError(f"unsupported workspaces command: {command}")
    _emit_control_result(result, as_json=bool(namespace.json))
    return 0


def _projects(namespace: argparse.Namespace) -> int:
    client = _control_plane_client()
    command = cast(str, namespace.projects_command)
    workspace_id = cast(str, namespace.workspace_id)
    project_id = cast(str | None, getattr(namespace, "project_id", None))
    if command == "list":
        result = client.list_projects(
            workspace_id, limit=cast(int, namespace.limit), cursor=namespace.cursor
        )
        _emit_control_result(result, as_json=bool(namespace.json))
        return 0
    if command == "get":
        result = client.get_project(workspace_id, cast(str, project_id))
    elif command == "create":
        result = client.create_project(
            workspace_id,
            _read_json_object_file(cast(Path, namespace.manifest), "project manifest"),
            idempotency_key=cast(str | None, namespace.idempotency_key),
        )
    elif command == "update":
        result = client.update_project(
            workspace_id,
            cast(str, project_id),
            _read_json_object_file(cast(Path, namespace.manifest), "project manifest"),
            if_match=cast(str | None, namespace.if_match),
        )
    elif command == "archive":
        result = client.archive_project(
            workspace_id,
            cast(str, project_id),
            idempotency_key=cast(str, namespace.idempotency_key),
        )
    elif command == "delete":
        result = client.delete_project(workspace_id, cast(str, project_id))
    elif command == "bundle-export":
        output = cast(Path | None, namespace.output)
        if cast(str, namespace.format) == "manifest":
            manifest = client.export_project_bundle_manifest(workspace_id, cast(str, project_id))
            if output is None:
                print(
                    json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                )
            else:
                target = _write_new_file(
                    output,
                    (
                        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
                    ).encode("utf-8"),
                    "project manifest export",
                )
                print(f"project manifest written: {target}")
            return 0
        if output is None:
            raise CliError("projects bundle-export --format archive requires --output")
        archive = client.export_project_bundle_archive(workspace_id, cast(str, project_id))
        target = _write_new_file(output, archive, "project Bundle export")
        print(f"project Bundle written: {target}")
        return 0
    elif command == "bundle-import":
        archive_path = cast(Path, namespace.archive).resolve(strict=True)
        if not archive_path.is_file():
            raise CliError(f"project Bundle archive is not a file: {archive_path}")
        if archive_path.stat().st_size > 8 * 1024 * 1024:
            raise CliError(f"project Bundle archive exceeds the 8 MiB CLI limit: {archive_path}")
        result = client.import_project_bundle_archive(
            workspace_id,
            cast(str, project_id),
            archive_path.read_bytes(),
            idempotency_key=cast(str, namespace.idempotency_key),
        )
    else:
        raise CliError(f"unsupported projects command: {command}")
    _emit_control_result(result, as_json=bool(namespace.json))
    return 0


def _catalog(namespace: argparse.Namespace) -> int:
    client = _control_plane_client()
    command = cast(str, namespace.catalog_command)
    workspace_id = cast(str, namespace.workspace_id)
    if command == "assets":
        result = client.list_catalog_assets(
            workspace_id,
            query=cast(str | None, namespace.query),
            limit=cast(int, namespace.limit),
            cursor=cast(str | None, namespace.cursor),
        )
    elif command == "lineage":
        result = client.list_catalog_lineage(
            workspace_id,
            cast(str, namespace.asset_id),
            cast(str, namespace.version),
            direction=cast(str, namespace.direction),
            limit=cast(int, namespace.limit),
        )
    elif command == "revisions":
        result = client.list_catalog_revisions(workspace_id, cast(str, namespace.asset_id))
    elif command == "revision":
        result = client.get_catalog_revision(
            workspace_id,
            cast(str, namespace.asset_id),
            cast(str, namespace.version),
        )
    else:
        raise CliError(f"unsupported catalog command: {command}")
    _emit_control_result(result, as_json=bool(namespace.json))
    return 0


def _ontology(namespace: argparse.Namespace) -> int:
    client = _control_plane_client()
    command = cast(str, namespace.ontology_command)
    workspace_id = cast(str, namespace.workspace_id)
    if command == "versions":
        result = client.list_ontology_versions(workspace_id, cast(str, namespace.ontology_id))
    elif command == "schema":
        result = client.get_ontology_schema(
            workspace_id,
            cast(str, namespace.ontology_id),
            cast(str, namespace.version),
        )
    else:
        raise CliError(f"unsupported ontology command: {command}")
    _emit_control_result(result, as_json=bool(namespace.json))
    return 0


def _graph_key(raw: str) -> list[object]:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CliError("graph key must be valid JSON") from exc
    if not isinstance(value, list):
        raise CliError("graph key must be a JSON array")
    return cast(list[object], value)


def _graphs(namespace: argparse.Namespace) -> int:
    client = _control_plane_client()
    command = cast(str, namespace.graphs_command)
    workspace_id = cast(str, namespace.workspace_id)
    graph_id = cast(str, namespace.graph_id)
    if command == "query":
        result = client.query_graph(
            workspace_id,
            graph_id,
            cast(str, namespace.query),
            max_limit=cast(int, namespace.max_limit),
        )
    elif command == "objects":
        result = client.list_graph_objects(
            workspace_id,
            graph_id,
            cast(str, namespace.object_type),
            limit=cast(int, namespace.limit),
        )
    elif command == "neighbors":
        result = client.graph_neighbors(
            workspace_id,
            graph_id,
            cast(str, namespace.object_type),
            _graph_key(cast(str, namespace.key_json)),
            limit=cast(int, namespace.limit),
        )
    else:
        raise CliError(f"unsupported graphs command: {command}")
    _emit_control_result(result, as_json=bool(namespace.json))
    return 0


def _quality(namespace: argparse.Namespace) -> int:
    client = _control_plane_client()
    command = cast(str, namespace.quality_command)
    workspace_id = cast(str, namespace.workspace_id)
    if command == "contract":
        contract_command = cast(str, namespace.quality_contract_command)
        asset_id = cast(str, namespace.asset_id)
        version = cast(str, namespace.version)
        if contract_command == "get":
            result = client.get_quality_contract(workspace_id, asset_id, version)
        elif contract_command == "put":
            result = client.put_quality_contract(
                workspace_id,
                asset_id,
                version,
                _read_json_object_file(cast(Path, namespace.contract), "quality contract"),
            )
        else:
            raise CliError(f"unsupported quality contract command: {contract_command}")
    elif command == "run":
        result = client.run_quality(
            workspace_id,
            _read_json_object_file(cast(Path, namespace.request), "quality run request"),
        )
    elif command == "history":
        result = client.list_quality_runs(
            workspace_id, cast(str, namespace.asset_id), cast(str, namespace.version)
        )
    elif command == "state":
        result = client.get_quality_state(
            workspace_id, cast(str, namespace.asset_id), cast(str, namespace.version)
        )
    else:
        raise CliError(f"unsupported quality command: {command}")
    _emit_control_result(result, as_json=bool(namespace.json))
    return 0


def _connectors(namespace: argparse.Namespace) -> int:
    client = _control_plane_client()
    command = cast(str, namespace.connectors_command)
    workspace_id = cast(str | None, namespace.workspace_id)
    if command == "capabilities":
        result = client.connector_capabilities()
    else:
        if workspace_id is None or not workspace_id.strip():
            raise CliError(f"connectors {command} requires --workspace-id or RONIN_WORKSPACE_ID")
    if command == "discover":
        connector_id = cast(str | None, namespace.connector_id)
        connection_ref = cast(str | None, namespace.connection_ref)
        if connector_id is None or connection_ref is None:
            raise CliError("connectors discover requires --connector-id and --connection-ref")
        result = client.connector_discover(
            cast(str, workspace_id),
            connector_id,
            connection_ref,
            cursor=cast(str | None, namespace.cursor),
            page_size=cast(int | None, namespace.page_size),
        )
    elif command == "sync-submit":
        project_id = cast(str | None, namespace.project_id)
        definition_file = cast(Path | None, namespace.definition_file)
        idempotency_key = cast(str | None, namespace.idempotency_key)
        if project_id is None:
            raise CliError("connectors sync-submit requires --project-id")
        if definition_file is None:
            raise CliError("connectors sync-submit requires --definition-file")
        if idempotency_key is None:
            raise CliError("connectors sync-submit requires --idempotency-key")
        try:
            if definition_file.stat().st_size > 1024 * 1024:
                raise CliError("connector definition file exceeds the 1 MiB CLI limit")
            definition = json.loads(definition_file.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CliError(f"cannot read connector definition file: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CliError("connector definition file must contain valid JSON") from exc
        except UnicodeDecodeError as exc:
            raise CliError("connector definition file must use UTF-8 encoding") from exc
        if not isinstance(definition, dict):
            raise CliError("connector definition file must contain a JSON object")
        result = client.connector_sync_submit(
            cast(str, workspace_id),
            project_id,
            definition,
            idempotency_key=idempotency_key,
        )
    elif command in {"sync-status", "sync-cancel"}:
        project_id = cast(str | None, namespace.project_id)
        job_id = cast(str | None, namespace.job_id)
        if project_id is None:
            raise CliError(f"connectors {command} requires --project-id")
        if job_id is None:
            raise CliError(f"connectors {command} requires --job-id")
        operation = (
            client.connector_sync_status
            if command == "sync-status"
            else client.connector_sync_cancel
        )
        result = operation(cast(str, workspace_id), project_id, job_id)
    elif command == "checkpoint-health":
        identity = cast(str | None, namespace.checkpoint_identity)
        if identity is None:
            raise CliError("connectors checkpoint-health requires --checkpoint-identity")
        result = client.connector_checkpoint_health(cast(str, workspace_id), identity)
    elif command in {"preview", "plan"}:
        names = (
            "connector_id",
            "connection_ref",
            "asset_ref",
            "destination_ref",
            "checkpoint_identity",
        )
        values = {name: getattr(namespace, name) for name in names}
        missing = [f"--{name.replace('_', '-')}" for name, value in values.items() if value is None]
        if missing:
            raise CliError(f"connectors {command} requires {', '.join(missing)}")
        payload = {**values, "mode": cast(str, namespace.mode)}
        result = (
            client.connector_preview(cast(str, workspace_id), payload)
            if command == "preview"
            else client.connector_plan(cast(str, workspace_id), payload)
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0


def _migration_inventory(namespace: argparse.Namespace) -> int:
    source = namespace.source.resolve(strict=True)
    if not source.is_file():
        raise CliError(f"migration source is not a file: {source}")
    if source.stat().st_size > 16 * 1024 * 1024:
        raise CliError("migration source exceeds the 16 MiB CLI inspection limit")
    document = _read_text(source, "migration source")
    discover = {
        "databricks": discover_databricks,
        "fabric": discover_fabric,
        "dataiku": discover_dataiku,
        "foundry": discover_foundry,
    }[namespace.platform]
    report = discover(document, source_version=namespace.source_version)
    output = report.to_json() + "\n"
    if namespace.output is None:
        print(output, end="")
    else:
        namespace.output.resolve().write_text(output, encoding="utf-8", newline="\n")
        print(f"migration report written: {namespace.output.resolve()}")
    return 0


def _migration_adapters() -> int:
    payload = {
        "items": [
            {
                "adapter_id": "iics",
                "adapter_version": IICS_ADAPTER_VERSION,
                "capabilities": ["discover", "scope", "generate"],
            }
        ]
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


def _migration_artifact(namespace: argparse.Namespace) -> int:
    source = cast(Path, namespace.source).resolve(strict=True)
    if not source.is_file():
        raise CliError(f"source artifact is not a file: {source}")
    content = source.read_bytes()
    media_type = cast(str, namespace.media_type)
    if not media_type or media_type != media_type.strip():
        raise CliError("--media-type must be non-empty and trimmed")
    payload = {
        "name": cast(str, namespace.name),
        "digest": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "media_type": media_type,
        "execution": "not_run",
    }
    output = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    if namespace.output is None:
        print(output, end="")
    else:
        target = cast(Path, namespace.output).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8", newline="\n")
        print(f"artifact descriptor written: {target}")
    return 0


def _migration_status(namespace: argparse.Namespace) -> int:
    database = (namespace.database or _database()).expanduser().resolve()
    if not database.is_file():
        raise CliError(f"database does not exist: {database}")
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise CliError(f"unable to open database read-only: {database}") from exc
    try:
        rows = migration_status(connection)
    finally:
        connection.close()
    if namespace.json:
        print(json.dumps(rows, sort_keys=True, separators=(",", ":")))
    else:
        for row in rows:
            print(f"{row['domain']}\t{row['current']}\t{row['supported']}\t{row['state']}")
    return 0


def _now() -> Instant:
    return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _database() -> Path:
    return Path(_env("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()


def _sql_engine_from_environment() -> DuckDbSqlEngine | None:
    raw_root = os.environ.get("RONIN_SQL_PARQUET_ROOT")
    if raw_root is None or not raw_root.strip():
        return None
    root = Path(raw_root).expanduser().resolve()
    if not root.is_dir():
        raise CliError("RONIN_SQL_PARQUET_ROOT must reference an existing directory")
    try:
        engine = DuckDbSqlEngine()
    except DuckDbDependencyError as exc:
        raise CliError(str(exc)) from exc
    try:
        for path in sorted(root.glob("*.parquet")):
            engine.register_parquet(path.stem, str(path))
    except Exception:
        engine.close()
        raise
    return engine


def _serve() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if os.environ.get("RONIN_SERVER_PROFILE", "single") == "local-composed":
        return _serve_local_composed()
    storage_backend = os.environ.get("RONIN_STORAGE_BACKEND", "sqlite").strip().lower()
    if storage_backend not in {"sqlite", "postgres"}:
        raise CliError("RONIN_STORAGE_BACKEND must be sqlite or postgres")
    postgres_dsn = os.environ.get("RONIN_POSTGRES_DSN")
    readiness_probe: Callable[[], bool] | None = None
    try:
        port = int(_env("RONIN_PORT", "8080"))
    except ValueError as exc:
        raise CliError("RONIN_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise CliError("RONIN_PORT must be between 1 and 65535")
    database = _database()
    database.parent.mkdir(parents=True, exist_ok=True)
    job_store: JobStore
    if storage_backend == "postgres" and postgres_dsn is None:
        raise CliError("RONIN_POSTGRES_DSN is required for PostgreSQL storage")
    if postgres_dsn is not None and not postgres_dsn.strip():
        raise CliError("RONIN_POSTGRES_DSN must be non-empty and trimmed")
    if storage_backend == "postgres" or postgres_dsn is not None:
        try:
            dsn = cast(str, postgres_dsn)
            postgres_metadata = PostgresMetadataStore(dsn, application_name="ronin-server")
            job_store = PostgresJobReadPort(dsn, application_name="ronin-server")

            def readiness_probe() -> bool:
                return _postgres_ready(postgres_metadata)

        except Exception as exc:
            raise CliError(f"PostgreSQL backend initialization failed: {exc}") from exc
    else:
        job_store = SqliteJobStore(database, migration_now=_now())
    service = DurableExecutionService(job_store)
    sql_engine = _sql_engine_from_environment()
    server = RoninHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), port),
        service,
        token=_token(),
        grants=_token_grants(),
        sql_engine=sql_engine,
        readiness_probe=readiness_probe,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if sql_engine is not None:
            sql_engine.close()
    return 0


def _serve_local_composed() -> int:
    """Run the opt-in jobs plus control-plane local composition."""
    from threading import Event

    from studio_execution.scheduler_daemon import install_scheduler_stop_signals

    from .local_composed import build_local_composed_from_env

    composition = build_local_composed_from_env()
    composition.start()
    stopped = Event()
    restore_signals = install_scheduler_stop_signals(stopped.set)
    try:
        stopped.wait()
    except KeyboardInterrupt:
        return 130
    finally:
        restore_signals()
        composition.stop()
    return 0


def _postgres_ready(metadata: PostgresMetadataStore) -> bool:
    """Probe the configured PostgreSQL connection through the metadata adapter."""
    return metadata.ready()


def _worker() -> int:
    config = _worker_config_from_environment()

    async def run() -> None:
        async with LocalWorkerRuntime(config, migration_now=_now()) as runtime:
            await runtime.run_until_signalled()

    asyncio.run(run())
    return 0


def _worker_config_from_environment() -> LocalWorkerRuntimeConfig:
    """Build a worker config using the same durable backend as the server."""

    storage_backend = os.environ.get("RONIN_STORAGE_BACKEND", "sqlite").strip().lower()
    if storage_backend not in {"sqlite", "postgres"}:
        raise CliError("RONIN_STORAGE_BACKEND must be sqlite or postgres")
    postgres_dsn = os.environ.get("RONIN_POSTGRES_DSN")
    if storage_backend == "postgres" and postgres_dsn is None:
        raise CliError("RONIN_POSTGRES_DSN is required for PostgreSQL storage")
    if postgres_dsn is not None and (not postgres_dsn or postgres_dsn != postgres_dsn.strip()):
        raise CliError("RONIN_POSTGRES_DSN must be non-empty and trimmed")
    database = _database()
    workspace = Path(_env("RONIN_WORKSPACE", ".")).expanduser().resolve()
    excluded_targets = tuple(
        target.strip()
        for target in os.environ.get("RONIN_WORKER_EXCLUDED_TARGETS", "ml-studio.execute").split(
            ","
        )
        if target.strip()
    )
    queryflux_runner = _queryflux_runner_from_environment(database, postgres_dsn)
    try:
        lease_seconds = int(os.environ.get("RONIN_WORKER_LEASE_SECONDS", "30"))
    except ValueError as exc:
        raise CliError("RONIN_WORKER_LEASE_SECONDS must be an integer") from exc
    if lease_seconds < 2:
        raise CliError("RONIN_WORKER_LEASE_SECONDS must be at least 2")
    try:
        heartbeat_interval = float(os.environ.get("RONIN_WORKER_HEARTBEAT_INTERVAL_SECONDS", "10"))
    except ValueError as exc:
        raise CliError("RONIN_WORKER_HEARTBEAT_INTERVAL_SECONDS must be numeric") from exc
    if not 0 < heartbeat_interval < lease_seconds:
        raise CliError(
            "RONIN_WORKER_HEARTBEAT_INTERVAL_SECONDS must be positive and shorter than the lease"
        )
    return LocalWorkerRuntimeConfig(
        paths=WorkerPaths(workspace, database.parent),
        owner=_env("RONIN_WORKER_OWNER", f"worker-{os.getpid()}"),
        image=_env("RONIN_IMAGE"),
        database_name=database.name,
        postgres_dsn=postgres_dsn,
        connector_workspace_id=os.environ.get("RONIN_WORKSPACE_ID"),
        excluded_targets=excluded_targets,
        queryflux_runner=queryflux_runner,
        lease_seconds=lease_seconds,
        heartbeat_interval_seconds=heartbeat_interval,
    )


class _LoopbackQueryFluxHttpClient:
    """Small JSON client restricted to the explicitly configured provider URL."""

    def request(self, method: str, url: str, *, body: str | None = None) -> dict[str, object]:
        request = urllib.request.Request(  # noqa: S310
            url,
            data=body.encode("utf-8") if body is not None else None,
            method=method,
            headers={
                "Content-Type": "text/plain",
                "X-Trino-User": "ronin-worker",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("QueryFlux provider response must be a JSON object")
        return payload


def _queryflux_runner_from_environment(
    database: Path, postgres_dsn: str | None
) -> Callable[..., dict[str, object]] | None:
    base_url = os.environ.get("RONIN_QUERYFLUX_URL")
    if not base_url:
        return None
    if not base_url.endswith("/") or not base_url.startswith(("http://", "https://")):
        raise CliError("RONIN_QUERYFLUX_URL must be an HTTP(S) URL ending with '/'")
    provider_version = os.environ.get("RONIN_QUERYFLUX_PROVIDER_VERSION", "configured")
    provider = QueryEngineRuntimeProvider(
        DiscoveredEngine(
            EngineHandshake(
                "queryflux",
                provider_version,
                EngineCapabilities((("cancel", True), ("parameter_binding", True))),
                True,
            ),
            ("trino",),
            "ready",
        ),
        QueryExecutionPolicy((("queryflux", ("trino",)),), required_capability="cancel"),
    )
    transport = QueryFluxTrinoTransport(_LoopbackQueryFluxHttpClient(), base_url=base_url)
    artifacts = LocalArtifactStore(database.parent / "artifacts")
    references = (
        PostgresQueryEvidenceReferenceStore(postgres_dsn)
        if postgres_dsn is not None
        else SqliteQueryEvidenceReferenceStore(database)
    )
    executions = (
        PostgresQueryFluxExecutionStore(postgres_dsn)
        if postgres_dsn is not None
        else SqliteQueryFluxExecutionStore(database)
    )
    return QueryFluxWorkerRunner(provider, transport, artifacts, references, executions)


def _migration_iics_discover(namespace: argparse.Namespace) -> int:
    archives: list[tuple[str, bytes]] = []
    for raw_path in sorted(cast(Sequence[Path], namespace.archive), key=lambda item: item.name):
        path = raw_path.resolve(strict=True)
        if not path.is_file() or path.suffix.casefold() != ".zip":
            raise CliError(f"IICS artifact must be a ZIP file: {path}")
        if path.stat().st_size > 512 * 1024 * 1024:
            raise CliError(f"IICS artifact exceeds the 512 MiB limit: {path}")
        archives.append((path.name, path.read_bytes()))
    inventory = discover_iics_zip(archives)
    selected = set(cast(Sequence[str], namespace.select))
    if selected:
        unknown = selected - {unit.key for unit in inventory.units}
        if unknown:
            raise CliError(f"unknown IICS migration unit(s): {sorted(unknown)}")
    payload = {
        "adapter_id": inventory.adapter_id,
        "adapter_version": inventory.adapter_version,
        "inventory_digest": inventory.digest,
        "artifacts": [
            {
                "name": item.name,
                "digest": item.digest,
                "size_bytes": item.size_bytes,
                "media_type": item.media_type,
            }
            for item in inventory.artifacts
        ],
        "units": [
            {
                "key": unit.key,
                "kind": unit.kind,
                "name": unit.name,
                "state": unit.state,
                "dependencies": list(unit.dependencies),
                "source_refs": list(unit.source_refs),
                "notes": list(unit.notes),
            }
            for unit in inventory.units
        ],
        "selected": sorted(selected),
    }
    output = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    if namespace.output is None:
        print(output, end="")
    else:
        target = namespace.output.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8", newline="\n")
        print(f"migration inventory written: {target}")
    return 0


def _load_result_rows(path: Path, label: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(_read_text(path.resolve(strict=True), label))
    except json.JSONDecodeError as exc:
        raise CliError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise CliError(f"{label} must be a JSON array of objects: {path}")
    return cast(list[dict[str, object]], payload)


def _load_migration_inventory(path: Path) -> SourceInventory:
    try:
        payload = json.loads(_read_text(path.resolve(strict=True), "migration inventory"))
    except json.JSONDecodeError as exc:
        raise CliError(f"migration inventory is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CliError("migration inventory root must be an object")
    try:
        artifacts = tuple(
            SourceArtifact(
                str(item["name"]),
                str(item["digest"]),
                int(cast(int | str, item["size_bytes"])),
                str(item.get("media_type", "application/octet-stream")),
            )
            for item in cast(list[dict[str, object]], payload["artifacts"])
        )
        units = tuple(
            MigrationUnit(
                str(item["key"]),
                str(item["kind"]),
                str(item["name"]),
                cast(Literal["ready", "review_required", "unsupported"], str(item["state"])),
                tuple(cast(list[str], item.get("dependencies", []))),
                tuple(cast(list[str], item.get("source_refs", []))),
                tuple(cast(list[str], item.get("notes", []))),
            )
            for item in cast(list[dict[str, object]], payload["units"])
        )
        return SourceInventory(
            str(payload["adapter_id"]), str(payload["adapter_version"]), artifacts, units
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CliError(f"invalid migration inventory: {exc}") from exc


def _migration_generate(namespace: argparse.Namespace) -> int:
    inventory = _load_migration_inventory(cast(Path, namespace.inventory))
    requested = tuple(cast(Sequence[str], namespace.select))
    try:
        selection = select_scope(inventory, requested) if requested else select_all(inventory)
        blueprint = (
            extract_blueprint(_read_text(cast(Path, namespace.blueprint), "blueprint"))
            if namespace.blueprint
            else None
        )
        project = generate_project(inventory=inventory, selection=selection, blueprint=blueprint)
    except (TypeError, ValueError) as exc:
        raise CliError(f"cannot generate migration project: {exc}") from exc
    output_dir = cast(Path, namespace.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    for program in project.files:
        target = output_dir / program.path
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise CliError(f"refusing to overwrite generated file: {target}")
        target.write_text(program.content, encoding="utf-8", newline="\n")
    manifest = output_dir / "manifest.json"
    if manifest.exists():
        raise CliError(f"refusing to overwrite generated manifest: {manifest}")
    manifest.write_text(project.manifest + "\n", encoding="utf-8", newline="\n")
    print(f"migration project written: {output_dir}")
    return 0


def _migration_export(namespace: argparse.Namespace) -> int:
    project_dir = cast(Path, namespace.project).resolve(strict=True)
    manifest_path = project_dir / "manifest.json"
    try:
        manifest = json.loads(_read_text(manifest_path, "generated migration manifest"))
        programs = tuple(
            GeneratedProgram(
                str(path),
                _read_text(project_dir / str(path), "generated migration program"),
                cast(str | None, manifest.get("blueprint_digest")),
            )
            for path in cast(list[object], manifest["files"])
        )
        project = GeneratedProject(
            programs,
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            str(manifest["inventory_digest"]),
            str(manifest["scope_digest"]),
            cast(str | None, manifest.get("blueprint_digest")),
            hashlib.sha256(
                (
                    json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                    + "\n"
                    + "\n".join(program.content for program in programs)
                ).encode()
            ).hexdigest(),
        )
        exported = export_migration_script(project)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise CliError(f"cannot export migration project: {exc}") from exc
    output = cast(Path, namespace.output).resolve()
    if output.exists():
        raise CliError(f"refusing to overwrite export: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(exported.content, encoding="utf-8", newline="\n")
    print(f"portable migration script written: {output}")
    return 0


def _migration_qualify(namespace: argparse.Namespace) -> int:
    project_dir = cast(Path, namespace.project).resolve(strict=True)
    files = tuple(sorted(project_dir.rglob("*.py")))
    if not files:
        raise CliError(f"generated project contains no Python files: {project_dir}")
    findings = tuple(
        item for path in files for item in analyze_pyspark(_read_text(path, "generated PySpark"))
    )
    payload = {
        "schema": "ronin.migration.generated-qualification/v1",
        "project": str(project_dir),
        "files_checked": len(files),
        "status": "failed"
        if any(item.severity == "error" for item in findings)
        else "review_required"
        if findings
        else "passed",
        "findings": [item.to_payload() for item in findings],
    }
    output = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    if namespace.output is None:
        print(output, end="")
    else:
        target = cast(Path, namespace.output).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8", newline="\n")
        print(f"qualification report written: {target}")
    return 1 if payload["status"] == "failed" else 0


def _migration_validate(namespace: argparse.Namespace) -> int:
    tolerances: dict[str, float] = {}
    for raw in cast(Sequence[str], namespace.tolerance):
        column, separator, value = raw.partition("=")
        if not separator or not column or column in tolerances:
            raise CliError("--tolerance values must be unique COLUMN=VALUE pairs")
        try:
            parsed = float(value)
        except ValueError as exc:
            raise CliError(f"invalid tolerance: {raw}") from exc
        if parsed < 0:
            raise CliError("tolerances must be non-negative")
        tolerances[column] = parsed
    requested_modes = cast(Sequence[str], namespace.mode)
    modes = tuple(dict.fromkeys(requested_modes or ("schema", "counts", "multiset")))
    report = validate_results(
        _load_result_rows(cast(Path, namespace.expected), "expected result"),
        _load_result_rows(cast(Path, namespace.actual), "actual result"),
        asset_id=cast(str, namespace.asset_id),
        level=cast(Literal["simple", "full"], str(namespace.level)),
        modes=cast(tuple[Literal["schema", "counts", "multiset", "keyed"], ...], modes),
        key_columns=tuple(cast(Sequence[str], namespace.key)),
        tolerances=tolerances,
    )
    report_format = cast(str, namespace.format)
    output = {
        "json": report.to_json() + "\n",
        "markdown": render_validation_markdown(report),
        "html": render_validation_html(report),
    }[report_format]
    if namespace.output is None:
        print(output, end="")
    else:
        target = namespace.output.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8", newline="\n")
        print(f"validation report written: {target}")
    return 0 if report.status == "pass" else 1


def _migration_promote(namespace: argparse.Namespace) -> int:
    def load_benchmark(path: Path, label: str) -> BenchmarkResult:
        payload = json.loads(_read_text(path.resolve(strict=True), label))
        if not isinstance(payload, dict):
            raise CliError(f"{label} must contain a benchmark object")
        try:
            return BenchmarkResult(
                payload["name"],
                payload["warmup_runs"],
                payload["measured_runs"],
                tuple(payload["durations_ms"]),
                payload["median_ms"],
                payload["fingerprint"],
                payload.get("runtime_build_fingerprint"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CliError(f"{label} has invalid benchmark fields") from exc

    baseline = load_benchmark(cast(Path, namespace.baseline), "baseline benchmark")
    candidate = load_benchmark(cast(Path, namespace.candidate), "candidate benchmark")
    decision = decide_promotion(
        cast(str, namespace.candidate_id),
        baseline=baseline,
        candidate=candidate,
        semantic_passed=cast(bool, namespace.semantic_passed),
        quality_passed=cast(bool, namespace.quality_passed),
        max_regression_ratio=cast(float, namespace.max_regression_ratio),
    )
    payload = promotion_evidence(
        decision,
        baseline=baseline,
        candidate=candidate,
        semantic_passed=cast(bool, namespace.semantic_passed),
        quality_passed=cast(bool, namespace.quality_passed),
    )
    output = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    if namespace.output is None:
        print(output, end="")
    else:
        target = cast(Path, namespace.output).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8", newline="\n")
        print(f"promotion evidence written: {target}")
    return 0 if decision.promoted else 1


def _migration_analyze(namespace: argparse.Namespace) -> int:
    source = cast(Path, namespace.source).resolve(strict=True)
    if not source.is_file() or source.suffix.casefold() != ".py":
        raise CliError(f"PySpark analysis source must be a .py file: {source}")
    findings = analyze_pyspark(_read_text(source, "PySpark source"))
    payload = {
        "source": str(source),
        "status": "fail"
        if any(item.severity == "error" for item in findings)
        else "warn"
        if findings
        else "pass",
        "findings": [item.to_payload() for item in findings],
    }
    output = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    if namespace.output is None:
        print(output, end="")
    else:
        target = namespace.output.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8", newline="\n")
        print(f"analysis report written: {target}")
    return 1 if payload["status"] == "fail" else 0


def _migration_spark_preflight(namespace: argparse.Namespace) -> int:
    evidence = qualify_spark_runtime()
    output = json.dumps(evidence.to_payload(), sort_keys=True, separators=(",", ":")) + "\n"
    if namespace.output is None:
        print(output, end="")
    else:
        target = namespace.output.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8", newline="\n")
        print(f"Spark qualification evidence written: {target}")
    return 0 if evidence.status == "passed" else 1


def _migration_spark_smoke(namespace: argparse.Namespace) -> int:
    evidence = run_spark_smoke()
    output = json.dumps(evidence.to_payload(), sort_keys=True, separators=(",", ":")) + "\n"
    if namespace.output is None:
        print(output, end="")
    else:
        target = namespace.output.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8", newline="\n")
        print(f"Spark smoke evidence written: {target}")
    return 0 if evidence.status == "passed" else 1


def _skills(namespace: argparse.Namespace) -> int:
    root = (getattr(namespace, "root", None) or default_skill_root()).expanduser().resolve()
    skills = discover_skills(root)
    if namespace.skills_command == "list":
        if namespace.json:
            print(render_skills_json(skills))
        else:
            for skill in skills:
                state = "valid" if skill.valid else "invalid"
                print(f"{skill.name}\t{skill.display_name}\t{state}")
        return 0 if skills else 1
    if namespace.skills_command == "validate":
        selected = tuple(
            skill for skill in skills if namespace.name is None or skill.name == namespace.name
        )
        if namespace.name is not None and not selected:
            raise CliError(f"agent skill not found: {namespace.name}")
        payload = {
            "schema": "ronin.agent-skills-validation/v1",
            "root": str(root),
            "valid": all(skill.valid for skill in selected),
            "skills": [skill.to_payload() for skill in selected],
        }
        if namespace.json:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        else:
            for skill in selected:
                print(f"{skill.name}: {'valid' if skill.valid else '; '.join(skill.errors)}")
        return 0 if selected and bool(payload["valid"]) else 1
    if namespace.skills_command == "package":
        selected = tuple(
            skill for skill in skills if namespace.name is None or skill.name == namespace.name
        )
        if namespace.name is not None and not selected:
            raise CliError(f"agent skill not found: {namespace.name}")
        if not selected:
            raise CliError(f"no agent skills found in {root}")
        output = (namespace.output or root / "dist").expanduser().resolve()
        paths = [package_skill(skill, output) for skill in selected]
        print(
            json.dumps(
                {"output": str(output), "packages": [str(path) for path in paths]}, sort_keys=True
            )
        )
        return 0
    if namespace.skills_command == "install":
        selected = tuple(skill for skill in skills if skill.name == namespace.name)
        if not selected:
            raise CliError(f"agent skill not found: {namespace.name}")
        print(
            json.dumps(
                install_skill(selected[0], namespace.destination, dry_run=namespace.dry_run),
                sort_keys=True,
            )
        )
        return 0
    if namespace.skills_command == "uninstall":
        print(
            json.dumps(
                uninstall_skill(namespace.name, namespace.destination, dry_run=namespace.dry_run),
                sort_keys=True,
            )
        )
        return 0
    raise CliError(f"unsupported skills command: {namespace.skills_command}")


def _plugins(namespace: argparse.Namespace) -> int:
    from studio_runtime import PluginHost, PluginLock, PluginLockError

    host = PluginHost.discover()
    diagnostics = host.diagnostics()
    if namespace.plugins_command == "surfaces":
        contributions = host.contribution_diagnostics()
        print(
            json.dumps(
                {
                    "surfaces": contributions["surfaces"],
                    "cli": contributions["cli"],
                    "client_operations": contributions["client_operations"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    if namespace.plugins_command == "validate":
        try:
            lock = PluginLock.read(str(namespace.file))
            host.verify_lock(lock)
        except (OSError, PluginLockError) as exc:
            raise CliError(f"plugin lock validation failed: {exc}") from exc
        print(f"validated {len(diagnostics)} plugin(s) against {namespace.file}")
        return 0
    if namespace.plugins_command == "lock":
        path = namespace.file.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        host.create_lock().write(str(path))
        print(f"plugin lock written: {path}")
        return 0
    if namespace.plugins_command == "rollback":
        if namespace.snapshot is None:
            raise CliError("plugins rollback requires a snapshot path")
        try:
            snapshot = PluginLock.read(str(namespace.snapshot))
        except (OSError, PluginLockError) as exc:
            raise CliError(f"plugin rollback snapshot is invalid: {exc}") from exc
        target = namespace.file.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write(str(target))
        print(f"plugin lock restored: {target}")
        return 0
    for item in diagnostics:
        print(f"{item['id']}\t{item['version']}\t{item['edition']}\t{item['state']}")
    return 0


def _migration_import(namespace: argparse.Namespace) -> int:
    """Validate a generated candidate and emit deterministic import evidence."""
    project_dir = cast(Path, namespace.project).resolve(strict=True)
    try:
        manifest = json.loads(
            _read_text(project_dir / "manifest.json", "generated migration manifest")
        )
        files = tuple(
            (str(path), _read_text(project_dir / str(path), "generated migration program"))
            for path in cast(list[object], manifest["files"])
        )
        manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        project_digest = hashlib.sha256(
            (manifest_json + "\n" + "\n".join(content for _, content in files)).encode()
        ).hexdigest()
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise CliError(f"cannot import migration project: {exc}") from exc
    target = cast(str, namespace.target)
    if not target or target != target.strip():
        raise CliError("import target must be non-empty and trimmed")
    evidence = {
        "schema": "ronin.migration.import-evidence/v1",
        "status": "importable",
        "target": target,
        "project_digest": project_digest,
        "files": [
            {"path": path, "digest": hashlib.sha256(content.encode()).hexdigest()}
            for path, content in files
        ],
    }
    rendered = json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n"
    if namespace.output is None:
        print(rendered, end="")
    else:
        output = cast(Path, namespace.output).resolve()
        if output.exists():
            raise CliError(f"refusing to overwrite import evidence: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"migration import evidence written: {output}")
    return 0


def _artifacts_retention(namespace: argparse.Namespace) -> int:
    result = run_artifact_retention(
        cast(str, namespace.mode),
        confirmed=bool(namespace.confirm),
        allow_empty_live_set=bool(namespace.allow_empty_live_set),
        page_size=cast(int, namespace.page_size),
        max_objects=cast(int, namespace.max_objects),
        max_pages=cast(int, namespace.max_pages),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
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
        if command == "artifacts":
            if namespace.artifacts_command == "retention":
                return _artifacts_retention(namespace)
            raise CliError(f"unsupported artifacts command: {namespace.artifacts_command}")
        if command == "plugins":
            return _plugins(namespace)
        if command == "skills":
            return _skills(namespace)
        if command == "submit":
            return _submit(namespace)
        if command == "status":
            return _status(namespace)
        if command == "logs":
            return _logs(namespace)
        if command == "evidence":
            return _evidence(namespace)
        if command == "jobs":
            return _jobs(namespace)
        if command == "cancel":
            return _cancel(namespace)
        if command == "connectors":
            return _connectors(namespace)
        if command == "workspaces":
            return _workspaces(namespace)
        if command == "projects":
            return _projects(namespace)
        if command == "catalog":
            return _catalog(namespace)
        if command == "ontology":
            return _ontology(namespace)
        if command == "graphs":
            return _graphs(namespace)
        if command == "quality":
            return _quality(namespace)
        if command == "migrate":
            if namespace.migrate_command == "inventory":
                return _migration_inventory(namespace)
            if namespace.migrate_command == "adapters":
                return _migration_adapters()
            if namespace.migrate_command == "artifact":
                return _migration_artifact(namespace)
            if namespace.migrate_command == "iics-discover":
                return _migration_iics_discover(namespace)
            if namespace.migrate_command == "validate":
                return _migration_validate(namespace)
            if namespace.migrate_command == "promote":
                return _migration_promote(namespace)
            if namespace.migrate_command == "analyze":
                return _migration_analyze(namespace)
            if namespace.migrate_command == "spark-preflight":
                return _migration_spark_preflight(namespace)
            if namespace.migrate_command == "spark-smoke":
                return _migration_spark_smoke(namespace)
            if namespace.migrate_command == "generate":
                return _migration_generate(namespace)
            if namespace.migrate_command == "qualify":
                return _migration_qualify(namespace)
            if namespace.migrate_command == "export":
                return _migration_export(namespace)
            if namespace.migrate_command == "import":
                return _migration_import(namespace)
            if namespace.migrate_command == "status":
                return _migration_status(namespace)
            raise CliError(f"unsupported migrate command: {namespace.migrate_command}")
        raise CliError(f"unsupported command: {command}")
    except (CliError, ControlPlaneError, MigrationStatusError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


__all__ = ("CliError", "main")
