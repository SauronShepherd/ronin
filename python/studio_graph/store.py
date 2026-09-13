"""Persistent SQLite knowledge-graph store for materialized ontology snapshots."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from studio_core.ontology import KnowledgeObjectRef, OntologyId

from .contracts import GraphLink, GraphObject, GraphSnapshot


def _ref_json(ref: KnowledgeObjectRef) -> str:
    return json.dumps(
        {"object_type": ref.object_type, "key": dict(ref.key)},
        sort_keys=True,
        separators=(",", ":"),
    )


def _ref_from_json(payload: str) -> KnowledgeObjectRef:
    value = json.loads(payload)
    if not isinstance(value, dict) or set(value) != {"object_type", "key"}:
        raise ValueError("persisted graph object ref has invalid shape")
    object_type = value["object_type"]
    key = value["key"]
    if not isinstance(object_type, str) or not isinstance(key, dict):
        raise ValueError("persisted graph object ref fields are invalid")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in key.items()):
        raise ValueError("persisted graph object key must be string mapping")
    return KnowledgeObjectRef(object_type, tuple(sorted(key.items())))


class SqliteGraphStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS graph_objects (
                    ontology_id TEXT NOT NULL,
                    ontology_version TEXT NOT NULL,
                    object_ref_json TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    properties_json TEXT NOT NULL,
                    PRIMARY KEY(ontology_id, ontology_version, object_ref_json)
                );
                CREATE INDEX IF NOT EXISTS graph_objects_type_idx
                    ON graph_objects(ontology_id, ontology_version, object_type);
                CREATE TABLE IF NOT EXISTS graph_links (
                    ontology_id TEXT NOT NULL,
                    ontology_version TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    source_ref_json TEXT NOT NULL,
                    target_ref_json TEXT NOT NULL,
                    PRIMARY KEY(ontology_id, ontology_version, link_type, source_ref_json, target_ref_json)
                );
                CREATE INDEX IF NOT EXISTS graph_links_source_idx
                    ON graph_links(ontology_id, ontology_version, link_type, source_ref_json);
                CREATE INDEX IF NOT EXISTS graph_links_target_idx
                    ON graph_links(ontology_id, ontology_version, link_type, target_ref_json);
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def replace_snapshot(self, snapshot: GraphSnapshot) -> GraphSnapshot:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            identity = (snapshot.ontology_id.value, snapshot.ontology_version)
            connection.execute(
                "DELETE FROM graph_links WHERE ontology_id=? AND ontology_version=?",
                identity,
            )
            connection.execute(
                "DELETE FROM graph_objects WHERE ontology_id=? AND ontology_version=?",
                identity,
            )
            for item in snapshot.objects:
                connection.execute(
                    "INSERT INTO graph_objects(ontology_id,ontology_version,object_ref_json,object_type,properties_json) "
                    "VALUES (?,?,?,?,?)",
                    (
                        *identity,
                        _ref_json(item.ref),
                        item.ref.object_type,
                        json.dumps(dict(item.properties), sort_keys=True, separators=(",", ":")),
                    ),
                )
            for edge in snapshot.links:
                connection.execute(
                    "INSERT INTO graph_links(ontology_id,ontology_version,link_type,source_ref_json,target_ref_json) "
                    "VALUES (?,?,?,?,?)",
                    (*identity, edge.link_type, _ref_json(edge.source), _ref_json(edge.target)),
                )
            connection.commit()
            return snapshot
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _object(ref_json: str, properties_json: str) -> GraphObject:
        properties = json.loads(properties_json)
        if not isinstance(properties, dict):
            raise ValueError("persisted graph properties must be an object")
        return GraphObject(
            _ref_from_json(ref_json),
            tuple(sorted(properties.items())),
        )

    def get_object(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        ref: KnowledgeObjectRef,
    ) -> GraphObject | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT properties_json FROM graph_objects WHERE ontology_id=? "
                "AND ontology_version=? AND object_ref_json=?",
                (ontology_id.value, ontology_version, _ref_json(ref)),
            ).fetchone()
            return None if row is None else self._object(_ref_json(ref), row[0])
        finally:
            connection.close()

    def scan_objects(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        object_type: str,
    ) -> tuple[GraphObject, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT object_ref_json,properties_json FROM graph_objects WHERE ontology_id=? "
                "AND ontology_version=? AND object_type=? ORDER BY object_ref_json",
                (ontology_id.value, ontology_version, object_type),
            ).fetchall()
            return tuple(self._object(row[0], row[1]) for row in rows)
        finally:
            connection.close()

    def neighbors(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        ref: KnowledgeObjectRef,
        *,
        link_type: str,
        direction: str,
    ) -> tuple[GraphObject, ...]:
        if direction not in {"out", "in"}:
            raise ValueError("graph neighbor direction must be out or in")
        source_column = "source_ref_json" if direction == "out" else "target_ref_json"
        target_column = "target_ref_json" if direction == "out" else "source_ref_json"
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT {target_column} FROM graph_links WHERE ontology_id=? "
                f"AND ontology_version=? AND link_type=? AND {source_column}=? "
                f"ORDER BY {target_column}",
                (ontology_id.value, ontology_version, link_type, _ref_json(ref)),
            ).fetchall()
            result: list[GraphObject] = []
            for (target_ref_json,) in rows:
                row = connection.execute(
                    "SELECT properties_json FROM graph_objects WHERE ontology_id=? "
                    "AND ontology_version=? AND object_ref_json=?",
                    (ontology_id.value, ontology_version, target_ref_json),
                ).fetchone()
                if row is None:
                    raise RuntimeError("graph link references missing persisted object")
                result.append(self._object(target_ref_json, row[0]))
            return tuple(result)
        finally:
            connection.close()


__all__ = ("SqliteGraphStore",)
