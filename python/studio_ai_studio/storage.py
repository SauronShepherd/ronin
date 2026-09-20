"""SQLite persistence owned by AI Studio."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from .contracts import (
    AdapterKind,
    DesiredState,
    EndpointConfig,
    EndpointId,
    ModelSnapshot,
    ObservedState,
    PublicModelName,
)


class AIStudioConflict(RuntimeError):
    """Raised when an optimistic endpoint update loses a race."""


def migrate_ai_studio(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_studio_schema_migrations (
            version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ai_studio_endpoints (
            endpoint_id TEXT PRIMARY KEY, adapter TEXT NOT NULL, base_url TEXT NOT NULL,
            models_json TEXT NOT NULL, priority INTEGER NOT NULL, weight INTEGER NOT NULL,
            max_in_flight INTEGER NOT NULL, desired_state TEXT NOT NULL,
            observed_state TEXT NOT NULL, allow_http INTEGER NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS ai_studio_models (
            endpoint_id TEXT NOT NULL, provider_model_id TEXT NOT NULL,
            public_name TEXT NOT NULL, capabilities_json TEXT NOT NULL,
            context_window INTEGER, last_seen_at TEXT,
            PRIMARY KEY(endpoint_id, provider_model_id),
            FOREIGN KEY(endpoint_id) REFERENCES ai_studio_endpoints(endpoint_id)
        );
        INSERT OR IGNORE INTO ai_studio_schema_migrations(version) VALUES (1);
        """
    )


class SQLiteAIStudioStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        migrate_ai_studio(connection)

    def put_endpoint(self, endpoint: EndpointConfig, *, expected_version: int | None = None) -> int:
        current = self._connection.execute(
            "SELECT version FROM ai_studio_endpoints WHERE endpoint_id=?", (endpoint.id.value,)
        ).fetchone()
        if expected_version is not None and (
            current is None or current["version"] != expected_version
        ):
            raise AIStudioConflict(endpoint.id.value)
        version = 1 if current is None else int(current["version"]) + 1
        self._connection.execute(
            """INSERT INTO ai_studio_endpoints
            (endpoint_id,adapter,base_url,models_json,priority,weight,max_in_flight,
             desired_state,observed_state,allow_http,version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(endpoint_id) DO UPDATE SET adapter=excluded.adapter,
            base_url=excluded.base_url,models_json=excluded.models_json,
            priority=excluded.priority,weight=excluded.weight,max_in_flight=excluded.max_in_flight,
            desired_state=excluded.desired_state,allow_http=excluded.allow_http,version=excluded.version""",
            (endpoint.id.value, endpoint.adapter.value, endpoint.base_url,
             json.dumps([m.value for m in endpoint.models]), endpoint.priority, endpoint.weight,
             endpoint.max_in_flight, endpoint.desired_state.value, ObservedState.UNKNOWN.value,
             int(endpoint.allow_http), version),
        )
        self._connection.commit()
        return version

    def get_endpoint(
        self, endpoint_id: EndpointId
    ) -> tuple[EndpointConfig, ObservedState, int] | None:
        row = self._connection.execute(
            "SELECT * FROM ai_studio_endpoints WHERE endpoint_id=?", (endpoint_id.value,)
        ).fetchone()
        if row is None:
            return None
        endpoint = EndpointConfig(
            endpoint_id, AdapterKind(row["adapter"]), row["base_url"],
            tuple(PublicModelName(value) for value in json.loads(row["models_json"])),
            row["priority"], row["weight"], row["max_in_flight"],
            endpoint_desired(row["desired_state"]), bool(row["allow_http"]),
        )
        return endpoint, ObservedState(row["observed_state"]), row["version"]

    def set_observed_state(self, endpoint_id: EndpointId, state: ObservedState) -> None:
        self._connection.execute(
            "UPDATE ai_studio_endpoints SET observed_state=? WHERE endpoint_id=?",
            (state.value, endpoint_id.value),
        )
        self._connection.commit()

    def replace_models(self, snapshots: Iterable[ModelSnapshot]) -> None:
        rows = tuple(snapshots)
        for snapshot in rows:
            self._connection.execute(
                """INSERT INTO ai_studio_models
                (endpoint_id,provider_model_id,public_name,capabilities_json,context_window,last_seen_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(endpoint_id,provider_model_id) DO UPDATE SET
                public_name=excluded.public_name,capabilities_json=excluded.capabilities_json,
                context_window=excluded.context_window,last_seen_at=excluded.last_seen_at""",
                (snapshot.endpoint_id.value, snapshot.provider_model_id, snapshot.public_name.value,
                 json.dumps(sorted(capability.value for capability in snapshot.capabilities)),
                 snapshot.context_window, snapshot.last_seen_at),
            )
        self._connection.commit()


def endpoint_desired(value: str) -> DesiredState:
    return DesiredState(value)
