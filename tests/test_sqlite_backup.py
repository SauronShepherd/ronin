import sqlite3

from studio_storage.backup import backup_sqlite, restore_sqlite


def test_sqlite_backup_and_restore_are_consistent(tmp_path) -> None:
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table VALUES ('ronin')")
        connection.commit()
    backup = backup_sqlite(source, tmp_path / "backup.sqlite")
    restored = restore_sqlite(backup, tmp_path / "restored.sqlite")
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM values_table").fetchone() == ("ronin",)
