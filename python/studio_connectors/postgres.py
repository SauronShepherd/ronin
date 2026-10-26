"""Optional psycopg-backed PostgreSQL discovery and bounded reads."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast

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

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WATERMARK_SCHEMA = "ronin.postgresql-watermark/v1"
_MAX_TIE_BREAKERS = 8


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


def _encode_watermark_value(value: object) -> dict[str, str]:
    """Encode supported PostgreSQL scalar values without losing numeric/time types."""
    if value is None:
        raise ValueError("PostgreSQL watermark and tie-breaker values must not be null")
    if isinstance(value, bool):
        return {"type": "bool", "value": "true" if value else "false"}
    if isinstance(value, int):
        return {"type": "int", "value": str(value)}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("PostgreSQL watermark values must be finite")
        return {"type": "decimal", "value": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("PostgreSQL watermark values must be finite")
        return {"type": "float", "value": value.hex()}
    if isinstance(value, dt.datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, dt.date):
        return {"type": "date", "value": value.isoformat()}
    if isinstance(value, dt.time):
        return {"type": "time", "value": value.isoformat()}
    if isinstance(value, uuid.UUID):
        return {"type": "uuid", "value": str(value)}
    if isinstance(value, bytes):
        return {"type": "bytes", "value": base64.urlsafe_b64encode(value).decode("ascii")}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    raise ValueError(f"unsupported PostgreSQL watermark scalar type: {type(value).__name__}")


def _decode_watermark_value(value: object) -> object:
    if not isinstance(value, dict) or set(value) != {"type", "value"}:
        raise ValueError("PostgreSQL watermark checkpoint value is invalid")
    kind, raw = value["type"], value["value"]
    if not isinstance(kind, str) or not isinstance(raw, str):
        raise ValueError("PostgreSQL watermark checkpoint value is invalid")
    try:
        if kind == "bool" and raw in {"true", "false"}:
            return raw == "true"
        if kind == "int":
            return int(raw)
        if kind == "decimal":
            decoded = Decimal(raw)
            if decoded.is_finite():
                return decoded
        if kind == "float":
            decoded_float = float.fromhex(raw)
            if math.isfinite(decoded_float):
                return decoded_float
        if kind == "datetime":
            return dt.datetime.fromisoformat(raw)
        if kind == "date":
            return dt.date.fromisoformat(raw)
        if kind == "time":
            return dt.time.fromisoformat(raw)
        if kind == "uuid":
            return uuid.UUID(raw)
        if kind == "bytes":
            return base64.b64decode(raw, altchars=b"-_", validate=True)
        if kind == "str":
            return raw
    except (ValueError, InvalidOperation, OverflowError) as exc:
        raise ValueError("PostgreSQL watermark checkpoint value is invalid") from exc
    raise ValueError("PostgreSQL watermark checkpoint value is invalid")


@dataclass(frozen=True, slots=True)
class PostgresWatermarkCheckpoint:
    """Typed, source-bound lexicographic cursor for bounded PostgreSQL reads."""

    connection_id: str
    namespace: tuple[str, ...]
    table: str
    incremental_column: str
    tie_breaker_columns: tuple[str, ...]
    values: tuple[object, ...]
    schema_fingerprint: str
    initialized: bool

    def __post_init__(self) -> None:
        if not self.connection_id or not self.namespace or not self.table:
            raise ValueError("PostgreSQL watermark checkpoint source identity is required")
        if not self.incremental_column or not self.tie_breaker_columns:
            raise ValueError("PostgreSQL watermark checkpoint columns are required")
        if not _IDENTIFIER.fullmatch(self.incremental_column) or any(
            not _IDENTIFIER.fullmatch(column) for column in self.tie_breaker_columns
        ):
            raise ValueError("PostgreSQL watermark checkpoint columns must be simple identifiers")
        if not re.fullmatch(r"[0-9a-f]{64}", self.schema_fingerprint):
            raise ValueError("PostgreSQL watermark checkpoint schema fingerprint is invalid")
        if len(self.tie_breaker_columns) > _MAX_TIE_BREAKERS:
            raise ValueError("PostgreSQL watermark checkpoint has too many tie-breakers")
        if len({self.incremental_column, *self.tie_breaker_columns}) != (
            len(self.tie_breaker_columns) + 1
        ):
            raise ValueError("PostgreSQL watermark checkpoint columns must be unique")
        if not isinstance(self.initialized, bool):
            raise ValueError("PostgreSQL watermark checkpoint initialized must be boolean")
        if self.initialized and len(self.values) != len(self.tie_breaker_columns) + 1:
            raise ValueError("PostgreSQL watermark checkpoint values do not match columns")
        if not self.initialized and self.values:
            raise ValueError("uninitialized PostgreSQL watermark checkpoint must have no values")

    def encode(self) -> str:
        payload = {
            "schema": _WATERMARK_SCHEMA,
            "connection_id": self.connection_id,
            "namespace": list(self.namespace),
            "table": self.table,
            "incremental_column": self.incremental_column,
            "tie_breaker_columns": list(self.tie_breaker_columns),
            "values": [_encode_watermark_value(value) for value in self.values],
            "schema_fingerprint": self.schema_fingerprint,
            "initialized": self.initialized,
        }
        encoded = encode(payload).decode("utf-8")
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise ValueError("PostgreSQL watermark checkpoint exceeds 64 KiB")
        return encoded

    @classmethod
    def decode(cls, value: str) -> PostgresWatermarkCheckpoint:
        if not isinstance(value, str) or len(value.encode("utf-8")) > 64 * 1024:
            raise ValueError("PostgreSQL watermark checkpoint is invalid")
        try:
            payload = decode(value)
            expected = {
                "schema",
                "connection_id",
                "namespace",
                "table",
                "incremental_column",
                "tie_breaker_columns",
                "values",
                "schema_fingerprint",
                "initialized",
            }
            if not isinstance(payload, dict) or set(payload) != expected:
                raise ValueError("invalid shape")
            if payload["schema"] != _WATERMARK_SCHEMA:
                raise ValueError("unknown schema")
            namespace = payload["namespace"]
            tie_breakers = payload["tie_breaker_columns"]
            values = payload["values"]
            if (
                not isinstance(namespace, list)
                or not all(isinstance(part, str) and part for part in namespace)
                or not isinstance(tie_breakers, list)
                or not all(isinstance(column, str) for column in tie_breakers)
                or not isinstance(values, list)
                or not isinstance(payload["connection_id"], str)
                or not isinstance(payload["table"], str)
                or not isinstance(payload["incremental_column"], str)
                or not isinstance(payload["schema_fingerprint"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", payload["schema_fingerprint"])
                or not isinstance(payload["initialized"], bool)
            ):
                raise ValueError("invalid fields")
            return cls(
                payload["connection_id"],
                tuple(cast(list[str], namespace)),
                payload["table"],
                payload["incremental_column"],
                tuple(cast(list[str], tie_breakers)),
                tuple(_decode_watermark_value(item) for item in values),
                payload["schema_fingerprint"],
                cast(bool, payload["initialized"]),
            )
        except (TypeError, ValueError, UnicodeDecodeError) as exc:
            raise ValueError("PostgreSQL watermark checkpoint is invalid") from exc


def _watermark_configuration(
    options: dict[str, str],
) -> tuple[str, tuple[str, ...]] | None:
    raw_column = options.get("incremental_column")
    raw_tie_breakers = options.get("tie_breaker_columns")
    if raw_column is None and raw_tie_breakers is None:
        return None
    if raw_column is None or not raw_column.strip() or raw_column != raw_column.strip():
        raise ValueError("PostgreSQL incremental_column must be non-empty trimmed text")
    if not _IDENTIFIER.fullmatch(raw_column):
        raise ValueError("PostgreSQL incremental_column must be a simple SQL identifier")
    if raw_tie_breakers is None or not raw_tie_breakers:
        raise ValueError("PostgreSQL incremental reads require tie_breaker_columns")
    tie_breakers = tuple(raw_tie_breakers.split(","))
    if (
        len(tie_breakers) > _MAX_TIE_BREAKERS
        or any(
            not item or item != item.strip() or not _IDENTIFIER.fullmatch(item)
            for item in tie_breakers
        )
        or len(set(tie_breakers)) != len(tie_breakers)
        or raw_column in tie_breakers
    ):
        raise ValueError("PostgreSQL tie_breaker_columns must be unique simple SQL identifiers")
    return raw_column, tie_breakers


def _schema_fingerprint(fields: tuple[FieldSchema, ...]) -> str:
    return hashlib.sha256(
        encode([[field.name, field.data_type, field.nullable] for field in fields])
    ).hexdigest()


def _require_unique_tie_breaker(cursor: Any, asset: AssetHandle, columns: tuple[str, ...]) -> None:
    cursor.execute(
        "SELECT array_agg(attribute.attname ORDER BY key.ordinality) "
        "FROM pg_catalog.pg_index AS index_metadata "
        "JOIN pg_catalog.pg_class AS relation ON relation.oid = index_metadata.indrelid "
        "JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
        "CROSS JOIN LATERAL unnest(index_metadata.indkey) WITH ORDINALITY "
        "AS key(attnum, ordinality) "
        "JOIN pg_catalog.pg_attribute AS attribute "
        "ON attribute.attrelid = relation.oid AND attribute.attnum = key.attnum "
        "WHERE namespace.nspname = %s AND relation.relname = %s "
        "AND index_metadata.indisunique AND index_metadata.indisvalid "
        "AND index_metadata.indisready AND index_metadata.indpred IS NULL "
        "AND index_metadata.indexprs IS NULL "
        "AND key.ordinality <= index_metadata.indnkeyatts "
        "GROUP BY index_metadata.indexrelid",
        (asset.namespace[0], asset.name),
    )
    unique_keys = cursor.fetchall()
    configured = set(columns)
    if not any(
        isinstance(row, (tuple, list))
        and len(row) == 1
        and isinstance(row[0], (tuple, list))
        and set(row[0]).issubset(configured)
        for row in unique_keys
    ):
        raise ValueError(
            "PostgreSQL tie_breaker_columns must contain a non-partial unique key "
            "for the source table"
        )


class PostgresConnector:
    """Discover PostgreSQL tables and perform bounded snapshot/watermark reads."""

    descriptor = ConnectorDescriptor(
        "postgresql",
        1,
        ConnectorCapabilities(
            discover=True,
            read=True,
            incremental=True,
            schema=True,
            watermark_types=(
                "integer",
                "numeric",
                "floating-point",
                "date/time",
                "text",
                "uuid",
            ),
            max_page_size=10_000,
            max_batch_size=100_000,
        ),
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
        if checkpoint is not None and checkpoint.strategy not in {"snapshot", "watermark"}:
            raise ValueError("PostgreSQL connector only supports snapshot or watermark checkpoints")
        if limit < 1 or limit > 100_000:
            raise ValueError("PostgreSQL read limit must be between 1 and 100000")
        if asset.connection_id != connection.id:
            raise ValueError("PostgreSQL asset handle belongs to a different connection")
        options = self._validate(connection)
        if len(asset.namespace) != 1:
            raise ValueError("PostgreSQL table handles require exactly one schema namespace")

        watermark = _watermark_configuration(options)
        if checkpoint is not None and checkpoint.strategy == "watermark" and watermark is None:
            raise ValueError(
                "PostgreSQL watermark checkpoint requires incremental connection options"
            )

        psycopg, sql = _psycopg()
        base_query = sql.SQL("SELECT * FROM {}.{}").format(
            sql.Identifier(asset.namespace[0]),
            sql.Identifier(asset.name),
        )
        parameters: list[object] = []
        watermark_state: PostgresWatermarkCheckpoint | None = None
        if watermark is not None:
            incremental_column, tie_breaker_columns = watermark
            if checkpoint is not None and checkpoint.strategy == "watermark":
                watermark_state = PostgresWatermarkCheckpoint.decode(checkpoint.value)
                identity = (
                    str(asset.connection_id),
                    asset.namespace,
                    asset.name,
                    incremental_column,
                    tie_breaker_columns,
                )
                observed_identity = (
                    watermark_state.connection_id,
                    watermark_state.namespace,
                    watermark_state.table,
                    watermark_state.incremental_column,
                    watermark_state.tie_breaker_columns,
                )
                if identity != observed_identity:
                    raise ValueError("PostgreSQL watermark checkpoint belongs to another source")

            if watermark_state is not None and watermark_state.initialized:
                columns = (incremental_column, *tie_breaker_columns)
                terms: list[object] = []
                for index, column in enumerate(columns):
                    comparisons = [
                        sql.SQL("{} = %s").format(sql.Identifier(previous))
                        for previous in columns[:index]
                    ]
                    comparisons.append(sql.SQL("{} > %s").format(sql.Identifier(column)))
                    terms.append(sql.SQL("({})").format(sql.SQL(" AND ").join(comparisons)))
                    parameters.extend(watermark_state.values[:index])
                    parameters.append(watermark_state.values[index])
                predicate = sql.SQL(" OR ").join(terms)
                base_query += sql.SQL(" WHERE {} ").format(predicate)
            order_columns = (incremental_column, *tie_breaker_columns)
            order_by = sql.SQL(", ").join(sql.Identifier(column) for column in order_columns)
            base_query += sql.SQL(" ORDER BY {} LIMIT %s").format(order_by)
            parameters.append(limit + 1)
        else:
            base_query += sql.SQL(" LIMIT %s")
            parameters.append(limit)

        with (
            psycopg.connect(**_connection_kwargs(connection, secrets)) as database,
            database.cursor() as cursor,
        ):
            if watermark is not None:
                _require_unique_tie_breaker(cursor, asset, watermark[1])
            cursor.execute(base_query, tuple(parameters))
            description = cursor.description or ()
            fields = tuple(
                FieldSchema(str(column.name), _field_type(column.type_code), True)
                for column in description
            )
            fetched_rows = tuple(
                {field.name: value for field, value in zip(fields, values, strict=True)}
                for values in cursor.fetchall()
            )

        if watermark is not None:
            incremental_column, tie_breaker_columns = watermark
            column_names = {field.name for field in fields}
            if any(
                column not in column_names for column in (incremental_column, *tie_breaker_columns)
            ):
                raise ValueError("PostgreSQL watermark columns are not present in the source table")
            fingerprint = _schema_fingerprint(fields)
            if watermark_state is not None and watermark_state.schema_fingerprint != fingerprint:
                raise ValueError(
                    "PostgreSQL source schema changed since the checkpoint was created"
                )
            has_more = len(fetched_rows) > limit
            rows = fetched_rows[:limit]
            if rows:
                last = rows[-1]
                values = tuple(
                    last[column] for column in (incremental_column, *tie_breaker_columns)
                )
                next_state = PostgresWatermarkCheckpoint(
                    str(asset.connection_id),
                    asset.namespace,
                    asset.name,
                    incremental_column,
                    tie_breaker_columns,
                    values,
                    fingerprint,
                    True,
                )
                # Validate serialization before handing a checkpoint to the durable sync layer.
                next_state.encode()
            elif watermark_state is not None:
                next_state = watermark_state
                has_more = False
            else:
                next_state = PostgresWatermarkCheckpoint(
                    str(asset.connection_id),
                    asset.namespace,
                    asset.name,
                    incremental_column,
                    tie_breaker_columns,
                    (),
                    fingerprint,
                    False,
                )
                has_more = False
            return ConnectorReadResult(
                fields,
                rows,
                SourceCheckpoint("watermark", next_state.encode()),
                has_more,
            )

        rows = fetched_rows
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
