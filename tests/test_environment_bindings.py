from __future__ import annotations

from pathlib import Path

import pytest
from studio_core import (
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
    Workspace,
    WorkspaceId,
)
from studio_core.environments import (
    DeploymentBinding,
    EnvironmentDefinition,
    EnvironmentId,
    ProjectEnvironmentBindings,
)
from studio_storage.environments import EnvironmentConflict, SqliteEnvironmentStore
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = "2026-09-12T20:00:00.000000Z"


def _manifest() -> ProjectManifest:
    project = Project(
        id=ProjectId("orders"),
        name="Orders",
        repositories=(
            RepositoryBinding(
                "code",
                "https://git.example.test/orders.git",
                role="primary",
            ),
        ),
        execution=ExecutionProfile(runtime=RuntimeProfileRef("python", "3.11")),
    )
    return ProjectManifest.from_project(project)


def test_environment_and_bindings_round_trip_without_changing_project_manifest() -> None:
    manifest = _manifest()
    environment = EnvironmentDefinition(EnvironmentId("prod"), "Production")
    bindings = ProjectEnvironmentBindings(
        manifest.project.id,
        environment.id,
        (
            DeploymentBinding("secret", "warehouse-password", "secret://env/WAREHOUSE_PASSWORD"),
            DeploymentBinding("connection", "warehouse", "connection://prod-warehouse"),
            DeploymentBinding("runtime", "default-runtime", "runtime://kubernetes/python-311"),
        ),
    )

    assert EnvironmentDefinition.from_json(environment.to_json()) == environment
    assert ProjectEnvironmentBindings.from_json(bindings.to_json()) == bindings
    assert bindings.resolve("secret", "warehouse-password") == "secret://env/WAREHOUSE_PASSWORD"
    assert "WAREHOUSE_PASSWORD" not in manifest.to_json()


def test_binding_targets_require_kind_specific_reference_schemes() -> None:
    with pytest.raises(ValueError, match="secret://"):
        DeploymentBinding("secret", "password", "connection://wrong-kind")
    with pytest.raises(ValueError, match="credential material"):
        DeploymentBinding("endpoint", "service", "endpoint://service/password=cleartext")


def test_sqlite_environment_store_requires_registered_project_and_active_environment(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ronin.db"
    workspace_id = WorkspaceId("workspace-1")
    workspace_store = SqliteWorkspaceStore(database, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Workspace"), now=NOW)
    workspace_store.register_project(workspace_id, _manifest(), now=NOW)

    store = SqliteEnvironmentStore(database, migration_now=NOW)
    environment = EnvironmentDefinition(EnvironmentId("prod"), "Production")
    store.put_environment(workspace_id, environment, now=NOW)
    bindings = ProjectEnvironmentBindings(
        ProjectId("orders"),
        environment.id,
        (DeploymentBinding("storage", "warehouse", "storage://prod/lakehouse"),),
    )
    store.put_project_bindings(workspace_id, bindings, now=NOW)

    assert store.get_environment(workspace_id, environment.id) == environment
    assert store.get_project_bindings(workspace_id, ProjectId("orders"), environment.id) == bindings

    store.put_environment(
        workspace_id,
        EnvironmentDefinition(environment.id, "Production", state="disabled"),
        now=NOW,
    )
    with pytest.raises(EnvironmentConflict, match="disabled"):
        store.put_project_bindings(workspace_id, bindings, now=NOW)
