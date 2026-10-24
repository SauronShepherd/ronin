"""Optional psycopg-backed PostgreSQL discovery and bounded reads."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectorCapabilities,
    ConnectorDescriptor,
    DiscoveredAsset,
    FieldSchema,
    SourceCheckpoint,
)
from studio_core.canonical_json import decode, encode
from studio_storage.secrets import SecretResolver

from .contracts import ConnectorReadResult, DiscoveryPage


class PostgresConnectorDependencyError(RuntimeError):
    """Raised when psycopg is unavailable."""


def _psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise PostgresConnectorDependencyError(
            "PostgreSQL connector support requires the optional Ronin data-plane dependencies"
        ) from exc
    return psycopg, sql


def _connection_kwargs(
    definition: ConnectionDefinition,
    secrets: SecretResolver,
) -> dict[str, object]:
    options = dict(definition.options)
    refs = dict(definition.secret_refs)
    required = {"host", "database"}
    missing = sorted(required - set(options))
    if missing:
        raise ValueError(f"PostgreSQL connection missing options: {missing}")
    user_ref = refs.get("user")
    password_ref = refs.get("password")
    if user_ref is None or password_ref is None:
        raise ValueError("PostgreSQL connection requires user and password secret refs")
    try:
        port = int(options.get("port", "5432"))
        timeout = int(options.get("connect_timeout", "15"))
    except ValueError as exc:
        raise ValueError("PostgreSQL port/connect_timeout must be integers") from exc
    if port < 1 or port > 65535:
        raise ValueError("PostgreSQL port is outside the valid range")
    if timeout < 1 or timeout > 300:
        raise ValueError("PostgreSQL connect_timeout must be in [1, 300]")
    return {
        "host": options["host"],
        "port": port,
        "dbname": options["database"],
        "user": secrets.resolve(user_ref).reveal_text(),
        "password": secrets.resolve(password_ref).reveal_text(),
        "connect_timeout": timeout,
    }


def _field_type(type_code: object) -> str:
    name = getattr(type_code, "name", None)
    return str(name if name is not None else type_code)


class PostgresConnector:
    """Discover PostgreSQL tables and perform bounded snapshot reads."""

    descriptor = ConnectorDescriptor(
        "postgresql",
        1,
        ConnectorCapabilities(discover=True, read=True, schema=True, max_page_size=10_000),
    )

    def _validate(self, connection: ConnectionDefinition) -> dict[str, str]:
        if connection.connector_id != self.descriptor.connector_id:
            raise ValueError("connection does not target the PostgreSQL connector")
        return dict(connection.options)

    def discover(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
    ) -> tuple[DiscoveredAsset, ...]:
        options = self._validate(connection)
        psycopg, _ = _psycopg()
        schema_filter = options.get("schema")
        query = (
            "SELECT table_schema, table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
        )
        params: tuple[object, ...] = ()
        if schema_filter is not None:
            query += " AND table_schema = %s"
            params = (schema_filter,)
        query += " ORDER BY table_schema, table_name, ordinal_position"

        grouped: dict[tuple[str, str], list[FieldSchema]] = {}
        with (
            psycopg.connect(**_connection_kwargs(connection, secrets)) as database,
            database.cursor() as cursor,
        ):
            cursor.execute(query, params)
            for schema, table, column, data_type, nullable in cursor.fetchall():
                grouped.setdefault((str(schema), str(table)), []).append(
                    FieldSchema(str(column), str(data_type), str(nullable) == "YES")
                )
        return tuple(
            DiscoveredAsset(
                AssetHandle(connection.id, (schema,), table),
                "table",
                tuple(fields),
            )
            for (schema, table), fields in sorted(grouped.items())
        )

    @staticmethod
    def _encode_discovery_cursor(schema: str, table: str) -> str:
        return base64.urlsafe_b64encode(encode([schema, table])).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_discovery_cursor(cursor: str | None) -> tuple[str, str] | None:
        if cursor is None:
            return None
        if not cursor or len(cursor) > 4096:
            raise ValueError("PostgreSQL discovery cursor is invalid")
        try:
            padding = "=" * (-len(cursor) % 4)
            raw = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
            payload = decode(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("PostgreSQL discovery cursor is invalid") from exc
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError("PostgreSQL discovery cursor is invalid")
        schema, table = payload
        if not isinstance(schema, str) or not schema or not isinstance(table, str) or not table:
            raise ValueError("PostgreSQL discovery cursor is invalid")
        return schema, table

    def discover_page(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
        *,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> DiscoveryPage[DiscoveredAsset]:
        """Read bounded table metadata using a stable schema/table keyset cursor."""
        if page_size < 1 or page_size > 10_000:
            raise ValueError("PostgreSQL discovery page_size must be between 1 and 10000")
        options = self._validate(connection)
        schema_filter = options.get("schema")
        after = self._decode_discovery_cursor(cursor)
        psycopg, _ = _psycopg()
        with (
            psycopg.connect(**_connection_kwargs(connection, secrets)) as database,
            database.cursor() as cursor_handle,
        ):
            table_query = (
                "SELECT DISTINCT table_schema, table_name "
                "FROM information_schema.columns "
                "WHERE table_schema NOT IN ('pg_catalog', 'information_schema')"
            )
            table_params: list[object] = []
            if schema_filter is not None:
                table_query += " AND table_schema = %s"
                table_params.append(schema_filter)
            if after is not None:
                table_query += " AND (table_schema, table_name) > (%s, %s)"
                table_params.extend(after)
            table_query += " ORDER BY table_schema, table_name LIMIT %s"
            table_params.append(page_size + 1)
            cursor_handle.execute(table_query, tuple(table_params))
            tables = [(str(row[0]), str(row[1])) for row in cursor_handle.fetchall()]

            truncated = len(tables) > page_size
            selected = tables[:page_size]
            field_rows: list[tuple[object, ...]] = []
            if selected:
                placeholders = ", ".join("(%s, %s)" for _ in selected)
                field_query = (
                    "SELECT table_schema, table_name, column_name, data_type, is_nullable "  # noqa: S608
                    "FROM information_schema.columns "
                    f"WHERE (table_schema, table_name) IN ({placeholders}) "
                    "ORDER BY table_schema, table_name, ordinal_position"
                )  # noqa: S608
                field_params = tuple(value for pair in selected for value in pair)
                cursor_handle.execute(field_query, field_params)
                field_rows = cursor_handle.fetchall()

        grouped: dict[tuple[str, str], list[FieldSchema]] = {key: [] for key in selected}
        for schema, table, column, data_type, nullable in field_rows:
            grouped[(str(schema), str(table))].append(
                FieldSchema(str(column), str(data_type), str(nullable) == "YES")
            )
        assets = tuple(
            DiscoveredAsset(AssetHandle(connection.id, (schema,), table), "table", tuple(fields))
            for (schema, table), fields in grouped.items()
        )
        next_cursor = self._encode_discovery_cursor(*selected[-1]) if truncated else None
        return DiscoveryPage(assets, next_cursor, truncated)

    def read(
        self,
        connection: ConnectionDefinition,
        asset: AssetHandle,
        secrets: SecretResolver,
        *,
        limit: int = 10_000,
        checkpoint: SourceCheckpoint | None = None,
    ) -> ConnectorReadResult:
        if checkpoint is not None and checkpoint.strategy != "snapshot":
            raise ValueError("PostgreSQL connector only supports snapshot checkpoints")
        if limit < 1 or limit > 100_000:
            raise ValueError("PostgreSQL read limit must be between 1 and 100000")
        if asset.connection_id != connection.id:
            raise ValueError("PostgreSQL asset handle belongs to a different connection")
        self._validate(connection)
        if len(asset.namespace) != 1:
            raise ValueError("PostgreSQL table handles require exactly one schema namespace")

        psycopg, sql = _psycopg()
        query = sql.SQL("SELECT * FROM {}.{} LIMIT %s").format(
            sql.Identifier(asset.namespace[0]),
            sql.Identifier(asset.name),
        )
        with (
            psycopg.connect(**_connection_kwargs(connection, secrets)) as database,
            database.cursor() as cursor,
        ):
            cursor.execute(query, (limit,))
            description = cursor.description or ()
            fields = tuple(
                FieldSchema(str(column.name), _field_type(column.type_code), True)
                for column in description
            )
            rows = tuple(
                {field.name: value for field, value in zip(fields, values, strict=True)}
                for values in cursor.fetchall()
            )
        checkpoint_payload = repr((asset.qualified_name, fields, rows)).encode("utf-8")
        checkpoint_value = hashlib.sha256(checkpoint_payload).hexdigest()
        if checkpoint is not None and checkpoint.value == checkpoint_value:
            rows = ()
        return ConnectorReadResult(
            fields,
            rows,
            SourceCheckpoint("snapshot", checkpoint_value),
        )


__all__ = ("PostgresConnector", "PostgresConnectorDependencyError")
