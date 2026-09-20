from pathlib import Path

import pytest
from studio_synthetic_data.persistence import SqliteSyntheticRunStore, canonical_plan_json


def test_sqlite_run_store_survives_new_instance(tmp_path: Path) -> None:
    path = tmp_path / "ronin.db"
    payload = {"seed": 7, "tables": [{"name": "customers", "rows": 2}]}
    first = SqliteSyntheticRunStore(path)
    created = first.create_or_get(
        run_id="run-1",
        idempotency_key="key-1",
        plan_json=canonical_plan_json(payload),
        plan_fingerprint="fp-1",
        created_at="2026-01-01T00:00:00.000Z",
    )
    first.update_status("run-1", "generated")

    second = SqliteSyntheticRunStore(path)
    restored = second.create_or_get(
        run_id="run-different",
        idempotency_key="key-1",
        plan_json=canonical_plan_json(payload),
        plan_fingerprint="fp-1",
        created_at="2026-01-01T00:00:00.000Z",
    )
    assert created["run_id"] == "run-1"
    assert restored["run_id"] == "run-1"
    assert second.get("run-1")["status"] == "generated"


def test_sqlite_run_store_rejects_idempotency_reuse_for_other_plan(tmp_path: Path) -> None:
    store = SqliteSyntheticRunStore(tmp_path / "ronin.db")
    store.create_or_get(
        run_id="run-1",
        idempotency_key="key-1",
        plan_json="{}",
        plan_fingerprint="fp-1",
        created_at="2026-01-01T00:00:00.000Z",
    )
    with pytest.raises(ValueError, match="another plan"):
        store.create_or_get(
            run_id="run-2",
            idempotency_key="key-1",
            plan_json="{\"different\":true}",
            plan_fingerprint="fp-2",
            created_at="2026-01-01T00:00:00.000Z",
        )
