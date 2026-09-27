from pathlib import Path

import pytest

from studio_core import (
    Node,
    OperatorRef,
    Pipeline,
    Schedule,
    ScheduleId,
    WorkflowDefinition,
    WorkflowId,
    Workspace,
    WorkspaceId,
)
from studio_execution.bundle_workflow import (
    build_workflow_bundle_inventory,
    export_workflow_bundle,
    plan_workflow_bundle_import,
)
from studio_execution.bundle_workflow_commit import commit_workflow_bundle_import
from studio_storage.bundle_workflow_import import SqliteWorkflowBundleImportStore
from studio_storage.bundle_workflow_import_port import WorkflowBundleImportConflict

_T0 = "2026-09-13T10:00:00.000000Z"
_WS = WorkspaceId("workspace-workflow-bundle")


def _workflow(name: str = "Portable workflow") -> WorkflowDefinition:
    node = Node.create(
        operator=OperatorRef("notebook.run"),
        instance_key="portable-task",
        params={"target": "notebooks/demo.ronin.json", "parameters": {"limit": 5}},
    )
    return WorkflowDefinition(
        WorkflowId("workflow-portable"),
        name,
        Pipeline((node,)),
        max_concurrency=3,
    )


def _store(path: Path) -> SqliteWorkflowBundleImportStore:
    store = SqliteWorkflowBundleImportStore(path, migration_now=_T0)
    store.create_workspace(Workspace(_WS, "Workspace"), now=_T0)
    return store


def test_workflow_bundle_round_trip_excludes_runtime_state(tmp_path: Path) -> None:
    source = _store(tmp_path / "source.db")
    workflow = _workflow()
    schedule = Schedule(
        ScheduleId("schedule-portable"),
        workflow.id,
        "5 * * * *",
        "Europe/Madrid",
        True,
    )
    source.put_workflow(_WS, workflow, now=_T0)
    source.put_schedule(_WS, schedule, now=_T0)

    built = build_workflow_bundle_inventory(source, _WS, (workflow.id,))
    assert tuple(item.kind for item in built.inventory.objects) == ("schedule", "workflow")
    assert not built.inventory.unresolved_bindings

    bundle = tmp_path / "workflow.roninbundle"
    export_workflow_bundle(source, _WS, (workflow.id,), bundle)

    target = _store(tmp_path / "target.db")
    plan = plan_workflow_bundle_import(bundle, target, target, _WS)
    assert not plan.has_collisions
    assert {item.disposition for item in plan.objects} == {"create"}

    outcome = commit_workflow_bundle_import(bundle, target, _WS, now=_T0)
    assert outcome.commit.workflows_created == 1
    assert outcome.commit.schedules_created == 1
    assert target.get_workflow(_WS, workflow.id) == workflow
    assert target.get_schedule(_WS, schedule.id) == schedule

    replay = commit_workflow_bundle_import(bundle, target, _WS, now=_T0)
    assert replay.commit.workflows_created == 0
    assert replay.commit.schedules_created == 0


def test_workflow_bundle_collision_rolls_back_atomic_commit(tmp_path: Path) -> None:
    source = _store(tmp_path / "source.db")
    workflow = _workflow()
    source.put_workflow(_WS, workflow, now=_T0)
    bundle = tmp_path / "workflow.roninbundle"
    export_workflow_bundle(source, _WS, (workflow.id,), bundle)

    target = _store(tmp_path / "target.db")
    target.put_workflow(_WS, _workflow("Different target definition"), now=_T0)

    plan = plan_workflow_bundle_import(bundle, target, target, _WS)
    assert plan.has_collisions
    with pytest.raises(WorkflowBundleImportConflict):
        commit_workflow_bundle_import(bundle, target, _WS, now=_T0)
    assert target.get_workflow(_WS, workflow.id) == _workflow("Different target definition")
