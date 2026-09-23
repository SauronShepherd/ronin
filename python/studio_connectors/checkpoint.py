"""Durable restart-safe checkpoint contract for connector ingestion."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from studio_core import CheckpointStrategy, SourceCheckpoint


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
        return CheckpointHealth(
            identity, True, int(row[1]), str(row[0]), row[2] is not None, row[2]
        )

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
    ) -> CheckpointEvidence:
        self._validate_identity(identity)
        if (
            not output_id
            or output_id != output_id.strip()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in output_id)
        ):
            raise ValueError("output_id must be non-empty, trimmed and free of control characters")
        if (
            not output_digest
            or output_digest != output_digest.strip()
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in output_digest)
        ):
            raise ValueError(
                "output_digest must be non-empty, trimmed and free of control characters"
            )
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

    def _row(self, identity: str) -> tuple[str, str] | None:
        self._validate_identity(identity)
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT strategy,value FROM connector_checkpoints WHERE identity=?", (identity,)
            ).fetchone()
            return None if row is None else (str(row[0]), str(row[1]))

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
    def _digest(checkpoint: SourceCheckpoint) -> str:
        return hashlib.sha256(f"{checkpoint.strategy}:{checkpoint.value}".encode()).hexdigest()


__all__ = (
    "CheckpointEvidence",
    "CheckpointFenceConflict",
    "CheckpointHealth",
    "SqliteConnectorCheckpointStore",
)
