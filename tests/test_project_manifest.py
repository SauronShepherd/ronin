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
    execution["requirements"] = [{"constraint": None, "level": "required", "name": "sql.execution"}]
    repositories[0]["subdirectory"] = None
    manifest = ProjectManifest.from_data(data)
    assert manifest.project.execution.runtime is None
    assert manifest.project.execution.requirements[0].constraint is None
    assert manifest.project.repositories[0].subdirectory is None
    serialized_project = manifest.to_data()["project"]
    assert isinstance(serialized_project, dict)
    serialized_execution = serialized_project["execution"]
    assert isinstance(serialized_execution, dict)
    assert serialized_execution["runtime"] is None


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


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("project", "id"), 1, "project.id"),
        (("project", "name"), None, "project.name"),
        (("project", "repositories", 0, "alias"), 1, "repository.alias"),
        (("project", "repositories", 0, "uri"), [], "repository.uri"),
        (("project", "repositories", 0, "default_ref"), {}, "repository.default_ref"),
        (("project", "repositories", 0, "adapter_id"), 1, "repository.adapter_id"),
        (("project", "execution", "runtime", "adapter_id"), 1, "execution.runtime.adapter_id"),
        (("project", "execution", "runtime", "profile_id"), None, "execution.runtime.profile_id"),
        (("project", "execution", "requirements", 0, "name"), 1, "requirement.name"),
    ],
)
def test_manifest_rejects_non_string_required_fields(
    path: tuple[object, ...], value: object, message: str
) -> None:
    data = _portable_data()
    cursor: object = data
    for key in path[:-1]:
        assert isinstance(cursor, (dict, list))
        cursor = cursor[key]  # type: ignore[index]
    assert isinstance(cursor, (dict, list))
    cursor[path[-1]] = value  # type: ignore[index]
    with pytest.raises(TypeError, match=message):
        ProjectManifest.from_data(data)


def test_manifest_rejects_non_mapping_repository_and_runtime_items() -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    repositories = project["repositories"]
    assert isinstance(repositories, list)
    repositories[0] = {1: "not-a-string-key"}
    with pytest.raises(TypeError, match="repository must be an object"):
        ProjectManifest.from_data(data)

    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["runtime"] = {1: "not-a-string-key"}
    with pytest.raises(TypeError, match="execution.runtime must be an object"):
        ProjectManifest.from_data(data)


@pytest.mark.parametrize("role", ["primary", "supporting"])
@pytest.mark.parametrize("sync_policy", ["manual", "fetch", "fast-forward"])
def test_manifest_accepts_each_declared_repository_policy_variant(
    role: str, sync_policy: str
) -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    repositories = project["repositories"]
    assert isinstance(repositories, list)
    repository = repositories[0]
    assert isinstance(repository, dict)
    repository["role"] = role
    repository["sync_policy"] = sync_policy
    other = repositories[1]
    assert isinstance(other, dict)
    other["role"] = "supporting" if role == "primary" else "primary"
    restored = ProjectManifest.from_data(data)
    assert restored.project.repositories[0].role == role
    assert restored.project.repositories[0].sync_policy == sync_policy


def test_manifest_accepts_preferred_requirement_and_runtime_without_auth() -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["resolution"] = "strict"
    execution["requirements"] = [{"name": "gpu", "constraint": "true", "level": "preferred"}]
    manifest = ProjectManifest.from_data(data)
    assert manifest.project.execution.resolution == "strict"
    assert manifest.project.execution.requirements[0].level == "preferred"


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("project", "id"), 1, "project.id must be a string"),
        (("project", "name"), None, "project.name must be a string"),
        (("project", "repositories", 0, "alias"), 1, "repository.alias must be a string"),
        (("project", "repositories", 0, "uri"), [], "repository.uri must be a string"),
        (
            ("project", "repositories", 0, "default_ref"),
            {},
            "repository.default_ref must be a string",
        ),
        (
            ("project", "repositories", 0, "adapter_id"),
            1,
            "repository.adapter_id must be a string",
        ),
        (
            ("project", "repositories", 0, "subdirectory"),
            1,
            "repository.subdirectory must be a string or null",
        ),
        (
            ("project", "execution", "runtime", "adapter_id"),
            1,
            "execution.runtime.adapter_id must be a string",
        ),
        (
            ("project", "execution", "runtime", "profile_id"),
            None,
            "execution.runtime.profile_id must be a string",
        ),
        (
            ("project", "execution", "requirements", 0, "name"),
            1,
            "requirement.name must be a string",
        ),
        (
            ("project", "execution", "requirements", 0, "constraint"),
            1,
            "requirement.constraint must be a string or null",
        ),
    ],
)
def test_manifest_required_field_errors_are_stable(
    path: tuple[object, ...], value: object, message: str
) -> None:
    data = _portable_data()
    cursor: object = data
    for key in path[:-1]:
        assert isinstance(cursor, (dict, list))
        cursor = cursor[key]  # type: ignore[index]
    assert isinstance(cursor, (dict, list))
    cursor[path[-1]] = value  # type: ignore[index]
    with pytest.raises(TypeError, match=f"^{message}$"):
        ProjectManifest.from_data(data)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (
            ("project", "repositories", 0, "role"),
            "owner",
            "repository.role must be primary or supporting",
        ),
        (
            ("project", "repositories", 0, "sync_policy"),
            "merge",
            "repository.sync_policy must be manual, fetch, or fast-forward",
        ),
        (
            ("project", "execution", "resolution"),
            "best-effort",
            "execution.resolution must be strict or compatible",
        ),
        (
            ("project", "execution", "requirements", 0, "level"),
            "optional",
            "requirement.level must be required or preferred",
        ),
    ],
)
def test_manifest_enum_errors_are_stable(
    path: tuple[object, ...], value: object, message: str
) -> None:
    data = _portable_data()
    cursor: object = data
    for key in path[:-1]:
        assert isinstance(cursor, (dict, list))
        cursor = cursor[key]  # type: ignore[index]
    assert isinstance(cursor, (dict, list))
    cursor[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValueError, match=f"^{message}$"):
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
    assert (
        RepositoryBinding(
            "code", "https://git.example.test/team/code.git", role="primary"
        ).sync_policy
        == "manual"
    )
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


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (
            ("project", "repositories", 0, "role"),
            "owner",
            "repository.role must be primary or supporting",
        ),
        (
            ("project", "repositories", 0, "sync_policy"),
            "merge",
            "repository.sync_policy must be manual, fetch, or fast-forward",
        ),
        (
            ("project", "execution", "resolution"),
            "best-effort",
            "execution.resolution must be strict or compatible",
        ),
        (
            ("project", "execution", "requirements", 0, "level"),
            "optional",
            "requirement.level must be required or preferred",
        ),
    ],
)
def test_manifest_enum_diagnostics_are_exact(
    path: tuple[object, ...], value: object, message: str
) -> None:
    data = _portable_data()
    cursor: object = data
    for key in path[:-1]:
        assert isinstance(cursor, (dict, list))
        cursor = cursor[key]  # type: ignore[index]
    assert isinstance(cursor, (dict, list))
    cursor[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValueError, match=".") as error:
        ProjectManifest.from_data(data)
    assert str(error.value) == message


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("project", "repositories", 0, "alias"), 1, "repository.alias must be a string"),
        (("project", "repositories", 0, "uri"), [], "repository.uri must be a string"),
        (
            ("project", "repositories", 0, "default_ref"),
            {},
            "repository.default_ref must be a string",
        ),
        (("project", "repositories", 0, "adapter_id"), 1, "repository.adapter_id must be a string"),
        (
            ("project", "execution", "runtime", "adapter_id"),
            1,
            "execution.runtime.adapter_id must be a string",
        ),
        (
            ("project", "execution", "runtime", "profile_id"),
            None,
            "execution.runtime.profile_id must be a string",
        ),
        (
            ("project", "execution", "requirements", 0, "name"),
            1,
            "requirement.name must be a string",
        ),
    ],
)
def test_manifest_required_field_diagnostics_are_exact(
    path: tuple[object, ...], value: object, message: str
) -> None:
    data = _portable_data()
    cursor: object = data
    for key in path[:-1]:
        assert isinstance(cursor, (dict, list))
        cursor = cursor[key]  # type: ignore[index]
    assert isinstance(cursor, (dict, list))
    cursor[path[-1]] = value  # type: ignore[index]
    with pytest.raises(TypeError) as error:
        ProjectManifest.from_data(data)
    assert str(error.value) == message


@pytest.mark.parametrize(
    ("container", "key", "message"),
    [
        ("repository", key, "repository")
        for key in (
            "adapter_id",
            "alias",
            "default_ref",
            "role",
            "subdirectory",
            "sync_policy",
            "uri",
        )
    ]
    + [("execution", key, "execution") for key in ("requirements", "resolution", "runtime")]
    + [("runtime", key, "execution.runtime") for key in ("adapter_id", "profile_id")]
    + [("requirement", key, "requirement") for key in ("constraint", "level", "name")],
)
def test_manifest_rejects_each_missing_nested_key(container: str, key: str, message: str) -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    if container == "repository":
        repositories = project["repositories"]
        assert isinstance(repositories, list)
        target = repositories[0]
    elif container == "execution":
        target = project["execution"]
    elif container == "runtime":
        execution = project["execution"]
        assert isinstance(execution, dict)
        target = execution["runtime"]
    else:
        execution = project["execution"]
        assert isinstance(execution, dict)
        requirements = execution["requirements"]
        assert isinstance(requirements, list)
        target = requirements[0]
    assert isinstance(target, dict)
    del target[key]
    with pytest.raises(ValueError, match=f"^{message} keys mismatch"):
        ProjectManifest.from_data(data)


def test_manifest_round_trip_preserves_all_nested_optional_and_enum_values() -> None:
    data = _portable_data()
    project = data["project"]
    assert isinstance(project, dict)
    repositories = project["repositories"]
    assert isinstance(repositories, list)
    first = repositories[0]
    assert isinstance(first, dict)
    first.update(
        {
            "adapter_id": "custom",
            "alias": "source",
            "default_ref": "release/2026",
            "role": "primary",
            "subdirectory": "nested/path",
            "sync_policy": "manual",
            "uri": "ssh://git.example.test/source",
        }
    )
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["resolution"] = "strict"
    execution["runtime"] = {"adapter_id": "local", "profile_id": "python-3.13"}
    execution["requirements"] = [
        {"constraint": ">=1", "level": "required", "name": "engine"},
        {"constraint": None, "level": "preferred", "name": "gpu"},
    ]

    restored = ProjectManifest.from_data(data)
    assert [item.alias for item in restored.project.repositories] == ["docs", "source"]
    assert restored.project.repositories[1].uri == "ssh://git.example.test/source"
    assert restored.project.repositories[1].subdirectory == "nested/path"
    assert restored.project.execution.resolution == "strict"
    assert restored.project.execution.runtime == RuntimeProfileRef("local", "python-3.13")
    assert restored.project.execution.requirements == (
        CapabilityRequirement("engine", ">=1"),
        CapabilityRequirement("gpu", None, "preferred"),
    )
