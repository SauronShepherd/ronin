import json
from dataclasses import FrozenInstanceError

import pytest
from studio_core import (
    PROJECT_MANIFEST_PATH,
    PROJECT_MANIFEST_SCHEMA,
    CapabilityRequirement,
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
)


def _workspace_project() -> Project:
    return Project(
        id=ProjectId("orders"),
        name="Orders",
        repositories=(
            RepositoryBinding(
                "docs",
                "../shared/docs",
                adapter_id="git",
                sync_policy="fetch",
            ),
            RepositoryBinding(
                "code",
                "https://git.example.test/data/orders.git",
                role="primary",
                default_ref="develop",
                auth_ref="connection://team-git",
                subdirectory="products/orders",
                adapter_id="git",
                sync_policy="fast-forward",
            ),
        ),
        execution=ExecutionProfile(
            runtime=RuntimeProfileRef("runtime-adapter", "team-default"),
            requirements=(
                CapabilityRequirement("python.version", ">=3.11"),
                CapabilityRequirement("gpu", level="preferred"),
            ),
            resolution="compatible",
        ),
    )


def _portable_data() -> dict[str, object]:
    return ProjectManifest.from_project(_workspace_project()).to_data()


def test_manifest_constants_and_immutability() -> None:
    manifest = ProjectManifest.from_project(_workspace_project())
    assert PROJECT_MANIFEST_PATH == ".ronin/project.json"
    assert PROJECT_MANIFEST_SCHEMA == "ronin.project/v1"
    with pytest.raises(FrozenInstanceError):
        manifest.schema = "changed"  # type: ignore[misc]


def test_manifest_from_project_strips_auth_and_preserves_portable_intent() -> None:
    workspace = _workspace_project()
    manifest = ProjectManifest.from_project(workspace)
    assert workspace.primary_repository.auth_ref == "connection://team-git"
    assert all(repository.auth_ref is None for repository in manifest.project.repositories)
    assert manifest.project.primary_repository.adapter_id == "git"
    assert manifest.project.primary_repository.sync_policy == "fast-forward"
    assert manifest.project.execution == workspace.execution


def test_manifest_rejects_unsupported_schema_and_direct_auth_binding() -> None:
    portable = ProjectManifest.from_project(_workspace_project()).project
    with pytest.raises(ValueError, match="unsupported project manifest schema"):
        ProjectManifest(portable, schema="ronin.project/v2")
    with pytest.raises(ValueError, match="auth bindings"):
        ProjectManifest(_workspace_project())


def test_manifest_json_is_canonical_deterministic_and_round_trips() -> None:
    manifest = ProjectManifest.from_project(_workspace_project())
    payload = manifest.to_json()
    assert payload == json.dumps(
        manifest.to_data(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    assert ProjectManifest.from_json(payload) == manifest
    assert [item.alias for item in manifest.project.repositories] == ["code", "docs"]
    assert [item.name for item in manifest.project.execution.requirements] == [
        "gpu",
        "python.version",
    ]
    assert "auth_ref" not in payload
    assert "connection://team-git" not in payload


def test_manifest_supports_capability_only_execution_and_null_values() -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    repositories = project["repositories"]
    assert isinstance(execution, dict)
    assert isinstance(repositories, list)
    execution["runtime"] = None
    execution["requirements"] = [
        {"constraint": None, "level": "required", "name": "sql.execution"}
    ]
    repositories[0]["subdirectory"] = None
    manifest = ProjectManifest.from_data(data)
    assert manifest.project.execution.runtime is None
    assert manifest.project.execution.requirements[0].constraint is None
    assert manifest.project.repositories[0].subdirectory is None


def test_manifest_rejects_top_level_project_and_repository_key_drift() -> None:
    data = _portable_data()
    with pytest.raises(ValueError, match="manifest keys mismatch"):
        ProjectManifest.from_data({"schema": PROJECT_MANIFEST_SCHEMA})

    project = data["project"]
    assert isinstance(project, dict)
    project["future"] = True
    with pytest.raises(ValueError, match="project keys mismatch"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    repositories = project["repositories"]
    assert isinstance(repositories, list)
    repositories[0]["auth_ref"] = "connection://must-stay-local"
    with pytest.raises(ValueError, match="repository keys mismatch"):
        ProjectManifest.from_data(data)


def test_manifest_rejects_execution_runtime_and_requirement_key_drift() -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["future"] = True
    with pytest.raises(ValueError, match="execution keys mismatch"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    runtime = execution["runtime"]
    assert isinstance(runtime, dict)
    runtime["future"] = True
    with pytest.raises(ValueError, match="execution.runtime keys mismatch"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    requirements = execution["requirements"]
    assert isinstance(requirements, list)
    requirements[0]["future"] = True
    with pytest.raises(ValueError, match="requirement keys mismatch"):
        ProjectManifest.from_data(data)


def test_manifest_rejects_invalid_schema_role_sync_resolution_and_level() -> None:
    data = _portable_data()
    data["schema"] = "ronin.project/v99"
    with pytest.raises(ValueError, match="unsupported"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    repositories = project["repositories"]
    assert isinstance(repositories, list)
    repositories[0]["role"] = "owner"
    with pytest.raises(ValueError, match="repository.role"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    repositories = project["repositories"]
    assert isinstance(repositories, list)
    repositories[0]["sync_policy"] = "merge"
    with pytest.raises(ValueError, match="repository.sync_policy"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["resolution"] = "best-effort"
    with pytest.raises(ValueError, match="execution.resolution"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    requirements = execution["requirements"]
    assert isinstance(requirements, list)
    requirements[0]["level"] = "optional"
    with pytest.raises(ValueError, match="requirement.level"):
        ProjectManifest.from_data(data)


def test_manifest_rejects_non_string_optional_values() -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    repositories = project["repositories"]
    assert isinstance(repositories, list)
    repositories[0]["subdirectory"] = 1
    with pytest.raises(TypeError, match="repository.subdirectory"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    requirements = execution["requirements"]
    assert isinstance(requirements, list)
    requirements[0]["constraint"] = 1
    with pytest.raises(TypeError, match="requirement.constraint"):
        ProjectManifest.from_data(data)


def test_manifest_shape_helpers_reject_invalid_objects_arrays_and_strings() -> None:
    with pytest.raises(TypeError, match="manifest must be an object"):
        ProjectManifest.from_json("[]")
    with pytest.raises(TypeError, match="manifest must be an object"):
        ProjectManifest.from_data({1: "bad"})  # type: ignore[dict-item]

    data = _portable_data()
    data["project"] = []
    with pytest.raises(TypeError, match="project must be an object"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    project["repositories"] = "not-an-array"
    with pytest.raises(TypeError, match="repositories must be an array"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    project["repositories"] = ["not-an-object"]
    with pytest.raises(TypeError, match="repository must be an object"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    data["schema"] = 1
    with pytest.raises(TypeError, match="schema must be a string"):
        ProjectManifest.from_data(data)


def test_manifest_rejects_non_array_requirements_and_invalid_runtime_shape() -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["requirements"] = 1
    with pytest.raises(TypeError, match="execution.requirements must be an array"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["runtime"] = []
    with pytest.raises(TypeError, match="execution.runtime must be an object"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["requirements"] = [[]]
    with pytest.raises(TypeError, match="requirement must be an object"):
        ProjectManifest.from_data(data)


def test_repository_binding_validates_adapter_and_sync_policy() -> None:
    repository = RepositoryBinding(
        "code",
        "https://git.example.test/team/code.git",
        role="primary",
        adapter_id="custom-git-adapter",
        sync_policy="fetch",
    )
    assert repository.adapter_id == "custom-git-adapter"
    assert repository.sync_policy == "fetch"
    assert RepositoryBinding(
        "code", "https://git.example.test/team/code.git", role="primary"
    ).sync_policy == "manual"
    with pytest.raises(ValueError, match="adapter id"):
        RepositoryBinding(
            "code",
            "https://git.example.test/team/code.git",
            role="primary",
            adapter_id=" ",
        )
    with pytest.raises(ValueError, match="line breaks"):
        RepositoryBinding(
            "code",
            "https://git.example.test/team/code.git",
            role="primary",
            adapter_id="bad\nadapter",
        )
    with pytest.raises(ValueError, match="sync policy"):
        RepositoryBinding(
            "code",
            "https://git.example.test/team/code.git",
            role="primary",
            sync_policy="rebase",  # type: ignore[arg-type]
        )
