import pytest

from studio_core import ActionType, KnowledgeGraph, KnowledgeObject, KnowledgeObjectRef
from studio_execution import OntologyHTTPAdapter
from studio_storage import SqliteKnowledgeGraphStore


class _Graphs:
    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    def get(self, graph_id: str) -> KnowledgeGraph | None:
        return self.graph if graph_id == "graph-1" else None


def test_ontology_http_adapter_executes_bounded_rql() -> None:
    graph = KnowledgeGraph(
        (
            KnowledgeObject(
                KnowledgeObjectRef("Person", (("id", "1"),)),
                (("name", "Ada"),),
            ),
        ),
        (),
    )
    result = OntologyHTTPAdapter(None, _Graphs(graph)).query(
        "graph-1", "SELECT Person WHERE name = 'Ada' LIMIT 1"
    )
    assert len(result.objects) == 1
    assert dict(result.objects[0].properties)["name"] == "Ada"
    assert (
        len(
            adapter_objects := OntologyHTTPAdapter(None, _Graphs(graph)).list_objects(
                "graph-1", "Person"
            )
        )
        == 1
    )
    assert adapter_objects[0].ref.object_type == "Person"


def test_ontology_http_adapter_dispatches_authorized_replayable_action(tmp_path) -> None:
    store = SqliteKnowledgeGraphStore(tmp_path / "graph.sqlite")
    adapter = OntologyHTTPAdapter(
        None, store, authorize=lambda _requirement: True, write=lambda *_args: {"ok": True}
    )
    action = ActionType("promote", "Person", ("value",), idempotent=True)
    target = KnowledgeObjectRef("Person", (("id", "1"),))
    calls = []
    result = adapter.execute_action(
        action,
        target,
        {"value": "gold"},
        authorize=lambda _requirement: True,
        write=lambda *_args: calls.append(True) or {"ok": True},
        idempotency_key="action-1",
    )
    replay = adapter.execute_action(
        action,
        target,
        {"value": "gold"},
        authorize=lambda _requirement: True,
        write=lambda *_args: calls.append(True) or {"ok": False},
        idempotency_key="action-1",
    )
    assert result == replay


def test_ontology_http_rejects_ambiguous_action_target_and_key(tmp_path) -> None:
    store = SqliteKnowledgeGraphStore(tmp_path / "graph.sqlite")
    adapter = OntologyHTTPAdapter(
        None, store, authorize=lambda _requirement: True, write=lambda *_args: {"ok": True}
    )
    action = ActionType("promote", "Person", (), idempotent=False).to_payload()
    with pytest.raises(ValueError, match="target has invalid shape"):
        adapter.execute_action_payload(
            "graph-1",
            {"action": action, "target": {"object_type": "Person"}, "inputs": {}},
        )
    with pytest.raises(ValueError, match="key pair"):
        adapter.execute_action_payload(
            "graph-1",
            {
                "action": action,
                "target": {"object_type": "Person", "key": []},
                "inputs": {},
            },
        )
    with pytest.raises(ValueError, match="idempotency_key"):
        adapter.execute_action_payload(
            "graph-1",
            {
                "action": action,
                "target": {"object_type": "Person", "key": [["id", "1"]]},
                "inputs": {},
                "idempotency_key": " ",
            },
        )
