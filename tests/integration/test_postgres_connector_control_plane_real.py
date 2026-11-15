"""Real control-plane journey for PostgreSQL discovery and preview."""

from __future__ import annotations

import http.client
import json
import os
import socket
from typing import Any
from uuid import uuid4

import pytest
from studio_cli.local_composed import build_local_composed_from_env
from studio_core import ConnectionDefinition, ConnectionId, SecretRef

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL connector control-plane qualification requires RONIN_POSTGRES_TEST_DSN",
)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request(
    address: tuple[str, int], method: str, path: str, body: object | None = None
) -> tuple[int, dict[str, Any]]:
    connection = http.client.HTTPConnection(*address, timeout=10)
    try:
        encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"Authorization": "Bearer control-token"}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=encoded, headers=headers)
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert isinstance(payload, dict)
        return response.status, payload
    finally:
        connection.close()


def test_postgres_connector_control_plane_discover_preview_survives_reopen(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict

    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    connection_parameters = conninfo_to_dict(dsn)
    password = str(connection_parameters.get("password") or "")
    if not password:
        pytest.skip("real PostgreSQL control-plane qualification requires password authentication")
    source_schema = f"control_plane_{uuid4().hex}"
    source_table = "events"
    with psycopg.connect(dsn) as database, database.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(source_schema)))
        cursor.execute(
            sql.SQL(
                "CREATE TABLE {}.{} ("
                "id bigint PRIMARY KEY, observed_at timestamptz NOT NULL, payload text NOT NULL)"
            ).format(sql.Identifier(source_schema), sql.Identifier(source_table))
        )
        cursor.execute(
            sql.SQL("INSERT INTO {}.{} VALUES (%s, %s, %s), (%s, %s, %s), (%s, %s, %s)").format(
                sql.Identifier(source_schema), sql.Identifier(source_table)
            ),
            (
                1,
                "2026-11-15T08:00:00+00:00",
                "alpha",
                2,
                "2026-11-15T08:00:00+00:00",
                "bravo",
                3,
                "2026-11-15T08:00:01+00:00",
                "charlie",
            ),
        )

    host = str(connection_parameters.get("host") or "127.0.0.1")
    port = str(connection_parameters.get("port") or "5432")
    database_name = str(connection_parameters.get("dbname") or "ronin_test")
    source_user = str(connection_parameters.get("user") or "ronin")
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", "workspace-pg-real")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_TOKEN", "control-token")
    monkeypatch.setenv(
        "RONIN_CONTROL_PLANE_PERMISSIONS",
        "scheduler.read,scheduler.write,workspace.read,workspace.write,project.read,project.write",
    )
    monkeypatch.setenv(
        "RONIN_TOKEN_SCOPES",
        (
            '{"version":1,"grants":[{"actions":["cancel","evidence:read",'
            '"execute","events","list","read","submit"],"constraints":{},'
            '"resource":{"identifier":null,"kind":"*"},"version":1}]}'
        ),
    )
    monkeypatch.setenv("RONIN_TOKEN", "job-token")
    monkeypatch.setenv("RONIN_PLUGIN_API", "legacy")
    monkeypatch.setenv("RONIN_PORT", str(_free_port()))
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(_free_port()))
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("RONIN_POSTGRES_DSN", dsn)
    monkeypatch.setenv("RONIN_REAL_PG_USER", source_user)
    monkeypatch.setenv("RONIN_REAL_PG_PASSWORD", password)

    source_connection = ConnectionDefinition(
        ConnectionId("conn-pg-real"),
        "Real PostgreSQL source",
        "postgresql",
        options=(
            ("connect_timeout", "5"),
            ("database", database_name),
            ("host", host),
            ("port", port),
            ("schema", source_schema),
            ("incremental_column", "observed_at"),
            ("tie_breaker_columns", "id"),
        ),
        secret_refs=(
            ("password", SecretRef("secret://env/RONIN_REAL_PG_PASSWORD")),
            ("user", SecretRef("secret://env/RONIN_REAL_PG_USER")),
        ),
    )

    try:
        composition = build_local_composed_from_env()
        try:
            composition.start()
            address = composition.control_plane_server.server_address
            create_status, created = _request(
                address,
                "POST",
                "/v1/workspaces/workspace-pg-real/connections",
                source_connection.to_payload(),
            )
            discover_status, discovered = _request(
                address,
                "POST",
                "/v1/platform/connectors/discover?workspace_id=workspace-pg-real",
                {"connector_id": "postgresql", "connection_ref": "conn-pg-real", "page_size": 1},
            )
            invalid_limit_status, invalid_limit = _request(
                address,
                "POST",
                "/v1/platform/connectors/discover?workspace_id=workspace-pg-real",
                {"connector_id": "postgresql", "connection_ref": "conn-pg-real", "page_size": True},
            )
            preview_status, preview = _request(
                address,
                "POST",
                "/v1/platform/connectors/preview?workspace_id=workspace-pg-real",
                {
                    "id": "pg-preview",
                    "connector_id": "postgresql",
                    "connection_ref": "conn-pg-real",
                    "asset_ref": f"conn-pg-real::{source_schema}.{source_table}",
                    "destination_ref": "local/pg-preview",
                    "checkpoint_identity": "pg-preview-v1",
                    "mode": "snapshot",
                },
            )
        finally:
            composition.stop()

        reopened = build_local_composed_from_env()
        try:
            reopened.start()
            reopened_preview_status, reopened_preview = _request(
                reopened.control_plane_server.server_address,
                "POST",
                "/v1/platform/connectors/preview?workspace_id=workspace-pg-real",
                {
                    "id": "pg-preview-reopened",
                    "connector_id": "postgresql",
                    "connection_ref": "conn-pg-real",
                    "asset_ref": f"conn-pg-real::{source_schema}.{source_table}",
                    "destination_ref": "local/pg-preview-reopened",
                    "checkpoint_identity": "pg-preview-reopened-v1",
                    "mode": "snapshot",
                },
            )
        finally:
            reopened.stop()
    finally:
        with psycopg.connect(dsn) as database, database.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(source_schema))
            )

    assert create_status == 201
    assert created["id"] == "conn-pg-real"
    assert discover_status == 200
    assert discovered["count"] == 1
    assert discovered["has_more"] is False
    assert discovered["items"][0]["asset_ref"] == f"conn-pg-real::{source_schema}.{source_table}"
    assert invalid_limit_status == 400
    assert invalid_limit["error"]["code"] == "invalid_request"
    assert preview_status == 200
    assert preview["row_count"] == 3
    assert {row["id"] for row in preview["rows"]} == {1, 2, 3}
    assert preview["checkpoint"]["present"] is False
    assert reopened_preview_status == 200
    assert reopened_preview["row_count"] == 3
    assert {row["payload"] for row in reopened_preview["rows"]} == {"alpha", "bravo", "charlie"}
