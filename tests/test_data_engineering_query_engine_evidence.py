from __future__ import annotations

import json
from pathlib import Path

import pytest
from studio_data_engineering import persist_query_engine_evidence
from studio_query_engine import QueryEvidence, QueryStatus
from studio_storage import LocalArtifactStore


def test_query_engine_evidence_is_content_addressed_and_secret_free(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    ref = persist_query_engine_evidence(
        store,
        project_id="project-1",
        run_id="run-1",
        attempt_id="attempt-1",
        query_evidence=QueryEvidence(
            "a" * 64,
            "optional-provider",
            "provider-q-1",
            "duckdb",
            (("queue", 4), ("execution", 8)),
            translated_sql_digest="b" * 64,
        ),
        status=QueryStatus("succeeded", provider_query_id="provider-q-1"),
        output={"row_count": 2},
    )
    payload = json.loads(store.get_bytes(ref))

    assert payload["version"] == "data-engineering.query-engine-evidence.v1"
    assert payload["query_evidence"]["selected_engine"] == "duckdb"
    assert payload["query_evidence"]["cancelled"] is False
    assert payload["query_evidence"]["engine_stats"] == {}
    assert "SELECT" not in json.dumps(payload)
    assert "token" not in json.dumps(payload).lower()


def test_query_engine_evidence_requires_all_durable_identity_parts(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="attempt_id"):
        persist_query_engine_evidence(
            LocalArtifactStore(tmp_path / "artifacts"),
            project_id="project-1",
            run_id="run-1",
            attempt_id="",
            query_evidence=QueryEvidence("a" * 64, "provider", None, None),
            status=QueryStatus("failed", "provider failed"),
        )
