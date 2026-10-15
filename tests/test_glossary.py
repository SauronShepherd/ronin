from pathlib import Path

import pytest
from studio_core import GlossaryTerm, GlossaryTermId, Workspace, WorkspaceId
from studio_storage import GlossaryConflict, SqliteGlossaryStore, SqliteWorkspaceStore

NOW = "2026-09-21T00:00:00.000000Z"
WS = WorkspaceId("workspace-1")


def _store(tmp_path: Path) -> SqliteGlossaryStore:
    database = tmp_path / "ronin.db"
    workspaces = SqliteWorkspaceStore(database, migration_now=NOW)
    workspaces.create_workspace(Workspace(WS, "Workspace"), now=NOW)
    return SqliteGlossaryStore(database, migration_now=NOW)


def test_glossary_versions_are_immutable_idempotent_and_searchable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    term = GlossaryTerm(GlossaryTermId("customer"), "1", "Customer", "A buyer", "data-team")
    assert store.put(WS, term, now=NOW) == term
    assert store.put(WS, term, now=NOW) == term
    newer = GlossaryTerm(term.id, "2", term.name, "A buyer or account", term.owner)
    store.put(WS, newer, now=NOW)
    assert store.list_versions(WS, term.id) == (term, newer)
    assert store.list_latest(WS) == (newer,)
    assert store.search(WS, "account") == (newer,)


def test_glossary_conflict_and_bounds_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    term = GlossaryTerm(GlossaryTermId("customer"), "1", "Customer", "A buyer", "data-team")
    store.put(WS, term, now=NOW)
    with pytest.raises(GlossaryConflict):
        store.put(WS, GlossaryTerm(term.id, "1", term.name, "Different", term.owner), now=NOW)
    with pytest.raises(ValueError, match="query"):
        store.search(WS, "")
    with pytest.raises(ValueError, match="limit"):
        store.search(WS, "customer", limit=0)
