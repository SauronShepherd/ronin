from pathlib import Path

from studio_core import KnowledgeGraph, KnowledgeObject, KnowledgeObjectRef
from studio_storage import SqliteKnowledgeGraphStore


def test_knowledge_graph_store_round_trips_objects_and_links(tmp_path: Path) -> None:
    source = KnowledgeObject(KnowledgeObjectRef("Customer", (("id", "1"),)), (("id", 1),))
    target = KnowledgeObject(KnowledgeObjectRef("Order", (("id", "9"),)), (("id", 9),))
    graph = KnowledgeGraph((source, target), ((source.ref, target.ref),))
    store = SqliteKnowledgeGraphStore(tmp_path / "graph.sqlite")
    assert store.put("graph-1", graph) == graph
    assert store.get("graph-1") == graph
