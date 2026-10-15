import pytest
from studio_migration import MigrationSessionService, SQLiteMigrationSessionStore


def test_sqlite_session_store_survives_new_store_instance(tmp_path) -> None:
    path = tmp_path / "migration.sqlite3"
    session = MigrationSessionService().create("ws-1", "project-1")
    first = SQLiteMigrationSessionStore(path)
    first.save(session)
    second = SQLiteMigrationSessionStore(path)
    snapshot = second.get(session.id, workspace_id="ws-1", project_id="project-1")
    assert snapshot["id"] == session.id
    assert second.list(workspace_id="ws-1", project_id="project-1")[0]["state"] == "draft"


def test_sqlite_session_store_enforces_project_scope(tmp_path) -> None:
    path = tmp_path / "migration.sqlite3"
    session = MigrationSessionService().create("ws-1", "project-1")
    store = SQLiteMigrationSessionStore(path)
    store.save(session)
    with pytest.raises(PermissionError):
        store.get(session.id, workspace_id="ws-2", project_id="project-2")


def test_service_rehydrates_full_session_after_restart(tmp_path) -> None:
    path = tmp_path / "migration.sqlite3"
    first_store = SQLiteMigrationSessionStore(path)
    first_service = MigrationSessionService(first_store)
    session = first_service.create("ws-1", "project-1")
    from studio_migration import MigrationUnit, SourceInventory

    inventory = SourceInventory(
        "iics", "test", (), (MigrationUnit("iics:process:p1", "process", "p1", "ready"),)
    )
    first_service.discover(session.id, inventory)
    first_service.set_scope(session.id, ("iics:process:p1",))
    second_service = MigrationSessionService(SQLiteMigrationSessionStore(path))
    restored = second_service.get(session.id)
    assert restored.inventory is not None
    assert restored.selection is not None
    assert restored.selection.all_units == ("iics:process:p1",)
