"""Pure project, Git repository, and execution-profile domain contracts."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Literal

RepositoryRole = Literal["primary", "supporting"]
RepositorySyncPolicy = Literal["manual", "fetch", "fast-forward"]
RequirementLevel = Literal["required", "preferred"]
ResolutionPolicy = Literal["strict", "compatible"]


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field_name} must not contain line breaks")


@dataclass(frozen=True, order=True, slots=True)
class ProjectId:
    """Stable project identity supplied by the authoring/persistence boundary."""

    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "project id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class RepositoryBinding:
    """A Git repository attached to a project without resolved credentials."""

    alias: str
    uri: str
    role: RepositoryRole = "supporting"
    default_ref: str = "main"
    auth_ref: str | None = None
    subdirectory: str | None = None
    adapter_id: str = "git"
    sync_policy: RepositorySyncPolicy = "manual"

    def __post_init__(self) -> None:
        _require_text(self.alias, "repository alias")
        _require_text(self.uri, "repository uri")
        _require_text(self.default_ref, "repository default ref")
        _require_text(self.adapter_id, "repository adapter id")
        if self.role not in {"primary", "supporting"}:
            raise ValueError("repository role must be primary or supporting")
        if self.sync_policy not in {"manual", "fetch", "fast-forward"}:
            raise ValueError("repository sync policy must be manual, fetch, or fast-forward")
        if self.auth_ref is not None and not self.auth_ref.startswith(
            ("secret://", "connection://")
        ):
            raise ValueError("repository auth_ref must be a secret:// or connection:// reference")
        if self.uri.lower().startswith(("http://", "https://")):
            authority = self.uri.split("://", maxsplit=1)[1].split("/", maxsplit=1)[0]
            if "@" in authority:
                raise ValueError("repository uri must not embed HTTP credentials")
        if self.subdirectory is not None:
            _require_text(self.subdirectory, "repository subdirectory")
            normalized = self.subdirectory.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                raise ValueError("repository subdirectory must stay within the repository root")


@dataclass(frozen=True, order=True, slots=True)
class CapabilityRequirement:
    """Provider-neutral execution capability requested by a project."""

    name: str
    constraint: str | None = None
    level: RequirementLevel = "required"

    def __post_init__(self) -> None:
        _require_text(self.name, "capability name")
        if self.constraint is not None:
            _require_text(self.constraint, "capability constraint")
        if self.level not in {"required", "preferred"}:
            raise ValueError("capability level must be required or preferred")


@dataclass(frozen=True, order=True, slots=True)
class RuntimeProfileRef:
    """Opaque reference to a runtime profile exposed by an execution adapter."""

    adapter_id: str
    profile_id: str

    def __post_init__(self) -> None:
        _require_text(self.adapter_id, "runtime adapter id")
        _require_text(self.profile_id, "runtime profile id")


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    """A project's desired runtime plus neutral compatibility requirements."""

    runtime: RuntimeProfileRef | None = None
    requirements: tuple[CapabilityRequirement, ...] = ()
    resolution: ResolutionPolicy = "strict"

    def __post_init__(self) -> None:
        if self.runtime is None and not self.requirements:
            raise ValueError("execution profile requires a runtime reference or capabilities")
        if self.resolution not in {"strict", "compatible"}:
            raise ValueError("execution resolution must be strict or compatible")
        canonical_requirements = tuple(sorted(self.requirements))
        names = [requirement.name for requirement in canonical_requirements]
        if len(names) != len(set(names)):
            raise ValueError("execution capability names must be unique")
        object.__setattr__(self, "requirements", canonical_requirements)


@dataclass(frozen=True, slots=True)
class Project:
    """Portable project configuration independent of hosting or runtime vendor."""

    id: ProjectId
    name: str
    repositories: tuple[RepositoryBinding, ...]
    execution: ExecutionProfile

    def __post_init__(self) -> None:
        _require_text(self.name, "project name")
        if not self.repositories:
            raise ValueError("project requires at least one repository")
        canonical_repositories = tuple(sorted(self.repositories, key=lambda item: item.alias))
        aliases = [repository.alias for repository in canonical_repositories]
        if len(aliases) != len(set(aliases)):
            raise ValueError("repository aliases must be unique within a project")
        primaries = [
            repository for repository in canonical_repositories if repository.role == "primary"
        ]
        if len(primaries) != 1:
            raise ValueError("project requires exactly one primary repository")
        object.__setattr__(self, "repositories", canonical_repositories)

    @property
    def primary_repository(self) -> RepositoryBinding:
        return next(repository for repository in self.repositories if repository.role == "primary")


@dataclass(frozen=True, slots=True)
class ProjectCollection:
    """Canonical collection for multi-project workspace/application boundaries."""

    projects: tuple[Project, ...] = ()

    def __post_init__(self) -> None:
        canonical_projects = tuple(sorted(self.projects, key=lambda project: project.id.value))
        ids = [project.id for project in canonical_projects]
        if len(ids) != len(set(ids)):
            raise ValueError("project ids must be unique")
        object.__setattr__(self, "projects", canonical_projects)

    def get(self, project_id: ProjectId) -> Project | None:
        index = bisect_left(self.projects, project_id.value, key=lambda project: project.id.value)
        if index < len(self.projects) and self.projects[index].id == project_id:
            return self.projects[index]
        return None
