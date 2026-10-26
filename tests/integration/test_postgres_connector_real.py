"""Reference-service qualification for the PostgreSQL connector.

The suite is skipped unless an explicit PostgreSQL DSN is provided.  This
keeps local unit runs honest while making the Docker qualification workflow
exercise the connector against its real PostgreSQL service.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from studio_connectors.postgres import PostgresConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SecretRef
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


def test_postgres_connector_real_watermark_pages_same_timestamp_without_loss() -> None:
    dsn = _dsn()
    if not dsn:
        pytest.skip("set RONIN_CONNECTOR_POSTGRES_DSN for real PostgreSQL qualification")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql

    parsed = urlsplit(dsn)
    connection = ConnectionDefinition(
        ConnectionId("real-postgres-incremental"),
        "PostgreSQL incremental qualification",
        "postgresql",
        options=(
            ("host", parsed.hostname or "localhost"),
            ("port", str(parsed.port or 5432)),
            ("database", (parsed.path or "/postgres").lstrip("/")),
            ("incremental_column", "observed_at"),
            ("tie_breaker_columns", "id"),
        ),
        secret_refs=(
            ("user", SecretRef("secret://env/PG_QUAL_USER")),
            ("password", SecretRef("secret://env/PG_QUAL_PASSWORD")),
        ),
    )
    resolver = EnvironmentSecretResolver(
        {"PG_QUAL_USER": parsed.username or "", "PG_QUAL_PASSWORD": parsed.password or ""}
    )
    table = f"ronin_incremental_{uuid4().hex}"
    with psycopg.connect(dsn) as database, database.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "CREATE TABLE {} "
                "(observed_at timestamptz NOT NULL, id bigint NOT NULL PRIMARY KEY, "
                "amount numeric(40,10) NOT NULL)"
            ).format(sql.Identifier(table))
        )
        cursor.execute(
            sql.SQL("INSERT INTO {} VALUES (%s, %s, %s), (%s, %s, %s), (%s, %s, %s)").format(
                sql.Identifier(table)
            ),
            (
                "2026-01-02T03:04:05+00:00",
                1,
                "12345678901234567890.1234567890",
                "2026-01-02T03:04:05+00:00",
                2,
                "2.25",
                "2026-01-02T03:04:05+00:00",
                3,
                "3.50",
            ),
        )
    try:
        asset = AssetHandle(connection.id, ("public",), table)
        connector = PostgresConnector()
        first = connector.read(connection, asset, resolver, limit=2)
        assert [row["id"] for row in first.rows] == [1, 2]
        assert first.has_more is True
        assert str(first.rows[0]["amount"]) == "12345678901234567890.1234567890"

        second = connector.read(connection, asset, resolver, limit=2, checkpoint=first.checkpoint)
        assert [row["id"] for row in second.rows] == [3]
        assert second.has_more is False

        repeated = connector.read(
            connection, asset, resolver, limit=2, checkpoint=second.checkpoint
        )
        assert repeated.rows == ()
        assert repeated.checkpoint == second.checkpoint

        with psycopg.connect(dsn) as database, database.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN added_after_checkpoint text").format(
                    sql.Identifier(table)
                )
            )
        with pytest.raises(ValueError, match="schema changed"):
            connector.read(connection, asset, resolver, checkpoint=second.checkpoint)
    finally:
        with psycopg.connect(dsn) as database, database.cursor() as cursor:
            cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table)))
