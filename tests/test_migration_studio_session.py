import pytest
import studio_migration.session as session_module
from studio_migration import (
    MigrationSessionService,
    MigrationUnit,
    SourceInventory,
    SQLiteMigrationSessionStore,
)


def test_session_lifecycle_freezes_scope_before_conversion() -> None:
    service = MigrationSessionService()
    session = service.create("ws-1", "project-1")
    inventory = SourceInventory(
        "iics",
        "1",
        (),
        (
            MigrationUnit("process:p", "process", "p", "ready", ("mapping:m",)),
            MigrationUnit("mapping:m", "mapping", "m", "ready"),
        ),
    )
    session = service.discover(session.id, inventory)
    session = service.set_scope(session.id, ("process:p",))
    assert session.state == "scope_ready"
    assert session.selection is not None
    assert session.selection.auto_included == ("mapping:m",)
    session = service.begin_conversion(session.id)
    assert session.state == "converting"
    assert service.complete(session.id, "result-digest").state == "completed"


def test_session_rejects_conversion_without_scope() -> None:
    service = MigrationSessionService()
    session = service.create("ws-1", "project-1")
    with pytest.raises(ValueError, match="state"):
        service.begin_conversion(session.id)


def test_session_service_persists_each_transition(tmp_path) -> None:
    store = SQLiteMigrationSessionStore(tmp_path / "migration.sqlite3")
    service = MigrationSessionService(store)
    session = service.create("ws-1", "project-1")
    inventory = SourceInventory("iics", "1", (), (MigrationUnit("m", "mapping", "m", "ready"),))
    service.discover(session.id, inventory)
    snapshots = store.list(workspace_id="ws-1", project_id="project-1")
    assert snapshots[0]["state"] == "scope_ready"


def test_session_artifact_budget_is_enforced_before_state_change(monkeypatch) -> None:
    service = MigrationSessionService()
    session = service.create("ws", "project")
    monkeypatch.setattr(session_module, "MAX_SESSION_ARTIFACTS", 1)
    first = session_module.SourceArtifact("one.zip", "a" * 64, 10, "application/zip")
    second = session_module.SourceArtifact("two.zip", "b" * 64, 10, "application/zip")
    service.add_artifact(session.id, first)
    with pytest.raises(ValueError, match="at most 1 artifacts"):
        service.add_artifact(session.id, second)
    assert service.get(session.id).inventory is not None
    assert len(service.get(session.id).inventory.artifacts) == 1
