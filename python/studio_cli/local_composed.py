"""Composition root for the opt-in local composed HTTP profile."""

from __future__ import annotations

import os
from pathlib import Path

from studio_core import GrantSet, WorkspaceId
from studio_execution import (
    DurableExecutionService,
    ProjectService,
    SqliteWorkflowHTTPAdapter,
    WorkspaceService,
)
from studio_orchestrator import Instant
from studio_server import (
    LocalServerComposition,
    RoninHTTPServer,
    StaticControlPlaneAuthenticator,
    StaticControlPlaneAuthorizer,
    WorkspaceProjectHTTPServer,
)
from studio_storage import SqliteJobStore
from studio_storage.bundle_workflow_import import SqliteWorkflowBundleImportStore


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty and trimmed")
    return value


def _port(name: str, default: str) -> int:
    try:
        value = int(_env(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


def build_local_composed_from_env() -> LocalServerComposition:
    """Build, but do not start, the opt-in two-surface local profile."""

    database = Path(_env("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    now = Instant("2026-09-17T00:00:00.000000Z")
    workspace_id = WorkspaceId(_env("RONIN_WORKSPACE_ID"))
    control_token = _env("RONIN_CONTROL_PLANE_TOKEN")
    raw_permissions = _env(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "scheduler.read,scheduler.write,workspace.read,project.read",
    )
    permissions = frozenset(item.strip() for item in raw_permissions.split(",") if item.strip())
    if not permissions or not permissions <= {
        "scheduler.read",
        "scheduler.write",
        "workspace.read",
        "workspace.admin",
        "project.read",
        "project.write",
    }:
        raise ValueError("RONIN_CONTROL_PLANE_PERMISSIONS contains unsupported permissions")

    job_service = DurableExecutionService(SqliteJobStore(database, migration_now=now))
    try:
        job_grants = GrantSet.from_json(_env("RONIN_TOKEN_SCOPES"))
    except ValueError as exc:
        raise ValueError(f"invalid RONIN_TOKEN_SCOPES: {exc}") from exc
    job_server = RoninHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), _port("RONIN_PORT", "8080")),
        job_service,
        token=_env("RONIN_TOKEN"),
        grants=job_grants,
    )
    scheduler = SqliteWorkflowBundleImportStore(database, migration_now=now)
    control_server = WorkspaceProjectHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), _port("RONIN_CONTROL_PLANE_PORT", "8081")),
        WorkspaceService(scheduler),
        ProjectService(scheduler),
        authenticator=StaticControlPlaneAuthenticator(control_token),
        authorizer=StaticControlPlaneAuthorizer(workspace_id, permissions),
        workflow_reader=SqliteWorkflowHTTPAdapter(scheduler, now=now),
    )
    return LocalServerComposition(job_server, control_server)


__all__ = ("build_local_composed_from_env",)
