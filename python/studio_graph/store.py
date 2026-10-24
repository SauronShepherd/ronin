"""Persistent SQLite knowledge-graph store for materialized ontology snapshots."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from studio_core.ontology import KnowledgeObjectRef, OntologyId

from .contracts import GraphObject, GraphSnapshot


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
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
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
                CREATE INDEX IF NOT EXISTS graph_objects_type_ref_idx
                    ON graph_objects(ontology_id, ontology_version, object_type, object_ref_json);
                CREATE TABLE IF NOT EXISTS graph_links (
                    ontology_id TEXT NOT NULL,
                    ontology_version TEXT NOT NULL,
                    link_type TEXT NOT NULL,
                    source_ref_json TEXT NOT NULL,
                    target_ref_json TEXT NOT NULL,
                    PRIMARY KEY(
                        ontology_id, ontology_version, link_type, source_ref_json, target_ref_json
                    )
                );
                CREATE INDEX IF NOT EXISTS graph_links_source_idx
                    ON graph_links(ontology_id, ontology_version, link_type, source_ref_json);
                CREATE INDEX IF NOT EXISTS graph_links_target_idx
                    ON graph_links(ontology_id, ontology_version, link_type, target_ref_json);
                CREATE INDEX IF NOT EXISTS graph_links_target_source_idx
                    ON graph_links(
                        ontology_id, ontology_version, link_type, target_ref_json, source_ref_json
                    );
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5.0)

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
                    "INSERT INTO graph_objects("
                    "ontology_id,ontology_version,object_ref_json,object_type,properties_json) "
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
                    "INSERT INTO graph_links("
                    "ontology_id,ontology_version,link_type,source_ref_json,target_ref_json) "
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

    @contextmanager
    def read_snapshot(self, *, timeout_ms: int = 5_000) -> Iterator[SqliteGraphReadSession]:
        """Hold one SQLite read transaction across every operation in a graph query."""
        if (
            not isinstance(timeout_ms, int)
            or isinstance(timeout_ms, bool)
            or timeout_ms < 1
            or timeout_ms > 60_000
        ):
            raise ValueError("graph read timeout_ms must be an integer between 1 and 60000")
        connection = self._connect()
        try:
            deadline = time.monotonic() + timeout_ms / 1000
            connection.set_progress_handler(lambda: time.monotonic() >= deadline, 1_000)
            connection.execute("BEGIN")
            yield SqliteGraphReadSession(connection)
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()

    def get_object(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        ref: KnowledgeObjectRef,
    ) -> GraphObject | None:
        with self.read_snapshot() as reader:
            return reader.get_object(ontology_id, ontology_version, ref)

    def scan_objects(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        object_type: str,
        *,
        limit: int | None = None,
    ) -> tuple[GraphObject, ...]:
        with self.read_snapshot() as reader:
            return reader.scan_objects(
                ontology_id,
                ontology_version,
                object_type,
                limit=limit,
            )

    def neighbors_many(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        refs: tuple[KnowledgeObjectRef, ...],
        *,
        link_type: str,
        direction: str,
        limit: int | None = None,
    ) -> tuple[GraphObject, ...]:
        with self.read_snapshot() as reader:
            return reader.neighbors_many(
                ontology_id,
                ontology_version,
                refs,
                link_type=link_type,
                direction=direction,
                limit=limit,
            )

    def neighbors(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        ref: KnowledgeObjectRef,
        *,
        link_type: str,
        direction: str,
        limit: int | None = None,
    ) -> tuple[GraphObject, ...]:
        with self.read_snapshot() as reader:
            return reader.neighbors(
                ontology_id,
                ontology_version,
                ref,
                link_type=link_type,
                direction=direction,
                limit=limit,
            )


class SqliteGraphReadSession:
    """Read one stable materialized graph generation on a shared SQLite connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_object(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        ref: KnowledgeObjectRef,
    ) -> GraphObject | None:
        ref_json = _ref_json(ref)
        row = self._connection.execute(
            "SELECT properties_json FROM graph_objects WHERE ontology_id=? "
            "AND ontology_version=? AND object_ref_json=?",
            (ontology_id.value, ontology_version, ref_json),
        ).fetchone()
        return None if row is None else SqliteGraphStore._object(ref_json, row[0])

    def scan_objects(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        object_type: str,
        *,
        limit: int | None = None,
    ) -> tuple[GraphObject, ...]:
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 1_000_001
        ):
            raise ValueError("graph object scan limit must be an integer between 1 and 1000001")
        sql = (
            "SELECT object_ref_json,properties_json FROM graph_objects WHERE ontology_id=? "
            "AND ontology_version=? AND object_type=? ORDER BY object_ref_json"
        )
        params: tuple[object, ...] = (ontology_id.value, ontology_version, object_type)
        if limit is not None:
            sql += " LIMIT ?"
            params += (limit,)
        rows = self._connection.execute(sql, params).fetchall()
        return tuple(SqliteGraphStore._object(row[0], row[1]) for row in rows)

    def neighbors_many(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        refs: tuple[KnowledgeObjectRef, ...],
        *,
        link_type: str,
        direction: str,
        limit: int | None = None,
    ) -> tuple[GraphObject, ...]:
        if direction not in {"out", "in"}:
            raise ValueError("graph neighbor direction must be out or in")
        if limit is not None and (
            not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 1_000_001
        ):
            raise ValueError("graph neighbor limit must be an integer between 1 and 1000001")
        if not refs:
            return ()

        ordered_refs = tuple(sorted(set(refs), key=_ref_json))
        if direction == "out":
            filter_column = "l.source_ref_json"
            target_column = "l.target_ref_json"
            order_by = "l.source_ref_json,l.target_ref_json"
        else:
            filter_column = "l.target_ref_json"
            target_column = "l.source_ref_json"
            order_by = "l.target_ref_json,l.source_ref_json"

        result: list[GraphObject] = []
        for offset in range(0, len(ordered_refs), 500):
            remaining = None if limit is None else limit - len(result)
            if remaining == 0:
                break
            chunk = ordered_refs[offset : offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            # Identifiers are selected from the fixed direction allowlist; data stays bound.
            sql = (
                "SELECT o.object_ref_json,o.properties_json FROM graph_links AS l "  # noqa: S608
                "LEFT JOIN graph_objects AS o ON o.ontology_id=l.ontology_id "
                "AND o.ontology_version=l.ontology_version "
                f"AND o.object_ref_json={target_column} "  # noqa: S608
                "WHERE l.ontology_id=? AND l.ontology_version=? AND l.link_type=? "
                f"AND {filter_column} IN ({placeholders}) ORDER BY {order_by}"  # noqa: S608
            )  # noqa: S608
            params: tuple[object, ...] = (
                ontology_id.value,
                ontology_version,
                link_type,
                *(_ref_json(ref) for ref in chunk),
            )
            if remaining is not None:
                sql += " LIMIT ?"
                params += (remaining,)
            rows = self._connection.execute(sql, params).fetchall()
            for row in rows:
                if row[0] is None or row[1] is None:
                    raise RuntimeError("graph link references missing persisted object")
                result.append(SqliteGraphStore._object(row[0], row[1]))
        return tuple(result)

    def neighbors(
        self,
        ontology_id: OntologyId,
        ontology_version: str,
        ref: KnowledgeObjectRef,
        *,
        link_type: str,
        direction: str,
        limit: int | None = None,
    ) -> tuple[GraphObject, ...]:
        return self.neighbors_many(
            ontology_id,
            ontology_version,
            (ref,),
            link_type=link_type,
            direction=direction,
            limit=limit,
        )


__all__ = ("SqliteGraphReadSession", "SqliteGraphStore")
