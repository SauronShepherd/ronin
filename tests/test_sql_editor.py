from __future__ import annotations

import pytest
from studio_data_engineering import SqliteSqlEditorStore


def test_sql_editor_revisions_are_durable_and_digestable(tmp_path) -> None:
    store = SqliteSqlEditorStore(tmp_path / "editor.db")
    first = store.save(project_id="p", query_id="q", sql="SELECT 1")
    second = store.save(
        project_id="p", query_id="q", sql="SELECT 2", expected_revision=first.revision
    )
    assert second.revision == 2
    assert store.latest(project_id="p", query_id="q") == second
    assert len(second.digest) == 64


def test_sql_editor_rejects_stale_revision(tmp_path) -> None:
    store = SqliteSqlEditorStore(tmp_path / "editor.db")
    store.save(project_id="p", query_id="q", sql="SELECT 1")
    with pytest.raises(ValueError, match="stale"):
        store.save(project_id="p", query_id="q", sql="SELECT 2", expected_revision=0)


def test_sql_editor_lists_latest_revision_per_saved_query(tmp_path) -> None:
    store = SqliteSqlEditorStore(tmp_path / "editor.db")
    store.save(project_id="p", query_id="z", sql="SELECT 1")
    first = store.save(project_id="p", query_id="a", sql="SELECT 2")
    latest = store.save(
        project_id="p", query_id="a", sql="SELECT 3", expected_revision=first.revision
    )
    assert [(item.query_id, item.revision) for item in store.list_queries(project_id="p")] == [
        ("a", latest.revision),
        ("z", 1),
    ]
