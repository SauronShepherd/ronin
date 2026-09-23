from __future__ import annotations

import pytest
from studio_data_engineering import SqlExecutionRecord, SqliteSqlEditorStore


def test_sql_editor_keeps_bounded_execution_history(tmp_path) -> None:
    store = SqliteSqlEditorStore(tmp_path / "editor.db")
    revision = store.save(project_id="p", query_id="q", sql="SELECT 1")
    record = SqlExecutionRecord(
        "exec-1", "p", "q", revision.revision, revision.provider, "succeeded", 1, "sha256:r"
    )
    assert store.record_execution(record) == record
    assert store.history(project_id="p", query_id="q") == (record,)


def test_sql_editor_history_requires_matching_revision_and_provider(tmp_path) -> None:
    store = SqliteSqlEditorStore(tmp_path / "editor.db")
    revision = store.save(project_id="p", query_id="q", sql="SELECT 1", provider="local")
    with pytest.raises(ValueError, match="existing query revision"):
        store.record_execution(SqlExecutionRecord("missing", "p", "q", 2, "local", "failed", 0))
    with pytest.raises(ValueError, match="provider"):
        store.record_execution(
            SqlExecutionRecord("wrong-provider", "p", "q", revision.revision, "remote", "failed", 0)
        )
