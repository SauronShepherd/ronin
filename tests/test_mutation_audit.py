from studio_core import WorkspaceId
from studio_security import Actor, Principal, PrincipalId, mutation_audit_event


def test_mutation_audit_is_deterministic_and_redacts_metadata():
    actor = Actor(Principal(PrincipalId("admin"), "user", "Admin", "issuer", "sub", None, True))
    event = mutation_audit_event(
        actor,
        workspace_id=WorkspaceId("ws").value,
        action="security.service_identity.rotate",
        resource_ref="service:worker",
        outcome="succeeded",
        metadata={"secret": "do-not-persist", "replacement": "worker-v2"},
        now="2026-01-01T00:00:00.000000Z",
        request_id="req-1",
    )
    assert event == mutation_audit_event(
        actor,
        workspace_id="ws",
        action="security.service_identity.rotate",
        resource_ref="service:worker",
        outcome="succeeded",
        metadata={"secret": "do-not-persist", "replacement": "worker-v2"},
        now="2026-01-01T00:00:00.000000Z",
        request_id="req-1",
    )
    assert "do-not-persist" not in str(event.metadata)
