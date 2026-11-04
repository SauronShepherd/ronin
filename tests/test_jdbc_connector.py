from __future__ import annotations

import hashlib
from datetime import UTC

import pytest
from studio_connectors import (
    JdbcBridgeProvenance,
    JdbcConnector,
    JdbcDependencyError,
    JdbcIncrementalCheckpointV2,
)
from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectionId,
    FieldSchema,
    SourceCheckpoint,
)
from studio_storage import EnvironmentSecretResolver


class _Cursor:
    description = (("id", "integer"),)

    def execute(self, query, params=()):
        self.query, self.params = query, params

    def fetchall(self):
        return [(1,)]


class _Db:
    def cursor(self):
        return _Cursor()

    def close(self):
        pass


def _connection() -> ConnectionDefinition:
    return ConnectionDefinition(
        ConnectionId("jdbc"), "JDBC", "jdbc", options=(("url", "jdbc:test"),)
    )


def test_jdbc_bridge_supports_discovery_and_snapshot_read() -> None:
    connector = JdbcConnector(connect=lambda *_args: _Db())
    connection = _connection()
    secrets = EnvironmentSecretResolver({})
    assets = connector.discover(connection, secrets)
    assert assets[0].handle.name == "1"
    result = connector.read(connection, AssetHandle(connection.id, ("public",), "events"), secrets)
    assert result.rows == ({"id": 1},)


def test_jdbc_without_bridge_fails_closed() -> None:
    with pytest.raises(JdbcDependencyError, match="bridge"):
        JdbcConnector().discover(_connection(), EnvironmentSecretResolver({}))


@pytest.mark.parametrize(
    "url",
    [
        "jdbc:postgresql://user:password@db.local/warehouse",
        "jdbc:mysql://db.local/warehouse?user=ronin&password=secret",
        "jdbc:mysql://db.local/warehouse?pwd=secret",
        "jdbc:sqlserver://db.local;user id=ronin;password=secret",
        "jdbc:h2:mem:test;USER=ronin;PASSWORD=secret",
        "jdbc:oracle:thin:ronin/secret@db.local:1521/warehouse",
        "postgresql://db.local/warehouse",
    ],
)
def test_jdbc_rejects_urls_with_embedded_credentials_or_non_jdbc_scheme(url: str) -> None:
    connection = ConnectionDefinition(ConnectionId("jdbc"), "JDBC", "jdbc", options=(("url", url),))
    with pytest.raises(ValueError, match="must use jdbc:.*must not embed credentials"):
        JdbcConnector().discover(connection, EnvironmentSecretResolver({}))


def test_jdbc_discovery_validates_and_applies_row_limit() -> None:
    connector = JdbcConnector(connect=lambda *_args: _Db())
    with pytest.raises(ValueError, match="discovery limit"):
        connector.discover(_connection(), EnvironmentSecretResolver({}), limit=0)
    connector.discover(_connection(), EnvironmentSecretResolver({}), limit=7)


def test_jdbc_discovery_page_is_bounded_and_returns_opaque_cursor() -> None:
    connector = JdbcConnector(connect=lambda *_args: _Db())
    page = connector.discover_page(_connection(), EnvironmentSecretResolver({}), page_size=1)
    assert len(page.items) == 1
    assert page.truncated is True
    assert page.next_cursor == "1"


def test_jdbc_incremental_watermark_is_ordered_and_advanced() -> None:
    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(("url", "jdbc:test"), ("incremental_column", "id")),
    )
    connector = JdbcConnector(connect=lambda *_args: _Db())
    result = connector.read(
        connection,
        AssetHandle(connection.id, ("public",), "events"),
        EnvironmentSecretResolver({}),
        checkpoint=SourceCheckpoint("watermark", "0"),
    )
    assert result.checkpoint == SourceCheckpoint("watermark", "1")


def test_jdbc_v2_checkpoint_round_trip_preserves_typed_cursor() -> None:
    checkpoint = JdbcIncrementalCheckpointV2(
        "asset-1", "updated_at", 1735689600, ("id",), (42,), "a" * 64, 3
    )
    assert JdbcIncrementalCheckpointV2.decode(checkpoint.encode()) == checkpoint
    assert checkpoint.predicate() == (
        '(("updated_at" > ?) OR ("updated_at" = ? AND "id" > ?))',
        (1735689600, 1735689600, 42),
    )
    assert checkpoint.order_by() == '"updated_at", "id"'


def test_jdbc_v2_checkpoint_round_trip_preserves_database_scalar_types() -> None:
    from datetime import date, datetime, time
    from decimal import Decimal

    checkpoint = JdbcIncrementalCheckpointV2(
        "asset-1",
        "updated_at",
        datetime(2026, 11, 3, 12, 30, tzinfo=UTC),
        ("id",),
        (Decimal("42.125"),),
        "b" * 64,
        4,
    )
    assert JdbcIncrementalCheckpointV2.decode(checkpoint.encode()) == checkpoint
    for value in (None, True, -10, 1.25, date(2026, 11, 3), time(12, 30), b"\x00\xff", "cursor"):
        encoded = JdbcIncrementalCheckpointV2._encode_scalar(value)
        assert JdbcIncrementalCheckpointV2._decode_scalar(encoded) == value


@pytest.mark.parametrize(
    ("incremental_value", "tie_breaker_values", "message"),
    [
        (None, (7,), "empty checkpoint must have null tie-breaker values"),
        (10, (None,), "checkpoint cursor values must not be null"),
    ],
)
def test_jdbc_v2_checkpoint_rejects_inconsistent_null_cursor(
    incremental_value: object,
    tie_breaker_values: tuple[object, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        JdbcIncrementalCheckpointV2(
            "public.events",
            "updated_at",
            incremental_value,
            ("id",),
            tie_breaker_values,
            "d" * 64,
            1,
        )


def test_jdbc_v2_checkpoint_decodes_legacy_untyped_payload() -> None:
    payload = (
        '{"source_asset_id":"public.events","incremental_column":"id",'
        '"incremental_value":7,"tie_breaker_columns":[],"tie_breaker_values":[],'
        '"schema_fingerprint":"' + ("c" * 64) + '","checkpoint_generation":2}'
    )
    checkpoint = JdbcIncrementalCheckpointV2.decode(payload)
    assert checkpoint.incremental_value == 7
    assert checkpoint.checkpoint_generation == 2


def test_jdbc_v2_read_binds_lexicographic_cursor() -> None:
    class Cursor(_Cursor):
        description = (("updated_at", "integer"), ("id", "integer"))

        def fetchall(self):
            return [(10, 8)]

    class Database(_Db):
        def cursor(self):
            return Cursor()

    schema_fingerprint = hashlib.sha256(
        repr(
            (
                FieldSchema("updated_at", "integer", True),
                FieldSchema("id", "integer", True),
            )
        ).encode()
    ).hexdigest()
    checkpoint = JdbcIncrementalCheckpointV2(
        "public.events", "updated_at", 10, ("id",), (7,), schema_fingerprint, 1
    )
    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(
            ("url", "jdbc:test"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
    )
    connector = JdbcConnector(connect=lambda *_args: Database())
    result = connector.read(
        connection,
        AssetHandle(connection.id, ("public",), "events"),
        EnvironmentSecretResolver({}),
        checkpoint=SourceCheckpoint("watermark", checkpoint.encode()),
    )
    assert result.rows == ({"updated_at": 10, "id": 8},)


def test_jdbc_empty_v2_checkpoint_reads_rows_added_after_empty_snapshot() -> None:
    class Database:
        rows = []
        last_query = ""

        def cursor(self):
            database = self

            class Cursor(_Cursor):
                description = (("updated_at", "integer"), ("id", "integer"))

                def execute(self, query, params=()):
                    database.last_query = query
                    self.query, self.params = query, params

                def fetchall(self):
                    return list(database.rows)

            return Cursor()

        def close(self):
            pass

    database = Database()
    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(
            ("url", "jdbc:test"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
    )
    asset = AssetHandle(connection.id, ("public",), "events")
    connector = JdbcConnector(connect=lambda *_args: database)
    secrets = EnvironmentSecretResolver({})

    empty = connector.read(connection, asset, secrets)
    database.rows = [(10, 1)]
    populated = connector.read(
        connection,
        asset,
        secrets,
        checkpoint=empty.checkpoint,
    )

    assert populated.rows == ({"updated_at": 10, "id": 1},)
    assert " WHERE " not in database.last_query


def test_jdbc_v2_checkpoint_rejects_schema_change() -> None:
    class ChangedCursor(_Cursor):
        description = (("updated_at", "varchar"), ("id", "integer"))

        def fetchall(self):
            return []

    class ChangedDatabase(_Db):
        def cursor(self):
            return ChangedCursor()

    old_fingerprint = hashlib.sha256(
        repr(
            (
                FieldSchema("updated_at", "integer", True),
                FieldSchema("id", "integer", True),
            )
        ).encode()
    ).hexdigest()
    checkpoint = JdbcIncrementalCheckpointV2(
        "public.events", "updated_at", 10, ("id",), (7,), old_fingerprint, 1
    )
    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(
            ("url", "jdbc:test"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
    )
    with pytest.raises(ValueError, match="schema fingerprint"):
        JdbcConnector(connect=lambda *_args: ChangedDatabase()).read(
            connection,
            AssetHandle(connection.id, ("public",), "events"),
            EnvironmentSecretResolver({}),
            checkpoint=SourceCheckpoint("watermark", checkpoint.encode()),
        )


def test_jdbc_v2_empty_source_does_not_create_empty_string_cursor() -> None:
    class EmptyCursor(_Cursor):
        description = (("updated_at", "timestamp"), ("id", "integer"))

        def fetchall(self):
            return []

    class EmptyDatabase(_Db):
        def cursor(self):
            return EmptyCursor()

    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(
            ("url", "jdbc:test"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
    )
    result = JdbcConnector(connect=lambda *_args: EmptyDatabase()).read(
        connection,
        AssetHandle(connection.id, ("public",), "events"),
        EnvironmentSecretResolver({}),
    )
    decoded = JdbcIncrementalCheckpointV2.decode(result.checkpoint.value)
    assert decoded.incremental_value is None
    assert decoded.incremental_value != ""


def test_jdbc_watermark_rejects_null_cursor_values_in_any_returned_row() -> None:
    class NullableCursor(_Cursor):
        description = (("updated_at", "integer"), ("id", "integer"))

        def fetchall(self):
            # The final row is valid; checking only the last row would miss the
            # earlier NULL and create a cursor that can skip or replay data.
            return [(None, 1), (10, 2)]

    class NullableDatabase(_Db):
        def cursor(self):
            return NullableCursor()

    connection = ConnectionDefinition(
        ConnectionId("jdbc"),
        "JDBC",
        "jdbc",
        options=(
            ("url", "jdbc:test"),
            ("incremental_column", "updated_at"),
            ("tie_breaker_columns", "id"),
        ),
    )
    with pytest.raises(ValueError, match="watermark and tie-breaker values must not be null"):
        JdbcConnector(connect=lambda *_args: NullableDatabase()).read(
            connection,
            AssetHandle(connection.id, ("public",), "events"),
            EnvironmentSecretResolver({}),
        )


def test_jdbc_bridge_provenance_is_explicit_and_fail_closed() -> None:
    connector = JdbcConnector(
        connect=lambda _connection, _secrets: object(),
        provenance=JdbcBridgeProvenance("bridge-1", "sqlite-jdbc", "3.45.0"),
    )
    assert connector.bridge_provenance().driver_name == "sqlite-jdbc"
    with pytest.raises(JdbcDependencyError):
        JdbcConnector(connect=lambda _connection, _secrets: object()).bridge_provenance()
