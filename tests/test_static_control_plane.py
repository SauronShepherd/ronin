import pytest

from studio_core import WorkspaceId
from studio_server import StaticControlPlaneAuthenticator, StaticControlPlaneAuthorizer
from studio_security import PolicyRequirement


def test_static_control_plane_is_explicit_and_workspace_scoped() -> None:
    authenticator = StaticControlPlaneAuthenticator("secret")
    authorizer = StaticControlPlaneAuthorizer(
        WorkspaceId("workspace-a"), frozenset({"workflow.read"})
    )
    actor = authenticator.authenticate("Bearer secret")
    assert actor is not None
    assert authenticator.authenticate("Bearer other") is None
    assert authorizer.authorize(
        actor, PolicyRequirement(WorkspaceId("workspace-a"), "workflow.read")
    ).allowed
    assert not authorizer.authorize(
        actor, PolicyRequirement(WorkspaceId("workspace-b"), "workflow.read")
    ).allowed
    assert not authorizer.authorize(
        actor, PolicyRequirement(WorkspaceId("workspace-a"), "workflow.write")
    ).allowed


def test_static_control_plane_rejects_empty_configuration() -> None:
    with pytest.raises(ValueError, match="token"):
        StaticControlPlaneAuthenticator(" ")
    with pytest.raises(ValueError, match="permissions"):
        StaticControlPlaneAuthorizer(WorkspaceId("workspace-a"), frozenset())
