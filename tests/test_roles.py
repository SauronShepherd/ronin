from studio_core import (
    Requirement,
    ResourceScope,
    role_definition,
    role_names,
)


def test_named_roles_are_canonical_and_deterministic() -> None:
    scope = ResourceScope("project", "orders")
    assert role_names() == ("viewer", "editor", "owner")
    viewer = role_definition("viewer", resource=scope)
    assert viewer.grants.permits(Requirement("read", scope)).allowed
    assert not viewer.grants.permits(Requirement("write", scope)).allowed
    assert (
        role_definition("owner", resource=scope).grants
        == role_definition("owner", resource=scope).grants
    )


def test_role_grants_remain_scoped_to_the_assigned_resource() -> None:
    editor = role_definition("editor", resource=ResourceScope("project", "orders"))
    other = ResourceScope("project", "billing")
    assert not editor.grants.permits(Requirement("write", other)).allowed
