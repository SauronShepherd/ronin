from dataclasses import FrozenInstanceError

import pytest
from studio_core import (
    CapabilityRequirement,
    ExecutionProfile,
    Project,
    ProjectCollection,
    ProjectId,
    RepositoryBinding,
    RuntimeProfileRef,
)


def _execution() -> ExecutionProfile:
    return ExecutionProfile(
        runtime=RuntimeProfileRef("spark-local", "default"),
        requirements=(CapabilityRequirement("python.version", ">=3.11"),),
    )


def _project(project_id: str, repository_uri: str) -> Project:
    return Project(
        id=ProjectId(project_id),
        name=f"Project {project_id}",
        repositories=(RepositoryBinding("code", repository_uri, role="primary"),),
        execution=_execution(),
    )


def test_project_id_is_immutable_and_stringifies() -> None:
    project_id = ProjectId("orders")
    assert str(project_id) == "orders"
    with pytest.raises(FrozenInstanceError):
        project_id.value = "changed"  # type: ignore[misc]


def test_text_contracts_reject_blank_untrimmed_and_line_break_values() -> None:
    for value in (" ", " orders", "orders "):
        with pytest.raises(ValueError, match="project id"):
            ProjectId(value)
    with pytest.raises(ValueError, match="line breaks"):
        ProjectId("bad\nid")
    with pytest.raises(ValueError, match="repository alias"):
        RepositoryBinding("", "https://example.test/repo.git", role="primary")
    with pytest.raises(ValueError, match="repository uri"):
        RepositoryBinding("code", "", role="primary")
    with pytest.raises(ValueError, match="default ref"):
        RepositoryBinding(
            "code",
            "https://example.test/repo.git",
            role="primary",
            default_ref="",
        )


def test_repository_binding_supports_remote_and_local_git_without_vendor_coupling() -> None:
    remote = RepositoryBinding(
        "code",
        "https://git.example.test/team/data-platform.git",
        role="primary",
        default_ref="develop",
        auth_ref="connection://team-git",
        subdirectory="products/orders",
    )
    local = RepositoryBinding("local", "../repos/orders", role="supporting")
    ssh = RepositoryBinding("ssh", "git@example.test:team/orders.git", role="supporting")
    assert remote.default_ref == "develop"
    assert remote.auth_ref == "connection://team-git"
    assert local.uri == "../repos/orders"
    assert ssh.uri.startswith("git@")


def test_repository_binding_rejects_invalid_role_or_literal_auth_material() -> None:
    with pytest.raises(ValueError, match="role"):
        RepositoryBinding(
            "code",
            "https://example.test/repo.git",
            role="owner",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="auth_ref"):
        RepositoryBinding(
            "code",
            "https://example.test/repo.git",
            role="primary",
            auth_ref="plain-token-value",
        )
    assert (
        RepositoryBinding(
            "code",
            "https://example.test/repo.git",
            role="primary",
            auth_ref="secret://git-token",
        ).auth_ref
        == "secret://git-token"
    )


def test_repository_binding_rejects_embedded_credentials_for_url_schemes() -> None:
    for uri in (
        "https://user:token@example.test/team/repo.git",
        "http://user:token@example.test/team/repo.git",
        "ssh://user:token@example.test/team/repo.git",
    ):
        with pytest.raises(ValueError, match="credentials"):
            RepositoryBinding("code", uri, role="primary")
    for uri in (
        " https://user:token@example.test/team/repo.git",
        "\thttps://user:token@example.test/team/repo.git",
    ):
        with pytest.raises(ValueError, match="trimmed"):
            RepositoryBinding("code", uri, role="primary")
    assert RepositoryBinding(
        "code",
        "https://example.test/team/repo.git",
        role="primary",
    ).uri.endswith("repo.git")


def test_repository_subdirectory_must_stay_inside_repository() -> None:
    with pytest.raises(ValueError, match="subdirectory"):
        RepositoryBinding(
            "code",
            "https://example.test/repo.git",
            role="primary",
            subdirectory="",
        )
    for subdirectory in ("/absolute", "../escape", "safe\\..\\escape", "C:/secrets"):
        with pytest.raises(ValueError, match="repository root"):
            RepositoryBinding(
                "code",
                "https://example.test/repo.git",
                role="primary",
                subdirectory=subdirectory,
            )


def test_capability_requirement_validates_name_constraint_and_level() -> None:
    requirement = CapabilityRequirement("spark.version", ">=3.5,<4", "preferred")
    assert requirement.constraint == ">=3.5,<4"
    with pytest.raises(ValueError, match="capability name"):
        CapabilityRequirement("")
    with pytest.raises(ValueError, match="constraint"):
        CapabilityRequirement("spark.version", " ")
    with pytest.raises(ValueError, match="level"):
        CapabilityRequirement("spark.version", level="maybe")  # type: ignore[arg-type]
    for constraint, message in (
        (">=4,,<5", "empty term"),
        (">=", "missing a value"),
        (">=four", "version-like"),
    ):
        with pytest.raises(ValueError, match=message):
            CapabilityRequirement("spark.version", constraint)


def test_runtime_profile_reference_is_opaque_and_provider_neutral() -> None:
    fabric = RuntimeProfileRef("fabric-runtime", "runtime-selected-by-adapter")
    databricks = RuntimeProfileRef("databricks-runtime", "lts-selected-by-adapter")
    local = RuntimeProfileRef("spark-local", "default")
    assert {fabric.adapter_id, databricks.adapter_id, local.adapter_id} == {
        "fabric-runtime",
        "databricks-runtime",
        "spark-local",
    }
    with pytest.raises(ValueError, match="adapter"):
        RuntimeProfileRef("", "runtime")
    with pytest.raises(ValueError, match="profile"):
        RuntimeProfileRef("adapter", "")


def test_execution_profile_can_pin_runtime_and_require_capabilities() -> None:
    first = ExecutionProfile(
        runtime=RuntimeProfileRef("databricks-runtime", "lts-selected-by-adapter"),
        requirements=(
            CapabilityRequirement("gpu", "optional", "preferred"),
            CapabilityRequirement("spark.version", ">=3.5"),
            CapabilityRequirement("python.version", ">=3.11"),
        ),
        resolution="compatible",
    )
    second = ExecutionProfile(
        runtime=first.runtime,
        requirements=tuple(reversed(first.requirements)),
        resolution="compatible",
    )
    assert first == second
    assert [item.name for item in first.requirements] == [
        "gpu",
        "python.version",
        "spark.version",
    ]


def test_execution_profile_can_be_capability_only() -> None:
    profile = ExecutionProfile(requirements=(CapabilityRequirement("engine.spark"),))
    assert profile.runtime is None
    assert profile.resolution == "strict"


def test_execution_profile_rejects_empty_invalid_or_duplicate_requirements() -> None:
    with pytest.raises(ValueError, match="runtime reference or capabilities"):
        ExecutionProfile()
    with pytest.raises(ValueError, match="resolution"):
        ExecutionProfile(
            runtime=RuntimeProfileRef("spark-local", "default"),
            resolution="best-effort",  # type: ignore[arg-type]
        )
    duplicate = CapabilityRequirement("spark.version", ">=3.5")
    with pytest.raises(ValueError, match="unique"):
        ExecutionProfile(requirements=(duplicate, CapabilityRequirement("spark.version", "<4")))


def test_project_requires_exactly_one_primary_repository() -> None:
    supporting = RepositoryBinding("docs", "https://example.test/docs.git")
    with pytest.raises(ValueError, match="at least one"):
        Project(ProjectId("empty"), "Empty", (), _execution())
    with pytest.raises(ValueError, match="exactly one"):
        Project(ProjectId("no-primary"), "No primary", (supporting,), _execution())
    with pytest.raises(ValueError, match="exactly one"):
        Project(
            ProjectId("two-primary"),
            "Two primary",
            (
                RepositoryBinding("a", "https://example.test/a.git", role="primary"),
                RepositoryBinding("b", "https://example.test/b.git", role="primary"),
            ),
            _execution(),
        )


def test_project_canonicalizes_repositories_and_exposes_primary() -> None:
    project = Project(
        ProjectId("analytics"),
        "Analytics",
        (
            RepositoryBinding("z-docs", "https://example.test/docs.git"),
            RepositoryBinding("a-code", "https://example.test/code.git", role="primary"),
        ),
        _execution(),
    )
    assert [repository.alias for repository in project.repositories] == ["a-code", "z-docs"]
    assert project.primary_repository.alias == "a-code"


def test_project_rejects_blank_name_and_duplicate_repository_aliases() -> None:
    primary = RepositoryBinding("code", "https://example.test/code.git", role="primary")
    with pytest.raises(ValueError, match="project name"):
        Project(ProjectId("bad-name"), " ", (primary,), _execution())
    with pytest.raises(ValueError, match="aliases"):
        Project(
            ProjectId("duplicates"),
            "Duplicates",
            (primary, RepositoryBinding("code", "https://example.test/other.git")),
            _execution(),
        )


def test_project_collection_supports_multiple_projects_canonically() -> None:
    alpha = _project("alpha", "https://example.test/alpha.git")
    beta = _project("beta", "https://example.test/beta.git")
    projects = ProjectCollection((beta, alpha))
    assert [project.id.value for project in projects.projects] == ["alpha", "beta"]
    assert projects.get(ProjectId("beta")) == beta
    assert projects.get(ProjectId("missing")) is None


def test_project_collection_rejects_duplicate_project_ids() -> None:
    first = _project("same", "https://example.test/one.git")
    second = Project(
        ProjectId("same"),
        "Other",
        (RepositoryBinding("code", "https://example.test/two.git", role="primary"),),
        _execution(),
    )
    with pytest.raises(ValueError, match="project ids"):
        ProjectCollection((first, second))
