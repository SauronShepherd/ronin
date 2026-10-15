"""Reference-service qualification for the PostgreSQL connector.

The suite is skipped unless an explicit PostgreSQL DSN is provided.  This
keeps local unit runs honest while making the Docker qualification workflow
exercise the connector against its real PostgreSQL service.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest
from studio_connectors.postgres import PostgresConnector
from studio_core import ConnectionDefinition, ConnectionId, SecretRef
from studio_storage import EnvironmentSecretResolver


def _dsn() -> str:
    return os.environ.get("RONIN_CONNECTOR_POSTGRES_DSN", "")


def test_postgres_connector_real_schema_null_timezone_and_large_value() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set RONIN_CONNECTOR_POSTGRES_DSN for real PostgreSQL qualification")
    psycopg = pytest.importorskip("psycopg")
    parsed = urlsplit(dsn)
    user = parsed.username or ""
    password = parsed.password or ""
    database = (parsed.path or "/postgres").lstrip("/")
    host = parsed.hostname or "localhost"
    port = str(parsed.port or 5432)
    connection = ConnectionDefinition(
        ConnectionId("real-postgres"),
        "PostgreSQL qualification",
        "postgresql",
        options=(("host", host), ("port", port), ("database", database)),
        secret_refs=(
            ("user", SecretRef("secret://env/PG_QUAL_USER")),
            ("password", SecretRef("secret://env/PG_QUAL_PASSWORD")),
        ),
    )
    resolver = EnvironmentSecretResolver({"PG_QUAL_USER": user, "PG_QUAL_PASSWORD": password})
    table = "ronin_connector_qualification"
    with psycopg.connect(dsn) as database_connection, database_connection.cursor() as cursor:
        cursor.execute(f'DROP TABLE IF EXISTS "{table}"')
        cursor.execute(
            f'CREATE TABLE "{table}" ('
            "id integer, nullable text, observed_at timestamptz, large_value numeric(40,10))"
        )
        cursor.execute(  # noqa: S608 - table name is a local constant
            f'INSERT INTO "{table}" VALUES (%s, %s, %s, %s)',  # noqa: S608
            (1, None, "2026-01-02T03:04:05+00:00", "12345678901234567890.1234567890"),
        )
    connector = PostgresConnector()
    assets = connector.discover(connection, resolver)
    asset = next(item.handle for item in assets if item.handle.name == table)
    result = connector.read(connection, asset, resolver)
    assert result.rows[0]["nullable"] is None
    assert result.rows[0]["observed_at"].tzinfo is not None
    assert str(result.rows[0]["large_value"]) == "12345678901234567890.1234567890"
    assert result.checkpoint is not None
    unchanged = connector.read(connection, asset, resolver, checkpoint=result.checkpoint)
    assert unchanged.rows == ()
