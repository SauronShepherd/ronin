"""Durable SQLite metadata for Synthetic Data Studio runs.

This adapter intentionally stores authored plans and lifecycle metadata only.
Generated rows remain artifacts owned by the output/catalog storage adapter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from studio_storage.sqlite import open_database


class SqliteSyntheticRunStore:
    """Small transactional store for idempotent local run submission."""

    def __init__(self, path: Path) -> None:
        self._path = path
        connection = open_database(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sds_runs ("
                "run_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, "
                "plan_json TEXT NOT NULL, plan_fingerprint TEXT NOT NULL, "
                "status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL)"
            )
        finally:
            connection.close()

    def create_or_get(
        self,
        *,
        run_id: str,
        idempotency_key: str,
        plan_json: str,
        plan_fingerprint: str,
        created_at: str,
    ) -> dict[str, Any]:
        if not idempotency_key.strip():
            raise ValueError("idempotency key is required")
        connection = open_database(self._path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM sds_runs WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                if existing["plan_fingerprint"] != plan_fingerprint:
                    raise ValueError("idempotency key already belongs to another plan")
                connection.execute("COMMIT")
                return dict(existing)
            connection.execute(
                "INSERT INTO sds_runs(run_id,idempotency_key,plan_json,plan_fingerprint,status,"
                "created_at) "
                "VALUES (?,?,?,?,?,?)",
                (run_id, idempotency_key, plan_json, plan_fingerprint, "created", created_at),
            )
            connection.execute("COMMIT")
            return {
                "run_id": run_id,
                "idempotency_key": idempotency_key,
                "plan_json": plan_json,
                "plan_fingerprint": plan_fingerprint,
                "status": "created",
                "error": None,
                "created_at": created_at,
            }
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def update_status(self, run_id: str, status: str, *, error: str | None = None) -> None:
        connection = open_database(self._path)
        try:
            cursor = connection.execute(
                "UPDATE sds_runs SET status=?,error=? WHERE run_id=?",
                (status, error, run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(run_id)
        finally:
            connection.close()

    def get(self, run_id: str) -> dict[str, Any] | None:
        connection = open_database(self._path)
        try:
            row = connection.execute("SELECT * FROM sds_runs WHERE run_id=?", (run_id,)).fetchone()
            return None if row is None else dict(row)
        finally:
            connection.close()


def canonical_plan_json(payload: dict[str, Any]) -> str:
    """Return deterministic JSON for persistence and request digests."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


__all__ = ["SqliteSyntheticRunStore", "canonical_plan_json"]
