"""Durable restart-safe checkpoint contract for connector ingestion."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from studio_core import (
    AssetRevision,
    CatalogAsset,
    CheckpointStrategy,
    LineageEdge,
    SourceCheckpoint,
    WorkspaceId,
)


class CheckpointFenceConflict(RuntimeError):
    """Another owner has acquired the checkpoint lease."""


@dataclass(frozen=True, slots=True)
class CheckpointEvidence:
    identity: str
    previous_digest: str
    next_digest: str
    output_id: str
    output_digest: str
    fence: int

    def to_payload(self) -> dict[str, object]:
        """Return secret-free, stable evidence suitable for Run/Evidence storage."""
        return {
            "schema": "ronin.connector-checkpoint-evidence/v1",
            "identity": self.identity,
            "previous_digest": self.previous_digest,
            "next_digest": self.next_digest,
            "output_id": self.output_id,
            "output_digest": self.output_digest,
            "fence": self.fence,
        }


@dataclass(frozen=True, slots=True)
class CheckpointHealth:
    identity: str
    present: bool
    fence: int | None
    checkpoint_digest: str | None
    output_committed: bool
    evidence_digest: str | None

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "ronin.connector-checkpoint-health/v1",
            "identity": self.identity,
            "present": self.present,
            "fence": self.fence,
            "checkpoint_digest": self.checkpoint_digest,
            "output_committed": self.output_committed,
            "evidence_digest": self.evidence_digest,
        }


class SqliteConnectorCheckpointStore:
    """CAS + fencing store whose commit API enforces output-before-checkpoint."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS connector_checkpoints ("
                "identity TEXT PRIMARY KEY, strategy TEXT NOT NULL, value TEXT NOT NULL, "
                "digest TEXT NOT NULL, previous_digest TEXT, fence INTEGER NOT NULL, "
                "output_id TEXT, output_digest TEXT)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS connector_discovery_cursor_keys ("
                "key_id INTEGER PRIMARY KEY CHECK (key_id = 1), signing_key BLOB NOT NULL)"
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(connector_checkpoints)")
            }
            if "previous_digest" not in columns:
                connection.execute(
                    "ALTER TABLE connector_checkpoints ADD COLUMN previous_digest TEXT"
                )

    def get(self, identity: str) -> SourceCheckpoint | None:
        row = self._row(identity)
        return None if row is None else SourceCheckpoint(cast(CheckpointStrategy, row[0]), row[1])

    def get_or_create_discovery_cursor_key(self) -> bytes:
        """Return the database-shared HMAC key used to authenticate discovery cursors."""
        with sqlite3.connect(self._path, isolation_level=None) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT signing_key FROM connector_discovery_cursor_keys WHERE key_id=1"
            ).fetchone()
            if row is None:
                key = secrets.token_bytes(32)
                connection.execute(
                    "INSERT INTO connector_discovery_cursor_keys(key_id,signing_key) VALUES(1,?)",
                    (key,),
                )
                connection.execute("COMMIT")
                return key
            key = row[0]
            connection.execute("COMMIT")
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("stored connector discovery cursor key is invalid")
        return key

    def get_evidence(self, identity: str) -> CheckpointEvidence | None:
        self._validate_identity(identity)
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT strategy,value,digest,previous_digest,fence,output_id,output_digest "
                "FROM connector_checkpoints WHERE identity=?",
                (identity,),
            ).fetchone()
        if row is None or row[5] is None or row[6] is None:
            return None
        return CheckpointEvidence(identity, row[3] or row[2], row[2], row[5], row[6], int(row[4]))

    def health(self, identity: str) -> CheckpointHealth:
        self._validate_identity(identity)
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT digest,fence,output_digest FROM connector_checkpoints WHERE identity=?",
                (identity,),
            ).fetchone()
        if row is None:
            return CheckpointHealth(identity, False, None, None, False, None)
        committed = row[2] is not None
        return CheckpointHealth(
            identity, committed, int(row[1]), str(row[0]) if committed else None, committed, row[2]
        )

    def list_committed_outputs(self, *, max_outputs: int = 10_000) -> tuple[tuple[str, str], ...]:
        """List committed output locators and digests within an explicit bound."""
        if max_outputs < 1 or max_outputs > 100_000:
            raise ValueError("max_outputs must be between 1 and 100000")
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                "SELECT output_id,output_digest FROM connector_checkpoints "
                "WHERE output_id IS NOT NULL OR output_digest IS NOT NULL "
                "ORDER BY identity LIMIT ?",
                (max_outputs + 1,),
            ).fetchall()
        if len(rows) > max_outputs:
            raise ValueError("connector output inventory exceeded its bound")
        outputs: list[tuple[str, str]] = []
        for output_id, output_digest in rows:
            if not isinstance(output_id, str) or not isinstance(output_digest, str):
                raise ValueError("connector output checkpoint has an incomplete identity")
            outputs.append((output_id, output_digest))
        return tuple(outputs)

    def acquire(self, identity: str) -> int:
        self._validate_identity(identity)
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT fence FROM connector_checkpoints WHERE identity=?", (identity,)
            ).fetchone()
            fence = 1 if row is None else int(row[0]) + 1
            if row is None:
                connection.execute(
                    "INSERT INTO connector_checkpoints(identity,strategy,value,digest,fence) "
                    "VALUES (?,?,?,?,?)",
                    (identity, "snapshot", "", hashlib.sha256(b"").hexdigest(), fence),
                )
            else:
                connection.execute(
                    "UPDATE connector_checkpoints SET fence=? WHERE identity=?",
                    (fence, identity),
                )
            return fence

    def commit_output_then_checkpoint(
        self,
        identity: str,
        expected: SourceCheckpoint | None,
        next_checkpoint: SourceCheckpoint,
        *,
        output_id: str,
        output_digest: str,
        fence: int,
        output_committed: bool,
        catalog_commit: tuple[
            WorkspaceId,
            AssetRevision,
            LineageEdge,
            str,
            tuple[str, str, str],
        ]
        | None = None,
    ) -> CheckpointEvidence:
        self._validate_identity(identity)
        self._validate_output(output_id, "output_id")
        self._validate_output(output_digest, "output_digest")
        if not output_committed:
            raise CheckpointFenceConflict(
                "checkpoint cannot advance before output commit is acknowledged"
            )
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT strategy,value,digest,previous_digest,fence,output_id,output_digest "
                "FROM connector_checkpoints WHERE identity=?",
                (identity,),
            ).fetchone()
            if row is None or int(row[4]) != fence:
                connection.rollback()
                raise CheckpointFenceConflict("checkpoint fence is stale")
            previous_digest = row[2]
            if (
                previous_digest == self._digest(next_checkpoint)
                and row[5] == output_id
                and row[6] == output_digest
            ):
                connection.rollback()
                return CheckpointEvidence(
                    identity,
                    row[3] or previous_digest,
                    previous_digest,
                    output_id,
                    output_digest,
                    fence,
                )
            if expected is not None and previous_digest != self._digest(expected):
                connection.rollback()
                raise CheckpointFenceConflict("checkpoint CAS precondition failed")
            if catalog_commit is not None:
                (
                    workspace_id,
                    revision,
                    edge,
                    catalog_now,
                    source_binding,
                ) = catalog_commit
                self._commit_catalog_records(
                    connection,
                    workspace_id,
                    revision,
                    edge,
                    catalog_now,
                    source_binding,
                )
            connection.execute(
                "UPDATE connector_checkpoints SET strategy=?,value=?,digest=?,previous_digest=?,"
                "output_id=?,output_digest=? WHERE identity=? AND fence=? AND digest=?",
                (
                    next_checkpoint.strategy,
                    next_checkpoint.value,
                    self._digest(next_checkpoint),
                    previous_digest,
                    output_id,
                    output_digest,
                    identity,
                    fence,
                    previous_digest,
                ),
            )
            connection.commit()
        return CheckpointEvidence(
            identity,
            previous_digest,
            self._digest(next_checkpoint),
            output_id,
            output_digest,
            fence,
        )

    @staticmethod
    def _commit_catalog_records(
        connection: sqlite3.Connection,
        workspace_id: WorkspaceId,
        revision: AssetRevision,
        edge: LineageEdge,
        now: str,
        source_binding: tuple[str, str, str],
    ) -> None:
        """Persist sync revision and lineage in the same transaction as its checkpoint."""
        if not now or now != now.strip():
            raise ValueError("catalog commit timestamp must be non-empty and trimmed")
        workspace = connection.execute(
            "SELECT archived_at FROM workspaces WHERE workspace_id=?", (str(workspace_id),)
        ).fetchone()
        if workspace is None or workspace[0] is not None:
            raise CheckpointFenceConflict("catalog workspace is missing or archived")
        if revision.ref != edge.target or edge.mode != "observed":
            raise ValueError("connector lineage must target the committed revision as observed")
        for ref in (edge.source, edge.target):
            asset = connection.execute(
                "SELECT 1 FROM catalog_assets WHERE workspace_id=? AND asset_id=?",
                (str(workspace_id), str(ref.asset_id)),
            ).fetchone()
            if asset is None:
                raise ValueError(f"connector lineage asset does not exist: {ref.asset_id}")
        source_definition = connection.execute(
            "SELECT definition_json FROM catalog_assets WHERE workspace_id=? AND asset_id=?",
            (str(workspace_id), str(edge.source.asset_id)),
        ).fetchone()
        source_asset = CatalogAsset.from_json(source_definition[0])
        expected_binding = dict(
            zip(
                ("ronin.connector_id", "ronin.connection_ref", "ronin.asset_ref"),
                source_binding,
                strict=True,
            )
        )
        if any(
            dict(source_asset.properties).get(key) != value
            for key, value in expected_binding.items()
        ):
            raise ValueError("connector sync source does not match the governed catalog binding")
        revision_payload = revision.to_json()
        existing_revision = connection.execute(
            "SELECT revision_json FROM catalog_asset_revisions "
            "WHERE workspace_id=? AND asset_id=? AND version=?",
            (str(workspace_id), str(revision.ref.asset_id), str(revision.ref.version)),
        ).fetchone()
        if existing_revision is not None and existing_revision[0] != revision_payload:
            raise ValueError("connector destination revision conflicts with existing content")
        if existing_revision is None:
            connection.execute(
                "INSERT INTO catalog_asset_revisions("
                "workspace_id,asset_id,version,revision_json,created_at) "
                "VALUES (?,?,?,?,?)",
                (
                    str(workspace_id),
                    str(revision.ref.asset_id),
                    str(revision.ref.version),
                    revision_payload,
                    now,
                ),
            )
        source_revision = connection.execute(
            "SELECT 1 FROM catalog_asset_revisions "
            "WHERE workspace_id=? AND asset_id=? AND version=?",
            (str(workspace_id), str(edge.source.asset_id), str(edge.source.version)),
        ).fetchone()
        if source_revision is None:
            raise ValueError("connector lineage source revision does not exist")
        edge_payload = edge.to_json()
        existing_edge = connection.execute(
            "SELECT edge_json FROM lineage_edges WHERE workspace_id=? AND edge_digest=?",
            (str(workspace_id), edge.digest),
        ).fetchone()
        if existing_edge is not None and existing_edge[0] != edge_payload:
            raise ValueError("connector lineage digest conflicts with existing content")
        if existing_edge is None:
            connection.execute(
                "INSERT INTO lineage_edges("
                "workspace_id,edge_digest,source_asset_id,source_version,"
                "target_asset_id,target_version,edge_json,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(workspace_id),
                    edge.digest,
                    str(edge.source.asset_id),
                    str(edge.source.version),
                    str(edge.target.asset_id),
                    str(edge.target.version),
                    edge_payload,
                    now,
                ),
            )

    def _row(self, identity: str) -> tuple[str, str] | None:
        self._validate_identity(identity)
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT strategy,value,output_digest FROM connector_checkpoints WHERE identity=?",
                (identity,),
            ).fetchone()
            return None if row is None or row[2] is None else (str(row[0]), str(row[1]))

    @staticmethod
    def _validate_identity(identity: str) -> None:
        if (
            not identity
            or identity != identity.strip()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in identity)
        ):
            raise ValueError(
                "checkpoint identity must be non-empty, trimmed and free of control characters"
            )

    @staticmethod
    def _validate_output(value: str, name: str) -> None:
        if (
            not value
            or value != value.strip()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        ):
            raise ValueError(f"{name} must be non-empty, trimmed and free of control characters")

    @staticmethod
    def _digest(checkpoint: SourceCheckpoint) -> str:
        return hashlib.sha256(f"{checkpoint.strategy}:{checkpoint.value}".encode()).hexdigest()


class PostgresConnectorCheckpointStore:
    """PostgreSQL CAS + fencing store with a bounded output inventory."""

    def __init__(self, dsn: str, *, application_name: str = "ronin-connector-checkpoints") -> None:
        if not dsn or dsn != dsn.strip():
            raise ValueError("PostgreSQL DSN must be non-empty and trimmed")
        if not application_name or application_name != application_name.strip():
            raise ValueError("application_name must be non-empty and trimmed")
        self._dsn = dsn
        self._application_name = application_name
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_connector_checkpoints ("
                    "identity TEXT PRIMARY KEY, strategy TEXT NOT NULL, value TEXT NOT NULL, "
                    "digest TEXT NOT NULL, previous_digest TEXT, fence BIGINT NOT NULL, "
                    "output_id TEXT, output_digest TEXT)"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_connector_discovery_cursor_keys ("
                    "key_id SMALLINT PRIMARY KEY CHECK (key_id = 1), signing_key BYTEA NOT NULL)"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> Any:
        from studio_storage.postgres_core import _psycopg

        psycopg, dict_row = _psycopg()
        return psycopg.connect(
            self._dsn,
            autocommit=False,
            row_factory=dict_row,
            application_name=self._application_name,
        )

    def get_or_create_discovery_cursor_key(self) -> bytes:
        """Return the database-shared HMAC key used to authenticate discovery cursors."""
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_connector_discovery_cursor_keys(key_id,signing_key) "
                    "VALUES(1,%s) ON CONFLICT (key_id) DO NOTHING",
                    (secrets.token_bytes(32),),
                )
                cursor.execute(
                    "SELECT signing_key FROM ronin_connector_discovery_cursor_keys WHERE key_id=1"
                )
                row = cursor.fetchone()
            connection.commit()
            key = row["signing_key"] if row is not None else None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError("stored connector discovery cursor key is invalid")
        return key

    def get(self, identity: str) -> SourceCheckpoint | None:
        row = self._row(identity)
        return None if row is None else SourceCheckpoint(cast(CheckpointStrategy, row[0]), row[1])

    def get_evidence(self, identity: str) -> CheckpointEvidence | None:
        self._validate_identity(identity)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT digest,previous_digest,fence,output_id,output_digest "
                    "FROM ronin_connector_checkpoints WHERE identity=%s",
                    (identity,),
                )
                row = cursor.fetchone()
            if row is None or row["output_id"] is None or row["output_digest"] is None:
                return None
            return CheckpointEvidence(
                identity,
                row["previous_digest"] or row["digest"],
                row["digest"],
                row["output_id"],
                row["output_digest"],
                int(row["fence"]),
            )
        finally:
            connection.close()

    def health(self, identity: str) -> CheckpointHealth:
        self._validate_identity(identity)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT digest,fence,output_digest FROM ronin_connector_checkpoints "
                    "WHERE identity=%s",
                    (identity,),
                )
                row = cursor.fetchone()
            if row is None:
                return CheckpointHealth(identity, False, None, None, False, None)
            committed = row["output_digest"] is not None
            return CheckpointHealth(
                identity,
                committed,
                int(row["fence"]),
                row["digest"] if committed else None,
                committed,
                row["output_digest"],
            )
        finally:
            connection.close()

    def list_committed_outputs(self, *, max_outputs: int = 10_000) -> tuple[tuple[str, str], ...]:
        if max_outputs < 1 or max_outputs > 100_000:
            raise ValueError("max_outputs must be between 1 and 100000")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT output_id,output_digest FROM ronin_connector_checkpoints "
                    "WHERE output_id IS NOT NULL OR output_digest IS NOT NULL "
                    "ORDER BY identity LIMIT %s",
                    (max_outputs + 1,),
                )
                rows = cursor.fetchall()
            if len(rows) > max_outputs:
                raise ValueError("connector output inventory exceeded its bound")
            outputs: list[tuple[str, str]] = []
            for row in rows:
                output_id, output_digest = row["output_id"], row["output_digest"]
                if not isinstance(output_id, str) or not isinstance(output_digest, str):
                    raise ValueError("connector output checkpoint has an incomplete identity")
                outputs.append((output_id, output_digest))
            return tuple(outputs)
        finally:
            connection.close()

    def acquire(self, identity: str) -> int:
        self._validate_identity(identity)
        empty_digest = hashlib.sha256(b"").hexdigest()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_connector_checkpoints "
                    "(identity,strategy,value,digest,fence) VALUES (%s,%s,%s,%s,0) "
                    "ON CONFLICT (identity) DO NOTHING",
                    (identity, "snapshot", "", empty_digest),
                )
                cursor.execute(
                    "UPDATE ronin_connector_checkpoints SET fence=fence+1 "
                    "WHERE identity=%s RETURNING fence",
                    (identity,),
                )
                row = cursor.fetchone()
            connection.commit()
            return int(row["fence"])
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def commit_output_then_checkpoint(
        self,
        identity: str,
        expected: SourceCheckpoint | None,
        next_checkpoint: SourceCheckpoint,
        *,
        output_id: str,
        output_digest: str,
        fence: int,
        output_committed: bool,
        catalog_commit: tuple[
            WorkspaceId,
            AssetRevision,
            LineageEdge,
            str,
            tuple[str, str, str],
        ]
        | None = None,
    ) -> CheckpointEvidence:
        SqliteConnectorCheckpointStore._validate_identity(identity)
        SqliteConnectorCheckpointStore._validate_output(output_id, "output_id")
        SqliteConnectorCheckpointStore._validate_output(output_digest, "output_digest")
        if not output_committed:
            raise CheckpointFenceConflict(
                "checkpoint cannot advance before output commit is acknowledged"
            )
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT strategy,value,digest,previous_digest,fence,output_id,output_digest "
                    "FROM ronin_connector_checkpoints WHERE identity=%s FOR UPDATE",
                    (identity,),
                )
                row = cursor.fetchone()
                if row is None or int(row["fence"]) != fence:
                    raise CheckpointFenceConflict("checkpoint fence is stale")
                previous_digest = row["digest"]
                next_digest = self._digest(next_checkpoint)
                if (
                    previous_digest == next_digest
                    and row["output_id"] == output_id
                    and row["output_digest"] == output_digest
                ):
                    connection.rollback()
                    return CheckpointEvidence(
                        identity,
                        row["previous_digest"] or previous_digest,
                        previous_digest,
                        output_id,
                        output_digest,
                        fence,
                    )
                if expected is not None and previous_digest != self._digest(expected):
                    raise CheckpointFenceConflict("checkpoint CAS precondition failed")
                if catalog_commit is not None:
                    self._commit_catalog_records(connection, *catalog_commit)
                cursor.execute(
                    "UPDATE ronin_connector_checkpoints SET strategy=%s,value=%s,digest=%s,"
                    "previous_digest=%s,output_id=%s,output_digest=%s "
                    "WHERE identity=%s AND fence=%s AND digest=%s",
                    (
                        next_checkpoint.strategy,
                        next_checkpoint.value,
                        next_digest,
                        previous_digest,
                        output_id,
                        output_digest,
                        identity,
                        fence,
                        previous_digest,
                    ),
                )
                if cursor.rowcount != 1:
                    raise CheckpointFenceConflict("checkpoint fence is stale")
            connection.commit()
            return CheckpointEvidence(
                identity, previous_digest, next_digest, output_id, output_digest, fence
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _commit_catalog_records(
        connection: Any,
        workspace_id: WorkspaceId,
        revision: AssetRevision,
        edge: LineageEdge,
        now: str,
        source_binding: tuple[str, str, str],
    ) -> None:
        """Persist governed sync records inside the checkpoint transaction."""
        if not now or now != now.strip():
            raise ValueError("catalog commit timestamp must be non-empty and trimmed")
        if revision.ref != edge.target or edge.mode != "observed":
            raise ValueError("connector lineage must target the committed revision as observed")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT archived_at FROM ronin_workspaces WHERE workspace_id=%s FOR SHARE",
                (str(workspace_id),),
            )
            workspace = cursor.fetchone()
            if workspace is None or workspace["archived_at"] is not None:
                raise CheckpointFenceConflict("catalog workspace is missing or archived")
            for ref in (edge.source, edge.target):
                cursor.execute(
                    "SELECT 1 FROM ronin_catalog_assets WHERE workspace_id=%s AND asset_id=%s",
                    (str(workspace_id), str(ref.asset_id)),
                )
                if cursor.fetchone() is None:
                    raise ValueError(f"connector lineage asset does not exist: {ref.asset_id}")
            cursor.execute(
                "SELECT definition_json FROM ronin_catalog_assets "
                "WHERE workspace_id=%s AND asset_id=%s",
                (str(workspace_id), str(edge.source.asset_id)),
            )
            source_definition = cursor.fetchone()
            source_asset = CatalogAsset.from_json(source_definition["definition_json"])
            expected_binding = dict(
                zip(
                    ("ronin.connector_id", "ronin.connection_ref", "ronin.asset_ref"),
                    source_binding,
                    strict=True,
                )
            )
            if any(
                dict(source_asset.properties).get(key) != value
                for key, value in expected_binding.items()
            ):
                raise ValueError(
                    "connector sync source does not match the governed catalog binding"
                )
            revision_payload = revision.to_json()
            cursor.execute(
                "SELECT revision_json FROM ronin_catalog_revisions "
                "WHERE workspace_id=%s AND asset_id=%s AND version=%s FOR UPDATE",
                (str(workspace_id), str(revision.ref.asset_id), str(revision.ref.version)),
            )
            existing_revision = cursor.fetchone()
            if (
                existing_revision is not None
                and existing_revision["revision_json"] != revision_payload
            ):
                raise ValueError("connector destination revision conflicts with existing content")
            if existing_revision is None:
                cursor.execute(
                    "INSERT INTO ronin_catalog_revisions("
                    "workspace_id,asset_id,version,revision_json,created_at) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (
                        str(workspace_id),
                        str(revision.ref.asset_id),
                        str(revision.ref.version),
                        revision_payload,
                        str(now),
                    ),
                )
            cursor.execute(
                "SELECT 1 FROM ronin_catalog_revisions "
                "WHERE workspace_id=%s AND asset_id=%s AND version=%s",
                (str(workspace_id), str(edge.source.asset_id), str(edge.source.version)),
            )
            if cursor.fetchone() is None:
                raise ValueError("connector lineage source revision does not exist")
            edge_payload = edge.to_json()
            cursor.execute(
                "SELECT edge_json FROM ronin_lineage_edges "
                "WHERE workspace_id=%s AND edge_digest=%s FOR UPDATE",
                (str(workspace_id), edge.digest),
            )
            existing_edge = cursor.fetchone()
            if existing_edge is not None and existing_edge["edge_json"] != edge_payload:
                raise ValueError("connector lineage digest conflicts with existing content")
            if existing_edge is None:
                cursor.execute(
                    "INSERT INTO ronin_lineage_edges("
                    "workspace_id,edge_digest,source_asset_id,source_version,"
                    "target_asset_id,target_version,edge_json,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        str(workspace_id),
                        edge.digest,
                        str(edge.source.asset_id),
                        str(edge.source.version),
                        str(edge.target.asset_id),
                        str(edge.target.version),
                        edge_payload,
                        str(now),
                    ),
                )

    def _row(self, identity: str) -> tuple[str, str] | None:
        self._validate_identity(identity)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT strategy,value,output_digest FROM ronin_connector_checkpoints "
                    "WHERE identity=%s",
                    (identity,),
                )
                row = cursor.fetchone()
            return (
                None
                if row is None or row["output_digest"] is None
                else (str(row["strategy"]), str(row["value"]))
            )
        finally:
            connection.close()

    @staticmethod
    def _validate_identity(identity: str) -> None:
        SqliteConnectorCheckpointStore._validate_identity(identity)

    @staticmethod
    def _digest(checkpoint: SourceCheckpoint) -> str:
        return SqliteConnectorCheckpointStore._digest(checkpoint)

    @staticmethod
    def _validate_output(value: str, name: str) -> None:
        if (
            not value
            or value != value.strip()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        ):
            raise ValueError(f"{name} must be non-empty, trimmed and free of control characters")


__all__ = (
    "CheckpointEvidence",
    "CheckpointFenceConflict",
    "CheckpointHealth",
    "PostgresConnectorCheckpointStore",
    "SqliteConnectorCheckpointStore",
)
