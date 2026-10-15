from concurrent.futures import ThreadPoolExecutor

import pytest
from studio_synthetic_data import (
    GovernStudioService,
    RunStatus,
    SqliteRunStore,
    plan_from_payload,
)


def _plan():
    return plan_from_payload(
        {
            "seed": 4,
            "tables": [
                {
                    "name": "customers",
                    "rows": 2,
                    "primary_key": "id",
                    "columns": [{"name": "id", "kind": "integer", "nullable": False}],
                }
            ],
        }
    )


def test_service_is_idempotent_and_has_explicit_lifecycle() -> None:
    service = GovernStudioService()
    first = service.create_run(_plan(), idempotency_key="same")
    assert service.create_run(_plan(), idempotency_key="same") == first
    generated = service.generate(first.run_id, _plan())
    assert generated.status is RunStatus.GENERATED
    validated = service.validate(first.run_id, _plan())
    assert validated.status is RunStatus.VALIDATED
    assert validated.validation.evidence_id.startswith("validation-")


def test_service_rejects_validation_without_generation() -> None:
    service = GovernStudioService()
    run = service.create_run(_plan(), idempotency_key="validate-before-generate")
    with pytest.raises(ValueError, match="no generated result"):
        service.validate(run.run_id, _plan())


def test_idempotency_key_cannot_be_reused_for_another_plan() -> None:
    service = GovernStudioService()
    service.create_run(_plan(), idempotency_key="strict-key")
    other = plan_from_payload({"seed": 99, "tables": []})
    with pytest.raises(ValueError, match="already belongs"):
        service.create_run(other, idempotency_key="strict-key")


def test_plan_fingerprint_includes_schema_and_relationships() -> None:
    service = GovernStudioService()
    base = _plan()
    changed = plan_from_payload(
        {
            "seed": 4,
            "tables": [
                {
                    "name": "customers",
                    "rows": 3,
                    "primary_key": "id",
                    "columns": [{"name": "id", "kind": "integer", "nullable": False}],
                }
            ],
        }
    )
    first = service.create_run(base, idempotency_key="schema-key")
    second = service.create_run(changed, idempotency_key="different-key")
    assert first.plan_fingerprint != second.plan_fingerprint


def test_run_rejects_a_different_plan_during_generation_and_validation() -> None:
    service = GovernStudioService()
    original = _plan()
    changed = plan_from_payload({"seed": 4, "tables": []})
    run = service.create_run(original, idempotency_key="run-plan-match")
    with pytest.raises(ValueError, match="does not match"):
        service.generate(run.run_id, changed)
    service.generate(run.run_id, original)
    with pytest.raises(ValueError, match="does not match"):
        service.validate(run.run_id, changed)


def test_sqlite_idempotency_is_safe_across_concurrent_services(tmp_path) -> None:
    database = str(tmp_path / "concurrent.sqlite3")
    plan = _plan()

    def create() -> str:
        service = GovernStudioService(SqliteRunStore(database))
        return service.create_run(plan, idempotency_key="concurrent-key").run_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        run_ids = list(executor.map(lambda _item: create(), range(4)))
    assert set(run_ids) == {run_ids[0]}


def test_sqlite_artifact_sequences_are_safe_concurrently(tmp_path) -> None:
    database = str(tmp_path / "artifact-concurrent.sqlite3")
    plan = _plan()
    seed_service = GovernStudioService(SqliteRunStore(database))
    run = seed_service.create_run(plan, idempotency_key="artifact-concurrent")
    seed_service.generate(run.run_id, plan)

    def export() -> str:
        service = GovernStudioService(SqliteRunStore(database))
        service.export(run.run_id, format_id="jsonl", table_name="customers")
        return run.run_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _item: export(), range(4)))
    reopened = GovernStudioService(SqliteRunStore(database))
    assert len(reopened.artifacts(run.run_id)) == 4


def test_sqlite_store_survives_service_restart_and_preserves_idempotency(tmp_path) -> None:
    database = str(tmp_path / "govern.sqlite3")
    plan = _plan()
    first_service = GovernStudioService(SqliteRunStore(database))
    created = first_service.create_run(plan, idempotency_key="durable")
    generated = first_service.generate(created.run_id, plan)
    assert generated.status is RunStatus.GENERATED

    restarted = GovernStudioService(SqliteRunStore(database))
    same = restarted.create_run(plan, idempotency_key="durable")
    assert same == generated
    validated = restarted.validate(created.run_id, plan)
    assert validated.status is RunStatus.VALIDATED
    assert restarted.get_run(created.run_id).validation.evidence_id.startswith("validation-")


def test_sqlite_store_persists_export_artifact_metadata(tmp_path) -> None:
    database = str(tmp_path / "artifacts.sqlite3")
    plan = _plan()
    service = GovernStudioService(SqliteRunStore(database))
    run = service.create_run(plan, idempotency_key="artifact-run")
    service.generate(run.run_id, plan)
    content = service.export(run.run_id, format_id="jsonl", table_name="customers")
    assert content.count("\n") == 2
    reopened = GovernStudioService(SqliteRunStore(database))
    artifacts = reopened.artifacts(run.run_id)
    assert artifacts[0]["format_id"] == "jsonl"
    assert artifacts[0]["size_bytes"] == len(content.encode())
    assert artifacts[0]["storage_ref"].endswith(artifacts[0]["digest"])


def test_generation_invokes_publication_hook_before_commit() -> None:
    published = []
    service = GovernStudioService(
        publication_hook=lambda run_id, result: published.append((run_id, result.plan_fingerprint))
    )
    plan = _plan()
    run = service.create_run(plan, idempotency_key="publish-hook")
    generated = service.generate(run.run_id, plan)
    assert generated.status is RunStatus.GENERATED
    assert published == [(run.run_id, generated.result.plan_fingerprint)]
