from __future__ import annotations

import os
from uuid import uuid4

import pytest

from studio_core import (
    ConnectionDefinition,
    ConnectionId,
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    SecretRef,
    Workspace,
    WorkspaceId,
)
from studio_core.environments import (
    DeploymentBinding,
    EnvironmentDefinition,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_orchestrator import Instant
from studio_storage import PostgresMetadataStore

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL qualification requires RONIN_POSTGRES_TEST_DSN",
)


def test_postgres_bundle_multi_object_commit_is_atomic_and_idempotent() -> None:
    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    store = PostgresMetadataStore(dsn, application_name="ronin-bundle-qualification")
    suffix = uuid4().hex
    workspace_id = WorkspaceId(f"bundle-ws-{suffix}")
    project_id = ProjectId(f"bundle-project-{suffix}")
    environment_id = EnvironmentId(f"bundle-env-{suffix}")
    connection_id = ConnectionId(f"bundle-connection-{suffix}")
    now = Instant("2026-09-24T12:00:00.000000Z")
    project = ProjectManifest.from_project(
        Project(
            project_id,
            "Bundle qualification",
            (RepositoryBinding("code", "https://git.example.test/bundle.git", role="primary"),),
            ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
        )
    )
    connection = ConnectionDefinition(
        connection_id,
        "Bundle warehouse",
        "postgresql",
        options=(("host", "db.example.test"),),
        secret_refs=(("password", SecretRef(f"secret://bundle/{suffix}")),),
    )
    bindings = ProjectEnvironmentBindings(
        project_id,
        environment_id,
        (DeploymentBinding("runtime", "runtime-profile:python/3.11", "runtime://python311"),),
    )

    store.create_workspace(Workspace(workspace_id, "Bundle workspace"), now=now)
    store.put_environment(
        workspace_id, EnvironmentDefinition(environment_id, "Bundle env"), now=now
    )
    first = store.commit_multi_object_import(
        workspace_id, (connection,), (project,), (bindings,), now=now
    )
    second = store.commit_multi_object_import(
        workspace_id, (connection,), (project,), (bindings,), now=now
    )

    assert (first.connections_created, first.projects_created, first.bindings_created) == (1, 1, 1)
    assert (second.connections_created, second.projects_created, second.bindings_created) == (
        0,
        0,
        0,
    )
