from __future__ import annotations

from collections.abc import Mapping

import pytest
from studio_core import (
    CapabilityRequirement,
    ExecutionProfile,
    Project,
    ProjectId,
    ProjectManifest,
    RepositoryBinding,
    RuntimeProfileRef,
)


def _project() -> Project:
    return Project(
        ProjectId("orders"),
        "Orders",
        (
            RepositoryBinding(
                "code",
                "https://example.test/orders.git",
                role="primary",
                default_ref="main",
                subdirectory="src",
                adapter_id="git",
                sync_policy="fast-forward",
                auth_ref="connection://local-only",
            ),
            RepositoryBinding(
                "docs",
                "../docs",
                role="supporting",
                default_ref="main",
                adapter_id="git",
                sync_policy="manual",
            ),
        ),
        ExecutionProfile(
            RuntimeProfileRef("python", "3.13"),
            (
                CapabilityRequirement("python.version", ">=3.13"),
                CapabilityRequirement("gpu", level="preferred"),
            ),
            "strict",
        ),
    )


def _data() -> dict[str, object]:
    return ProjectManifest.from_project(_project()).to_data()


def test_from_project_strips_only_auth_and_preserves_every_portable_field() -> None:
    source = _project()
    manifest = ProjectManifest.from_project(source)
    assert manifest.project.id == source.id
    assert manifest.project.name == source.name
    assert manifest.project.execution == source.execution
    assert tuple(repository.auth_ref for repository in source.repositories) == (
        "connection://local-only",
        None,
    )
    assert all(repository.auth_ref is None for repository in manifest.project.repositories)
    assert manifest.project.repositories[0].subdirectory == "src"
    assert manifest.project.repositories[1].sync_policy == "manual"


def test_manifest_parser_accepts_mapping_and_sequence_protocols() -> None:
    data = _data()
    project = data["project"]
    assert isinstance(project, dict)
    project["repositories"] = tuple(project["repositories"])  # type: ignore[arg-type]
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["requirements"] = tuple(execution["requirements"])  # type: ignore[arg-type]
    restored = ProjectManifest.from_data(MappingProxy(data))
    assert restored.project.repositories[0].alias == "code"
    assert restored.project.execution.requirements[0].name == "gpu"


class MappingProxy(Mapping[str, object]):
    def __init__(self, value: Mapping[str, object]) -> None:
        self._value = value

    def __getitem__(self, key: str) -> object:
        return self._value[key]

    def __iter__(self):
        return iter(self._value)

    def __len__(self) -> int:
        return len(self._value)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repositories", "not-a-sequence", "repositories must be an array"),
        ("repositories", b"bytes", "repositories must be an array"),
        ("repositories", bytearray(b"bytes"), "repositories must be an array"),
        ("execution", None, "execution must be an object"),
    ],
)
def test_manifest_parser_rejects_string_bytes_and_missing_nested_shapes(
    field: str, value: object, message: str
) -> None:
    data = _data()
    project = data["project"]
    assert isinstance(project, dict)
    project[field] = value
    with pytest.raises(TypeError, match=message):
        ProjectManifest.from_data(data)


def test_manifest_parser_rejects_non_string_mapping_keys_at_each_object_boundary() -> None:
    data = _data()
    project = data["project"]
    assert isinstance(project, dict)
    project["repositories"] = [{1: "invalid"}]
    with pytest.raises(TypeError, match="repository must be an object"):
        ProjectManifest.from_data(data)


def test_manifest_json_parser_reports_invalid_json() -> None:
    with pytest.raises(ValueError, match="."):
        ProjectManifest.from_json("{not-json}")


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("manifest", "schema"),
        ("project", "id"),
        ("repository", "uri"),
        ("execution", "resolution"),
        ("runtime", "profile_id"),
        ("requirement", "name"),
    ],
)
def test_manifest_exact_key_diagnostics_report_missing_key(section: str, key: str) -> None:
    data = _data()
    if section == "manifest":
        target = data
    elif section == "project":
        target = data["project"]
    elif section == "repository":
        target = data["project"]["repositories"][0]  # type: ignore[index]
    elif section == "execution":
        target = data["project"]["execution"]  # type: ignore[index]
    elif section == "runtime":
        target = data["project"]["execution"]["runtime"]  # type: ignore[index]
    else:
        target = data["project"]["execution"]["requirements"][0]  # type: ignore[index]
    assert isinstance(target, dict)
    del target[key]
    expected_section = "execution.runtime" if section == "runtime" else section
    with pytest.raises(ValueError, match=f"^{expected_section} keys mismatch"):
        ProjectManifest.from_data(data)
