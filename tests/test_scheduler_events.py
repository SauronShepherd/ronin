from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from studio_core import Node, OperatorRef, Pipeline, WorkflowDefinition, WorkflowId, Workspace, WorkspaceId
from studio_core.scheduler_events import (
    EventTriggerDefinition,
    EventTriggerId,
    SchedulerEventId,
)
from studio_execution.scheduler_event_service import SchedulerEventService
from studio_orchestrator import Instant
from studio_storage.scheduler_events import (
    SchedulerEventConflict,
    SchedulerEventRecord,
    SchedulerEventStore,
)
from studio_storage.workspaces import SqliteWorkspaceStore

NOW = Instant("2026-09-12T20:00:00.000000Z")


def _workflow(identifier: str = "workflow-1") -> WorkflowDefinition:
    node = Node.create(operator=OperatorRef("notebook.run"), instance_key=f"task-{identifier}")
    return WorkflowDefinition(WorkflowId(identifier), identifier, Pipeline((node,)))


def _store(tmp_path: Path) -> tuple[SchedulerEventStore, WorkspaceId, WorkflowDefinition]:
    database = tmp_path / "ronin.db"
    workspace_id = WorkspaceId("workspace-1")
    workspace_store = SqliteWorkspaceStore(database, migration_now=NOW)
    workspace_store.create_workspace(Workspace(workspace_id, "Workspace"), now=NOW)
    store = SchedulerEventStore(database, migration_now=NOW)
    workflow = _workflow()
    store.put_workflow(workspace_id, workflow, now=NOW)
    return store, workspace_id, workflow


def _event(workspace_id: WorkspaceId, identifier: str = "event-1") -> SchedulerEventRecord:
    return SchedulerEventRecord(
        workspace_id,
        SchedulerEventId(identifier),
        "dataset.snapshot.committed",
        "connector://local/orders",
        "asset://orders/v1",
        "a" * 64,
        NOW,
        NOW,
    )


def test_event_trigger_round_trip_and_exact_matching() -> None:
    trigger = EventTriggerDefinition(
        EventTriggerId("trigger-1"),
        WorkflowId("workflow-1"),
        "dataset.snapshot.committed",
        source_ref="connector://local/orders",
        subject_ref="asset://orders/v1",
    )
    assert EventTriggerDefinition.from_json(trigger.to_json()) == trigger
    assert trigger.matches(
        event_type="dataset.snapshot.committed",
        source_ref="connector://local/orders",
        subject_ref="asset://orders/v1",
    )
    assert not trigger.matches(
        event_type="dataset.snapshot.committed",
        source_ref="connector://other/orders",
        subject_ref="asset://orders/v1",
    )


def test_event_ingest_freezes_matching_trigger_set_on_first_receipt(tmp_path: Path) -> None:
    store, workspace_id, workflow = _store(tmp_path)
    first_trigger = EventTriggerDefinition(
        EventTriggerId("trigger-1"), workflow.id, "dataset.snapshot.committed"
    )
    store.put_event_trigger(workspace_id, first_trigger, now=NOW)
    event = _event(workspace_id)

    first = store.ingest_event(event)
    assert [delivery.trigger.id for delivery in first] == [first_trigger.id]

    # A trigger created after receipt must not retroactively reinterpret the event.
    second_trigger = EventTriggerDefinition(
        EventTriggerId("trigger-2"), workflow.id, "dataset.snapshot.committed"
    )
    store.put_event_trigger(workspace_id, second_trigger, now=NOW)
    replay = store.ingest_event(event)
    assert [delivery.trigger.id for delivery in replay] == [first_trigger.id]


def test_event_idempotency_rejects_conflicting_content(tmp_path: Path) -> None:
    store, workspace_id, _workflow = _store(tmp_path)
    original = _event(workspace_id)
    store.ingest_event(original)
    conflicting = SchedulerEventRecord(
        workspace_id,
        original.id,
        original.event_type,
        original.source_ref,
        original.subject_ref,
        "b" * 64,
        original.occurred_at,
        original.received_at,
    )
    with pytest.raises(SchedulerEventConflict, match="conflicting content"):
        store.ingest_event(conflicting)


def test_event_delivery_creates_deterministic_workflow_run_once(tmp_path: Path) -> None:
    store, workspace_id, workflow = _store(tmp_path)
    definition = EventTriggerDefinition(
        EventTriggerId("trigger-1"), workflow.id, "dataset.snapshot.committed"
    )
    store.put_event_trigger(workspace_id, definition, now=NOW)
    event = _event(workspace_id)
    pending = store.ingest_event(event)
    assert len(pending) == 1

    delivered = store.deliver_event(pending[0], now=NOW)
    assert delivered.state == "delivered"
    assert delivered.workflow_run_id is not None
    assert store.list_pending_deliveries(workspace_id) == ()

    # Replaying the same durable delivery maps to the same WorkflowRun.
    replay = store.deliver_event(pending[0], now=NOW)
    assert replay == delivered
    run = store.get_run(workspace_id, delivered.workflow_run_id)
    assert run is not None
    assert run.trigger.kind == "event"
    assert run.trigger.key == "event:event-1:trigger-1"


def test_event_service_processes_pending_deliveries(tmp_path: Path) -> None:
    store, workspace_id, workflow = _store(tmp_path)
    store.put_event_trigger(
        workspace_id,
        EventTriggerDefinition(
            EventTriggerId("trigger-1"), workflow.id, "dataset.snapshot.committed"
        ),
        now=NOW,
    )
    service = SchedulerEventService(store)

    async def scenario() -> None:
        deliveries = await service.ingest(_event(workspace_id))
        assert len(deliveries) == 1
        result = await service.process_pending(workspace_id, now=NOW)
        assert len(result.delivered) == 1
        assert result.delivered[0].workflow_run_id is not None
        second = await service.process_pending(workspace_id, now=NOW)
        assert second.delivered == ()

    asyncio.run(scenario())


def test_event_record_rejects_credential_bearing_refs(tmp_path: Path) -> None:
    _store_obj, workspace_id, _workflow_obj = _store(tmp_path)
    with pytest.raises(ValueError, match="credential material"):
        SchedulerEventRecord(
            workspace_id,
            SchedulerEventId("unsafe"),
            "webhook.received",
            "endpoint://service?token=cleartext",
            None,
            "c" * 64,
            NOW,
            NOW,
        )
