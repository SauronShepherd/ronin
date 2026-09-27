"""Durable-shaped persistence boundary for scheduler branch decisions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .branching import BranchDecision


class BranchStateConflict(RuntimeError):
    """A restart attempted to change an already persisted branch decision."""


@dataclass(frozen=True, slots=True)
class PersistedBranchDecision:
    workflow_id: str
    workflow_revision: int
    task_id: str
    snapshot_generation: int
    decision: BranchDecision
    skipped_tasks: tuple[str, ...] = ()


class BranchDecisionStore:
    """Small deterministic store contract suitable for a durable adapter."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, int, str], PersistedBranchDecision] = {}

    def record(
        self,
        workflow_id: str,
        workflow_revision: int,
        task_id: str,
        snapshot_generation: int,
        decision: BranchDecision,
        skipped_tasks: tuple[str, ...] = (),
    ) -> PersistedBranchDecision:
        if (
            not workflow_id
            or workflow_id != workflow_id.strip()
            or not task_id
            or task_id != task_id.strip()
        ):
            raise ValueError("workflow_id and task_id must be non-empty and trimmed")
        if workflow_revision < 1 or snapshot_generation < 1:
            raise ValueError("workflow revision and snapshot generation must be positive")
        normalized = tuple(sorted(set(skipped_tasks)))
        if any(not item or item != item.strip() for item in normalized):
            raise ValueError("skipped task ids must be non-empty and trimmed")
        item = PersistedBranchDecision(
            workflow_id, workflow_revision, task_id, snapshot_generation, decision, normalized
        )
        key = (workflow_id, workflow_revision, task_id)
        existing = self._items.get(key)
        if existing is not None:
            if existing != item:
                raise BranchStateConflict("branch decision conflicts with persisted snapshot")
            return existing
        self._items[key] = item
        return item

    def get(
        self, workflow_id: str, workflow_revision: int, task_id: str
    ) -> PersistedBranchDecision | None:
        return self._items.get((workflow_id, workflow_revision, task_id))


class SqliteBranchDecisionStore:
    """Restart-safe branch decision store with snapshot-conflict protection."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        with sqlite3.connect(self._path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS scheduler_branch_decisions ("
                "workflow_id TEXT NOT NULL, workflow_revision INTEGER NOT NULL, "
                "task_id TEXT NOT NULL, snapshot_generation INTEGER NOT NULL, "
                "decision_json TEXT NOT NULL, skipped_tasks_json TEXT NOT NULL, "
                "PRIMARY KEY (workflow_id, workflow_revision, task_id))"
            )

    def record(
        self,
        workflow_id: str,
        workflow_revision: int,
        task_id: str,
        snapshot_generation: int,
        decision: BranchDecision,
        skipped_tasks: tuple[str, ...] = (),
    ) -> PersistedBranchDecision:
        candidate = BranchDecisionStore().record(
            workflow_id,
            workflow_revision,
            task_id,
            snapshot_generation,
            decision,
            skipped_tasks,
        )
        with sqlite3.connect(self._path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT snapshot_generation, decision_json, skipped_tasks_json "
                "FROM scheduler_branch_decisions WHERE workflow_id=? "
                "AND workflow_revision=? AND task_id=?",
                (workflow_id, workflow_revision, task_id),
            ).fetchone()
            if row is not None:
                existing = PersistedBranchDecision(
                    workflow_id,
                    workflow_revision,
                    task_id,
                    int(row[0]),
                    BranchDecision.from_json(row[1]),
                    tuple(json.loads(row[2])),
                )
                if existing != candidate:
                    raise BranchStateConflict("branch decision conflicts with persisted snapshot")
                return existing
            connection.execute(
                "INSERT INTO scheduler_branch_decisions VALUES (?,?,?,?,?,?)",
                (
                    candidate.workflow_id,
                    candidate.workflow_revision,
                    candidate.task_id,
                    candidate.snapshot_generation,
                    candidate.decision.to_json(),
                    json.dumps(candidate.skipped_tasks),
                ),
            )
        return candidate

    def get(
        self, workflow_id: str, workflow_revision: int, task_id: str
    ) -> PersistedBranchDecision | None:
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT snapshot_generation, decision_json, skipped_tasks_json "
                "FROM scheduler_branch_decisions WHERE workflow_id=? "
                "AND workflow_revision=? AND task_id=?",
                (workflow_id, workflow_revision, task_id),
            ).fetchone()
        if row is None:
            return None
        return PersistedBranchDecision(
            workflow_id,
            workflow_revision,
            task_id,
            int(row[0]),
            BranchDecision.from_json(row[1]),
            tuple(json.loads(row[2])),
        )


__all__ = (
    "BranchDecisionStore",
    "BranchStateConflict",
    "PersistedBranchDecision",
    "SqliteBranchDecisionStore",
)
