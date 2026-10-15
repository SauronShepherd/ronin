from __future__ import annotations

import sqlite3

import pytest
from studio_storage.sqlite import execute_migration_script


def test_migration_script_preserves_semicolons_in_literals_and_trigger_bodies() -> None:
    connection = sqlite3.connect(":memory:")
    execute_migration_script(
        connection,
        """
        CREATE TABLE values_table (value TEXT);
        INSERT INTO values_table VALUES ('literal;value');
        CREATE TRIGGER values_copy AFTER INSERT ON values_table
        BEGIN
            INSERT INTO values_table VALUES ('trigger;value');
        END;
        """,
    )
    connection.execute("INSERT INTO values_table VALUES ('source')")
    assert [row[0] for row in connection.execute("SELECT value FROM values_table")] == [
        "literal;value",
        "source",
        "trigger;value",
    ]


def test_migration_script_rejects_incomplete_sql() -> None:
    with pytest.raises(ValueError, match="incomplete"):
        execute_migration_script(sqlite3.connect(":memory:"), "CREATE TABLE broken (")
