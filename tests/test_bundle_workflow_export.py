from __future__ import annotations

from studio_core import WorkspaceId
from studio_execution.bundle_workflow import (
    INVENTORY_MEDIA_TYPE,
    build_workflow_bundle_inventory,
)


class _EmptyScheduler:
    def list_workflows(self, _workspace_id: WorkspaceId) -> tuple[object, ...]:
        return ()

    def list_schedules(self, _workspace_id: WorkspaceId) -> tuple[object, ...]:
        return ()


def test_empty_workflow_inventory_is_deterministic_and_has_inventory_payload() -> None:
    built = build_workflow_bundle_inventory(_EmptyScheduler(), WorkspaceId("ws-1"))
    assert built.inventory.objects == ()
    assert len(built.files) == 1
    assert built.files[0].media_type == INVENTORY_MEDIA_TYPE
