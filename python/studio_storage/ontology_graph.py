"""Durable SQLite persistence for materialized ontology graph views."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from studio_core import ActionExecution, KnowledgeGraph, KnowledgeObject, KnowledgeObjectRef


class KnowledgeGraphConflict(RuntimeError):
    """Raised when graph identity is written with a different immutable payload."""


class SqliteKnowledgeGraphStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS knowledge_graphs ("
                "graph_id TEXT PRIMARY KEY, graph_json TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ontology_action_replays ("
                "idempotency_key TEXT PRIMARY KEY, action_name TEXT NOT NULL, "
                "target_json TEXT NOT NULL, execution_json TEXT NOT NULL)"
            )

    @staticmethod
    def _ref(ref: KnowledgeObjectRef) -> dict[str, object]:
        return {"object_type": ref.object_type, "key": list(ref.key)}

    @classmethod
    def _payload(cls, graph: KnowledgeGraph) -> str:
        return json.dumps(
            {
                "objects": [
                    {"ref": cls._ref(item.ref), "properties": list(item.properties)}
                    for item in graph.objects
                ],
                "links": [[cls._ref(source), cls._ref(target)] for source, target in graph.links],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def _graph(cls, payload: str) -> KnowledgeGraph:
        value = json.loads(payload)
        if not isinstance(value, dict) or set(value) != {"objects", "links"}:
            raise ValueError("knowledge graph payload has invalid shape")

        def ref(raw: object) -> KnowledgeObjectRef:
            if not isinstance(raw, dict) or set(raw) != {"object_type", "key"}:
                raise ValueError("knowledge graph reference has invalid shape")
            return KnowledgeObjectRef(
                str(raw["object_type"]), tuple(tuple(item) for item in raw["key"])
            )

        objects = []
        for raw in value["objects"]:
            if not isinstance(raw, dict) or set(raw) != {"ref", "properties"}:
                raise ValueError("knowledge graph object has invalid shape")
            objects.append(
                KnowledgeObject(ref(raw["ref"]), tuple(tuple(item) for item in raw["properties"]))
            )
        links = tuple((ref(pair[0]), ref(pair[1])) for pair in value["links"])
        return KnowledgeGraph(tuple(objects), links)

    def put(self, graph_id: str, graph: KnowledgeGraph) -> KnowledgeGraph:
        if not graph_id or graph_id != graph_id.strip() or "\x00" in graph_id:
            raise ValueError("graph_id must be non-empty and trimmed")
        payload = self._payload(graph)
        with sqlite3.connect(self._path) as connection:
            existing = connection.execute(
                "SELECT graph_json FROM knowledge_graphs WHERE graph_id=?", (graph_id,)
            ).fetchone()
            if existing is not None and existing[0] != payload:
                raise KnowledgeGraphConflict(
                    f"graph already exists with different content: {graph_id}"
                )
            connection.execute(
                "INSERT OR IGNORE INTO knowledge_graphs(graph_id,graph_json) VALUES (?,?)",
                (graph_id, payload),
            )
        return graph

    def get(self, graph_id: str) -> KnowledgeGraph | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT graph_json FROM knowledge_graphs WHERE graph_id=?", (graph_id,)
            ).fetchone()
        return None if row is None else self._graph(str(row[0]))

    def get_action_replay(self, idempotency_key: str) -> ActionExecution | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT execution_json FROM ontology_action_replays WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        return ActionExecution(
            value["action"],
            KnowledgeObjectRef(
                value["target"]["object_type"],
                tuple(tuple(item) for item in value["target"]["key"]),
            ),
            idempotency_key,
            value["output"],
        )

    def record_action_replay(self, execution: ActionExecution) -> None:
        if execution.idempotency_key is None:
            raise ValueError("action replay requires an idempotency key")
        target = self._ref(execution.target)
        payload = json.dumps(
            {"action": execution.action, "target": target, "output": dict(execution.output)},
            sort_keys=True,
            separators=(",", ":"),
        )
        with sqlite3.connect(self._path) as connection:
            existing = connection.execute(
                "SELECT action_name,target_json,execution_json "
                "FROM ontology_action_replays WHERE idempotency_key=?",
                (execution.idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing[2] != payload:
                    raise KnowledgeGraphConflict("action idempotency key has conflicting content")
                return
            connection.execute(
                "INSERT INTO ontology_action_replays("
                "idempotency_key,action_name,target_json,execution_json) "
                "VALUES (?,?,?,?)",
                (
                    execution.idempotency_key,
                    execution.action,
                    json.dumps(target, sort_keys=True),
                    payload,
                ),
            )


__all__ = ("KnowledgeGraphConflict", "SqliteKnowledgeGraphStore")
