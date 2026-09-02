"""Deterministic, repository-local project intent for ``.ronin/project.json``."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from .projects import (
    CapabilityRequirement,
    ExecutionProfile,
    Project,
    ProjectId,
    RepositoryBinding,
    RepositoryRole,
    RepositorySyncPolicy,
    RequirementLevel,
    ResolutionPolicy,
    RuntimeProfileRef,
)

PROJECT_MANIFEST_PATH = ".ronin/project.json"
PROJECT_MANIFEST_SCHEMA = "ronin.project/v1"


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    """Versioned portable project intent without machine-specific auth bindings."""

    project: Project
    schema: str = PROJECT_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != PROJECT_MANIFEST_SCHEMA:
            raise ValueError(f"unsupported project manifest schema: {self.schema}")
        if any(repository.auth_ref is not None for repository in self.project.repositories):
            raise ValueError("project manifest must not contain repository auth bindings")

    @classmethod
    def from_project(cls, project: Project) -> ProjectManifest:
        """Strip workspace-only auth references from otherwise portable project intent."""
        repositories = tuple(
            RepositoryBinding(
                alias=repository.alias,
                uri=repository.uri,
                role=repository.role,
                default_ref=repository.default_ref,
                subdirectory=repository.subdirectory,
                adapter_id=repository.adapter_id,
                sync_policy=repository.sync_policy,
            )
            for repository in project.repositories
        )
        return cls(Project(project.id, project.name, repositories, project.execution))

    def to_data(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "project": {
                "id": self.project.id.value,
                "name": self.project.name,
                "repositories": [_repository_to_data(item) for item in self.project.repositories],
                "execution": _execution_to_data(self.project.execution),
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_data(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_data(cls, value: Mapping[str, object]) -> ProjectManifest:
        manifest_data = _require_mapping(value, "manifest")
        _require_exact_keys(manifest_data, {"schema", "project"}, "manifest")
        schema = _require_str(manifest_data.get("schema"), "schema")
        project_data = _require_mapping(manifest_data.get("project"), "project")
        _require_exact_keys(project_data, {"id", "name", "repositories", "execution"}, "project")
        repositories_data = _require_sequence(project_data.get("repositories"), "repositories")
        return cls(
            project=Project(
                id=ProjectId(_require_str(project_data.get("id"), "project.id")),
                name=_require_str(project_data.get("name"), "project.name"),
                repositories=tuple(
                    _repository_from_data(_require_mapping(item, "repository"))
                    for item in repositories_data
                ),
                execution=_execution_from_data(
                    _require_mapping(project_data.get("execution"), "execution")
                ),
            ),
            schema=schema,
        )

    @classmethod
    def from_json(cls, payload: str) -> ProjectManifest:
        return cls.from_data(_require_mapping(json.loads(payload), "manifest"))


def _repository_to_data(repository: RepositoryBinding) -> dict[str, object]:
    return {
        "adapter_id": repository.adapter_id,
        "alias": repository.alias,
        "default_ref": repository.default_ref,
        "role": repository.role,
        "subdirectory": repository.subdirectory,
        "sync_policy": repository.sync_policy,
        "uri": repository.uri,
    }


def _repository_from_data(value: Mapping[str, object]) -> RepositoryBinding:
    _require_exact_keys(
        value,
        {"adapter_id", "alias", "default_ref", "role", "subdirectory", "sync_policy", "uri"},
        "repository",
    )
    role = _require_str(value.get("role"), "repository.role")
    sync_policy = _require_str(value.get("sync_policy"), "repository.sync_policy")
    subdirectory = value.get("subdirectory")
    if role not in {"primary", "supporting"}:
        raise ValueError("repository.role must be primary or supporting")
    if sync_policy not in {"manual", "fetch", "fast-forward"}:
        raise ValueError("repository.sync_policy must be manual, fetch, or fast-forward")
    if subdirectory is not None and not isinstance(subdirectory, str):
        raise TypeError("repository.subdirectory must be a string or null")
    return RepositoryBinding(
        alias=_require_str(value.get("alias"), "repository.alias"),
        uri=_require_str(value.get("uri"), "repository.uri"),
        role=cast(RepositoryRole, role),
        default_ref=_require_str(value.get("default_ref"), "repository.default_ref"),
        subdirectory=subdirectory,
        adapter_id=_require_str(value.get("adapter_id"), "repository.adapter_id"),
        sync_policy=cast(RepositorySyncPolicy, sync_policy),
    )


def _execution_to_data(execution: ExecutionProfile) -> dict[str, object]:
    runtime: object = None
    if execution.runtime is not None:
        runtime = {
            "adapter_id": execution.runtime.adapter_id,
            "profile_id": execution.runtime.profile_id,
        }
    return {
        "requirements": [
            {"constraint": item.constraint, "level": item.level, "name": item.name}
            for item in execution.requirements
        ],
        "resolution": execution.resolution,
        "runtime": runtime,
    }


def _execution_from_data(value: Mapping[str, object]) -> ExecutionProfile:
    _require_exact_keys(value, {"requirements", "resolution", "runtime"}, "execution")
    resolution = _require_str(value.get("resolution"), "execution.resolution")
    if resolution not in {"strict", "compatible"}:
        raise ValueError("execution.resolution must be strict or compatible")
    requirements_data = _require_sequence(value.get("requirements"), "execution.requirements")
    runtime_data = value.get("runtime")
    runtime = None
    if runtime_data is not None:
        runtime_mapping = _require_mapping(runtime_data, "execution.runtime")
        _require_exact_keys(runtime_mapping, {"adapter_id", "profile_id"}, "execution.runtime")
        runtime = RuntimeProfileRef(
            adapter_id=_require_str(
                runtime_mapping.get("adapter_id"), "execution.runtime.adapter_id"
            ),
            profile_id=_require_str(
                runtime_mapping.get("profile_id"), "execution.runtime.profile_id"
            ),
        )
    return ExecutionProfile(
        runtime=runtime,
        requirements=tuple(
            _requirement_from_data(_require_mapping(item, "requirement"))
            for item in requirements_data
        ),
        resolution=cast(ResolutionPolicy, resolution),
    )


def _requirement_from_data(value: Mapping[str, object]) -> CapabilityRequirement:
    _require_exact_keys(value, {"constraint", "level", "name"}, "requirement")
    level = _require_str(value.get("level"), "requirement.level")
    constraint = value.get("constraint")
    if level not in {"required", "preferred"}:
        raise ValueError("requirement.level must be required or preferred")
    if constraint is not None and not isinstance(constraint, str):
        raise TypeError("requirement.constraint must be a string or null")
    return CapabilityRequirement(
        name=_require_str(value.get("name"), "requirement.name"),
        constraint=constraint,
        level=cast(RequirementLevel, level),
    )


def _require_exact_keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise ValueError(f"{name} keys mismatch; missing={missing}, extra={extra}")


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{name} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _require_sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be an array")
    return cast(Sequence[object], value)


def _require_str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value
