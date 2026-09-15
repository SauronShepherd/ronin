"""Generic JDBC-profile connector over an injected DB-API bridge."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
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

from .contracts import ConnectorReadResult

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class JdbcDependencyError(RuntimeError):
    """Raised when no deployment-local JDBC bridge was supplied."""


class JdbcConnector:
    """Execute portable bounded reads through a deployment-provided DB-API bridge."""

    descriptor = ConnectorDescriptor(
        "jdbc", 1, ConnectorCapabilities(discover=True, read=True, incremental=True)
    )

    def __init__(
        self, *, connect: Callable[[ConnectionDefinition, SecretResolver], Any] | None = None
    ) -> None:
        self._connect = connect

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
        self, connection: ConnectionDefinition, secrets: SecretResolver
    ) -> tuple[DiscoveredAsset, ...]:
        options = self._options(connection)
        schema = options.get("schema", "public")
        self._identifier(schema, "schema")
        database = self._database(connection, secrets)
        try:
            cursor = database.cursor()
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = ? ORDER BY table_name",
                (schema,),
            )
            return tuple(
                DiscoveredAsset(AssetHandle(connection.id, (schema,), str(row[0])), "table", ())
                for row in cursor.fetchall()
            )
        finally:
            database.close()

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
            if checkpoint is not None and checkpoint.strategy == "watermark":
                if incremental_column is None:
                    raise ValueError("JDBC watermark checkpoints require incremental_column")
                predicate = f' WHERE "{incremental_column}" > ?'
                params = (checkpoint.value,)
            ordering = f' ORDER BY "{incremental_column}"' if incremental_column else ""
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


__all__ = ("JdbcConnector", "JdbcDependencyError")
