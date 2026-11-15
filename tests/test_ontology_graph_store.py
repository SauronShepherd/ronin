from pathlib import Path

import pytest
from studio_core import (
    ActionExecution,
    KnowledgeGraph,
    KnowledgeObject,
    KnowledgeObjectRef,
    WorkspaceId,
)
from studio_storage import KnowledgeGraphConflict, SqliteKnowledgeGraphStore


def test_knowledge_graph_store_round_trips_objects_and_links(tmp_path: Path) -> None:
    source = KnowledgeObject(KnowledgeObjectRef("Customer", (("id", "1"),)), (("id", 1),))
    target = KnowledgeObject(KnowledgeObjectRef("Order", (("id", "9"),)), (("id", 9),))
    graph = KnowledgeGraph((source, target), ((source.ref, target.ref),))
    store = SqliteKnowledgeGraphStore(tmp_path / "graph.sqlite")
    workspace = WorkspaceId("workspace-1")
    assert store.put(workspace, "graph-1", graph) == graph
    assert store.get(workspace, "graph-1") == graph
    assert store.get(WorkspaceId("workspace-2"), "graph-1") is None


def test_ontology_action_replay_is_durable_and_conflict_checked(tmp_path: Path) -> None:
    store = SqliteKnowledgeGraphStore(tmp_path / "graph.sqlite")
    execution = ActionExecution(
        "promote", KnowledgeObjectRef("Person", (("id", "1"),)), "idem-1", {"ok": True}
    )
    workspace = WorkspaceId("workspace-1")
    other_workspace = WorkspaceId("workspace-2")
    store.record_action_replay(workspace, execution)
    assert store.get_action_replay(workspace, "idem-1") == execution
    store.record_action_replay(workspace, execution)
    other_execution = ActionExecution(
        execution.action,
        execution.target,
        execution.idempotency_key,
        {"ok": "other"},
    )
    store.record_action_replay(other_workspace, other_execution)
    assert store.get_action_replay(other_workspace, "idem-1") == other_execution
    with pytest.raises(KnowledgeGraphConflict):
        store.record_action_replay(
            workspace,
            ActionExecution(
                execution.action, execution.target, execution.idempotency_key, {"ok": False}
            ),
        )
