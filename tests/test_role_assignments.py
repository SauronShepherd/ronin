import pytest
from studio_core import Principal, ResourceScope, RoleAssignment


def test_role_assignment_compiles_to_scoped_grants_and_safe_payload() -> None:
    assignment = RoleAssignment(
        Principal("service", "svc.scheduler"),
        "editor",
        ResourceScope("project", "orders"),
    )
    assert assignment.grants.exact_resource_ids("write", kind="project") == ("orders",)
    assert assignment.to_payload()["principal"] == {
        "kind": "service",
        "identifier": "svc.scheduler",
    }


@pytest.mark.parametrize(
    "principal",
    [Principal("user", "alice"), Principal("group", "data-team")],
)
def test_supported_principal_kinds_are_explicit(principal: Principal) -> None:
    assert principal.kind in {"user", "group"}


def test_role_assignment_rejects_unsafe_or_unknown_identity() -> None:
    with pytest.raises(ValueError, match="principal kind"):
        Principal("token", "secret")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="single-line"):
        Principal("user", "alice\nadmin")
    with pytest.raises(ValueError, match="role"):
        RoleAssignment(Principal("user", "alice"), "admin", ResourceScope("project", "p"))  # type: ignore[arg-type]
