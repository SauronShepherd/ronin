import sqlite3

import pytest

from studio_storage.backup import (
    backup_deployment,
    backup_sqlite,
    restore_deployment,
    restore_sqlite,
)


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


def test_deployment_backup_restores_database_and_artifacts_with_digest_verification(
    tmp_path,
) -> None:
    source = tmp_path / "source.sqlite"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "evidence.json").write_text('{"run":"r1"}', encoding="utf-8")
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table VALUES ('ronin')")
        connection.commit()
    bundle = backup_deployment(source, artifacts, tmp_path / "bundle")
    restored_db, restored_artifacts = restore_deployment(
        bundle, tmp_path / "restored" / "database.sqlite", tmp_path / "restored" / "artifacts"
    )
    assert (
        restored_artifacts.joinpath("evidence.json").read_text(encoding="utf-8") == '{"run":"r1"}'
    )
    with sqlite3.connect(restored_db) as connection:
        assert connection.execute("SELECT value FROM values_table").fetchone() == ("ronin",)


def test_deployment_restore_binds_artifact_digest_to_logical_path(tmp_path) -> None:
    source = tmp_path / "source.sqlite"
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "a.json").write_text("a", encoding="utf-8")
    (artifacts / "b.json").write_text("b", encoding="utf-8")
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.commit()
    bundle = backup_deployment(source, artifacts, tmp_path / "bundle")
    (bundle / "artifacts" / "a.json").write_text("b", encoding="utf-8")
    (bundle / "artifacts" / "b.json").write_text("a", encoding="utf-8")
    with pytest.raises(ValueError, match="^deployment artifact tree digest mismatch$"):
        restore_deployment(bundle, tmp_path / "restored.sqlite", tmp_path / "restored-artifacts")
