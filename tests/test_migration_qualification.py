import pytest

from tools.migration_qualification import MigrationQualificationError, qualify_migrations


def test_repository_migrations_are_forward_only():
    names = qualify_migrations(__import__("pathlib").Path("python/studio_storage/migrations"))
    assert names
    assert all("rollback" not in name for name in names)


def test_reverse_migration_is_rejected(tmp_path):
    (tmp_path / "jobs_001_create.sql").write_text("CREATE TABLE jobs(id TEXT);", encoding="utf-8")
    (tmp_path / "jobs_002_rollback.sql").write_text("DROP TABLE jobs;", encoding="utf-8")
    with pytest.raises(MigrationQualificationError, match="reverse"):
        qualify_migrations(tmp_path)
