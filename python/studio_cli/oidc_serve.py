"""Composition root for the opt-in OIDC `ronin serve` profile."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from studio_core import WorkspaceId
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant
from studio_security import (
    FileJwksProvider,
    JwksFileError,
    OidcConfig,
    OidcTokenValidator,
    SqliteIdentityStore,
)
from studio_server import OidcRoninHTTPServer
from studio_storage import SqliteJobStore, SqliteWorkspaceStore
from studio_storage.audit import SqliteAuditStore


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or not value or value != value.strip():
        raise ValueError(f"{name} must be set to a non-empty trimmed value")
    return value


def _now() -> Instant:
    return Instant(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))


def _database() -> Path:
    return Path(_env("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()


def _port() -> int:
    try:
        port = int(_env("RONIN_PORT", "8080"))
    except ValueError as exc:
        raise ValueError("RONIN_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("RONIN_PORT must be between 1 and 65535")
    return port


def build_oidc_server_from_env() -> OidcRoninHTTPServer:
    """Build but do not start the explicitly configured single-workspace OIDC server."""

    database = _database()
    database.parent.mkdir(parents=True, exist_ok=True)
    now = _now()
    workspace_id = WorkspaceId(_env("RONIN_WORKSPACE_ID"))

    workspaces = SqliteWorkspaceStore(database, migration_now=now)
    workspace = workspaces.get_workspace(workspace_id)
    if workspace is None:
        raise ValueError("RONIN_WORKSPACE_ID must reference a provisioned workspace")
    if workspace.archived:
        raise ValueError("RONIN_WORKSPACE_ID must reference an active workspace")

    provider = FileJwksProvider(Path(_env("RONIN_OIDC_JWKS_FILE")))
    try:
        provider.jwks()
    except JwksFileError as exc:
        raise ValueError(f"invalid RONIN_OIDC_JWKS_FILE: {exc}") from exc
    validator = OidcTokenValidator(
        OidcConfig(
            _env("RONIN_OIDC_ISSUER"),
            _env("RONIN_OIDC_AUDIENCE"),
        ),
        provider,
    )

    identities = SqliteIdentityStore(database)
    audit = SqliteAuditStore(database, migration_now=now)
    service = DurableExecutionService(SqliteJobStore(database, migration_now=now))
    return OidcRoninHTTPServer(
        (_env("RONIN_HOST", "127.0.0.1"), _port()),
        service,
        workspace_id=workspace_id,
        validator=validator,
        principal_store=identities,
        rbac_store=identities,
        workspace_store=workspaces,
        audit_store=audit,
    )


def serve_oidc_from_env() -> int:
    server = build_oidc_server_from_env()
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


__all__ = ("build_oidc_server_from_env", "serve_oidc_from_env")
