from studio_core import Grant, GrantSet, ResourceScope


def test_exact_resource_ids_projects_scoped_grants_deterministically() -> None:
    grants = GrantSet(
        (
            Grant(frozenset({"list"}), ResourceScope("project", "project-b")),
            Grant(frozenset({"list"}), ResourceScope("project", "project-a")),
        )
    )

    assert grants.exact_resource_ids("list", kind="project") == ("project-a", "project-b")


def test_exact_resource_ids_returns_wildcard_sentinel() -> None:
    grants = GrantSet((Grant(frozenset({"list"}), ResourceScope("project", None)),))

    assert grants.exact_resource_ids("list", kind="project") is None


def test_exact_resource_ids_ignores_constrained_grants() -> None:
    grants = GrantSet(
        (
            Grant(
                frozenset({"list"}),
                ResourceScope("project", "project-a"),
                constraints=(("team", "analytics"),),
            ),
        )
    )

    assert grants.exact_resource_ids("list", kind="project") == ()
