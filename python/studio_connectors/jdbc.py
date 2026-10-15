"""Generic JDBC-profile connector over an injected DB-API bridge."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
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
from studio_storage.secrets import SecretResolver

from .contracts import ConnectorReadResult, DiscoveryPage

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class JdbcDependencyError(RuntimeError):
    """Raised when no deployment-local JDBC bridge was supplied."""


@dataclass(frozen=True, slots=True)
class JdbcBridgeProvenance:
    """Identity of the deployment-local bridge and its selected driver."""

    bridge_version: str
    driver_name: str
    driver_version: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.bridge_version, self.driver_name, self.driver_version)
        ):
            raise ValueError("JDBC bridge provenance fields must be non-empty")


@dataclass(frozen=True, slots=True)
class JdbcIncrementalCheckpointV2:
    """Typed, deterministic JDBC cursor including a composite tie-breaker."""

    source_asset_id: str
    incremental_column: str
    incremental_value: object
    tie_breaker_columns: tuple[str, ...]
    tie_breaker_values: tuple[object, ...]
    schema_fingerprint: str
    checkpoint_generation: int

    def __post_init__(self) -> None:
        if not self.source_asset_id or not self.incremental_column:
            raise ValueError("JDBC checkpoint identity is required")
        if len(self.tie_breaker_columns) != len(self.tie_breaker_values):
            raise ValueError("JDBC checkpoint tie-breaker columns and values must match")
        if self.checkpoint_generation < 0:
            raise ValueError("JDBC checkpoint generation must be non-negative")

    def encode(self) -> str:
        return json.dumps(
            {
                "source_asset_id": self.source_asset_id,
                "incremental_column": self.incremental_column,
                "incremental_value": self.incremental_value,
                "tie_breaker_columns": self.tie_breaker_columns,
                "tie_breaker_values": self.tie_breaker_values,
                "schema_fingerprint": self.schema_fingerprint,
                "checkpoint_generation": self.checkpoint_generation,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def decode(cls, value: str) -> JdbcIncrementalCheckpointV2:
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JDBC V2 checkpoint") from exc
        if not isinstance(payload, dict):
            raise ValueError("invalid JDBC V2 checkpoint")
        try:
            return cls(
                str(payload["source_asset_id"]),
                str(payload["incremental_column"]),
                payload["incremental_value"],
                tuple(payload["tie_breaker_columns"]),
                tuple(payload["tie_breaker_values"]),
                str(payload["schema_fingerprint"]),
                int(payload["checkpoint_generation"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid JDBC V2 checkpoint") from exc

    def predicate(self) -> tuple[str, tuple[object, ...]]:
        """Return a bound lexicographic continuation predicate and its parameters."""
        columns = (self.incremental_column, *self.tie_breaker_columns)
        values = (self.incremental_value, *self.tie_breaker_values)
        predicates: list[str] = []
        parameters: list[object] = []
        for index, column in enumerate(columns):
            prefix = " AND ".join(f'"{item}" = ?' for item in columns[:index])
            predicates.append(f'({prefix + " AND " if prefix else ""}"{column}" > ?)')
            parameters.extend(values[:index])
            parameters.append(values[index])
        return "(" + " OR ".join(predicates) + ")", tuple(parameters)

    def order_by(self) -> str:
        """Return deterministic watermark-plus-tie-breaker ordering."""
        return ", ".join(
            f'"{column}"'
            for column in (
                self.incremental_column,
                *self.tie_breaker_columns,
            )
        )


class JdbcConnector:
    """Execute portable bounded reads through a deployment-provided DB-API bridge."""

    descriptor = ConnectorDescriptor(
        "jdbc", 1, ConnectorCapabilities(discover=True, read=True, incremental=True)
    )

    def __init__(
        self,
        *,
        connect: Callable[[ConnectionDefinition, SecretResolver], Any] | None = None,
        provenance: JdbcBridgeProvenance | None = None,
    ) -> None:
        self._connect = connect
        self._provenance = provenance

    def bridge_provenance(self) -> JdbcBridgeProvenance:
        """Return explicit driver provenance; never infer it from a URL."""
        if self._connect is None or self._provenance is None:
            raise JdbcDependencyError("JDBC bridge provenance is not configured")
        return self._provenance

    def _options(self, connection: ConnectionDefinition) -> dict[str, str]:
        if connection.connector_id != self.descriptor.connector_id:
            raise ValueError("connection does not target the JDBC connector")
        options = dict(connection.options)
        if not options.get("url", "").strip():
            raise ValueError("JDBC connection requires a non-empty url")
        return options

    def _database(self, connection: ConnectionDefinition, secrets: SecretResolver) -> Any:
        self._options(connection)
        if self._connect is None:
            raise JdbcDependencyError("JDBC support requires an injected deployment-local bridge")
        return self._connect(connection, secrets)

    @staticmethod
    def _identifier(value: str, name: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError(f"JDBC {name} is not a safe identifier")
        return value

    def discover(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
        *,
        limit: int = 10_000,
    ) -> tuple[DiscoveredAsset, ...]:
        if limit < 1 or limit > 100_000:
            raise ValueError("JDBC discovery limit must be between 1 and 100000")
        options = self._options(connection)
        schema = options.get("schema", "public")
        self._identifier(schema, "schema")
        database = self._database(connection, secrets)
        try:
            cursor = database.cursor()
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = ? ORDER BY table_name LIMIT ?",
                (schema, limit),
            )
            return tuple(
                DiscoveredAsset(AssetHandle(connection.id, (schema,), str(row[0])), "table", ())
                for row in cursor.fetchall()
            )
        finally:
            database.close()

    def discover_page(
        self,
        connection: ConnectionDefinition,
        secrets: SecretResolver,
        *,
        cursor: str | None = None,
        page_size: int = 1000,
    ) -> DiscoveryPage[DiscoveredAsset]:
        """Discover one bounded JDBC page using a provider-neutral opaque offset cursor."""
        if page_size < 1 or page_size > 10_000:
            raise ValueError("JDBC discovery page_size must be between 1 and 10000")
        offset = 0
        if cursor is not None:
            try:
                offset = int(cursor)
            except ValueError as exc:
                raise ValueError("JDBC discovery cursor is invalid") from exc
            if offset < 0:
                raise ValueError("JDBC discovery cursor is invalid")
        options = self._options(connection)
        schema = self._identifier(options.get("schema", "public"), "schema")
        database = self._database(connection, secrets)
        try:
            cursor_handle = database.cursor()
            cursor_handle.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = ? ORDER BY table_name LIMIT ? OFFSET ?",
                (schema, page_size, offset),
            )
            rows = tuple(cursor_handle.fetchall())
        finally:
            database.close()
        items = tuple(
            DiscoveredAsset(AssetHandle(connection.id, (schema,), str(row[0])), "table", ())
            for row in rows
        )
        truncated = len(items) == page_size
        return DiscoveryPage(items, str(offset + page_size) if truncated else None, truncated)

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
            raise ValueError("JDBC connector only supports snapshot or watermark checkpoints")
        if limit < 1 or limit > 100_000:
            raise ValueError("JDBC read limit must be between 1 and 100000")
        if asset.connection_id != connection.id or len(asset.namespace) != 1:
            raise ValueError("JDBC asset handle is invalid for the connection")
        schema = self._identifier(asset.namespace[0], "schema")
        table = self._identifier(asset.name, "table")
        options = self._options(connection)
        incremental_column = options.get("incremental_column")
        if incremental_column is not None:
            incremental_column = self._identifier(incremental_column, "incremental_column")
        tie_breaker_columns = tuple(
            self._identifier(item.strip(), "tie_breaker_column")
            for item in options.get("tie_breaker_columns", "").split(",")
            if item.strip()
        )
        checkpoint_v2 = (
            JdbcIncrementalCheckpointV2.decode(checkpoint.value)
            if checkpoint is not None
            and checkpoint.strategy == "watermark"
            and checkpoint.value.startswith("{")
            else None
        )
        if checkpoint_v2 is not None:
            if checkpoint_v2.source_asset_id != asset.qualified_name:
                raise ValueError("JDBC checkpoint belongs to a different source asset")
            if checkpoint_v2.incremental_column != incremental_column:
                raise ValueError("JDBC checkpoint column does not match connection")
            if checkpoint_v2.tie_breaker_columns != tie_breaker_columns:
                raise ValueError("JDBC checkpoint tie-breakers do not match connection")
        if (
            checkpoint is not None
            and checkpoint.strategy == "watermark"
            and incremental_column is None
        ):
            raise ValueError("JDBC watermark checkpoints require incremental_column")
        database = self._database(connection, secrets)
        try:
            cursor = database.cursor()
            predicate = ""
            params: tuple[object, ...] = ()
            if checkpoint_v2 is not None:
                predicate, params = checkpoint_v2.predicate()
                predicate = f" WHERE {predicate}"
            elif checkpoint is not None and checkpoint.strategy == "watermark":
                if incremental_column is None:
                    raise ValueError("JDBC watermark checkpoints require incremental_column")
                predicate = f' WHERE "{incremental_column}" > ?'
                params = (checkpoint.value,)
            ordering_columns = (incremental_column, *tie_breaker_columns)
            ordering = (
                " ORDER BY " + ", ".join(f'"{column}"' for column in ordering_columns)
                if incremental_column
                else ""
            )
            cursor.execute(
                f'SELECT * FROM "{schema}"."{table}"{predicate}{ordering} LIMIT ?',  # noqa: S608 - identifiers are validated by _identifier and values are bound
                (*params, limit),
            )
            description = cursor.description or ()
            fields = tuple(
                FieldSchema(str(column[0]), str(column[1] if len(column) > 1 else "unknown"), True)
                for column in description
            )
            rows = tuple(
                {field.name: value for field, value in zip(fields, row, strict=True)}
                for row in cursor.fetchall()
            )
        finally:
            database.close()
        if incremental_column is not None:
            names = [field.name for field in fields]
            if incremental_column not in names:
                raise ValueError("JDBC incremental_column is not present in the result")
            if checkpoint_v2 is not None or tie_breaker_columns:
                if not rows:
                    next_checkpoint = checkpoint or SourceCheckpoint(
                        "watermark",
                        JdbcIncrementalCheckpointV2(
                            asset.qualified_name,
                            incremental_column,
                            None,
                            tie_breaker_columns,
                            tuple(None for _ in tie_breaker_columns),
                            hashlib.sha256(repr(fields).encode()).hexdigest(),
                            0,
                        ).encode(),
                    )
                else:
                    last = rows[-1]
                    next_checkpoint = SourceCheckpoint(
                        "watermark",
                        JdbcIncrementalCheckpointV2(
                            asset.qualified_name,
                            incremental_column,
                            last[incremental_column],
                            tie_breaker_columns,
                            tuple(last[column] for column in tie_breaker_columns),
                            hashlib.sha256(repr(fields).encode()).hexdigest(),
                            (checkpoint_v2.checkpoint_generation + 1) if checkpoint_v2 else 1,
                        ).encode(),
                    )
            else:
                watermark = (
                    str(rows[-1][incremental_column])
                    if rows
                    else (checkpoint.value if checkpoint is not None else "")
                )
                next_checkpoint = SourceCheckpoint("watermark", watermark)
        else:
            next_checkpoint = SourceCheckpoint(
                "snapshot",
                hashlib.sha256(repr((asset.qualified_name, fields, rows)).encode()).hexdigest(),
            )
        if (
            checkpoint is not None
            and checkpoint.strategy == "snapshot"
            and checkpoint.value == next_checkpoint.value
        ):
            rows = ()
        return ConnectorReadResult(fields, rows, next_checkpoint)


__all__ = (
    "JdbcBridgeProvenance",
    "JdbcConnector",
    "JdbcDependencyError",
    "JdbcIncrementalCheckpointV2",
)
