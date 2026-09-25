import pytest

from studio_migration import (
    BenchmarkResult,
    MigrationEvidence,
    OptimizationDecision,
    publish_evidence_bundle,
    publish_promotion_evidence,
    publish_validation_evidence,
    validate_results,
    validation_evidence,
)
from studio_orchestrator import (
    AttemptId,
    Instant,
    Job,
    JobId,
    JobState,
    LeaseToken,
    Run,
    RunId,
    RunState,
    StoredEvidenceRef,
)
from studio_storage import InMemoryJobStore


def test_migration_evidence_is_canonical_and_content_addressed() -> None:
    evidence = MigrationEvidence(
        RunId("run-migration"),
        "qualification",
        "migration-qualification",
        {"status": "passed", "checks": [{"id": "schema", "status": "pass"}]},
    )
    reference = evidence.reference(
        StoredEvidenceRef, "local-evidence://run-migration/qualification.json"
    )
    assert reference.media_type == "application/json"
    assert reference.digest_algorithm == "sha256"
    assert reference.size_bytes == len(evidence.canonical_bytes())
    assert reference.digest


def test_evidence_bundle_uses_one_fenced_context_for_each_cell() -> None:
    class Store:
        def __init__(self) -> None:
            self.references: list[object] = []

        def put_evidence(self, _attempt, reference, **_kwargs) -> None:
            self.references.append(reference)

    store = Store()
    refs = publish_evidence_bundle(
        store,
        (
            MigrationEvidence(RunId("run-bundle"), "qualification", "migration", {"ok": True}),
            MigrationEvidence(RunId("run-bundle"), "promotion", "migration", {"ok": True}),
        ),
        attempt_id=AttemptId("attempt-bundle"),
        owner="bundle-worker",
        lease_token=LeaseToken("lease-bundle"),
        now=Instant("2026-09-19T00:00:00.000000Z"),
        evidence_ref_factory=StoredEvidenceRef,
        storage_prefix="memory://migration/bundle",
    )
    assert tuple(store.references) == refs
    assert [item.storage_ref for item in refs] == [
        "memory://migration/bundle/qualification.json",
        "memory://migration/bundle/promotion.json",
    ]


def test_evidence_bundle_rejects_path_traversal_and_duplicate_cells() -> None:
    evidence = MigrationEvidence(RunId("run-bundle"), "../escape", "migration", {})
    with pytest.raises(ValueError, match="path-safe"):
        publish_evidence_bundle(
            object(),
            (evidence,),
            attempt_id=AttemptId("attempt-bundle"),
            owner="bundle-worker",
            lease_token=LeaseToken("lease-bundle"),
            now=Instant("2026-09-19T00:00:00.000000Z"),
            evidence_ref_factory=StoredEvidenceRef,
            storage_prefix="memory://migration/bundle",
        )
    duplicate = MigrationEvidence(RunId("run-bundle"), "same", "migration", {})
    with pytest.raises(ValueError, match="unique"):
        publish_evidence_bundle(
            object(),
            (duplicate, duplicate),
            attempt_id=AttemptId("attempt-bundle"),
            owner="bundle-worker",
            lease_token=LeaseToken("lease-bundle"),
            now=Instant("2026-09-19T00:00:00.000000Z"),
            evidence_ref_factory=StoredEvidenceRef,
            storage_prefix="memory://migration/bundle",
        )


def test_migration_evidence_is_published_to_a_fenced_run() -> None:
    now = "2026-09-19T00:00:00.000000Z"
    store = InMemoryJobStore()
    store.create_job(
        Job(
            JobId("job-migration"),
            "project-1",
            "migration-key",
            "a" * 64,
            JobState.QUEUED,
            now,
            now,
        ),
        Run(RunId("run-migration"), JobId("job-migration"), 1, RunState.PENDING, now, now, now),
    )
    claim = store.claim_next_run(
        owner="migration-worker",
        lease_token=LeaseToken("lease-migration"),
        attempt_id=AttemptId("attempt-migration"),
        lease_seconds=30,
        now=now,
    )
    assert claim is not None
    from studio_migration import publish_migration_evidence

    reference = publish_migration_evidence(
        store,
        MigrationEvidence(RunId("run-migration"), "qualification", "runtime", {"status": "passed"}),
        attempt_id=AttemptId("attempt-migration"),
        evidence_ref_factory=StoredEvidenceRef,
        owner="migration-worker",
        lease_token=claim.lease_token,
        now=Instant(now),
        storage_ref="memory://migration/qualification.json",
    )
    assert store.read_evidence(RunId("run-migration")) == (reference,)


def test_validation_evidence_helper_publishes_to_fenced_run() -> None:
    now = "2026-09-19T00:00:00.000000Z"
    store = InMemoryJobStore()
    store.create_job(
        Job(
            JobId("job-validation"),
            "project-1",
            "validation-key",
            "b" * 64,
            JobState.QUEUED,
            now,
            now,
        ),
        Run(RunId("run-validation"), JobId("job-validation"), 1, RunState.PENDING, now, now, now),
    )
    claim = store.claim_next_run(
        owner="validation-worker",
        lease_token=LeaseToken("lease-validation"),
        attempt_id=AttemptId("attempt-validation"),
        lease_seconds=30,
        now=now,
    )
    assert claim is not None
    report = validate_results([{"id": "a"}], [{"id": "a"}], asset_id="orders")
    reference = publish_validation_evidence(
        store,
        report,
        run_id=RunId("run-validation"),
        cell_id="validation-orders",
        attempt_id=AttemptId("attempt-validation"),
        owner="validation-worker",
        lease_token=claim.lease_token,
        now=Instant(now),
        evidence_ref_factory=StoredEvidenceRef,
        storage_ref="memory://migration/orders.json",
    )
    assert store.read_evidence(RunId("run-validation")) == (reference,)


def test_promotion_evidence_helper_publishes_to_fenced_run() -> None:
    now = "2026-09-19T00:00:00.000000Z"
    store = InMemoryJobStore()
    store.create_job(
        Job(
            JobId("job-promotion"),
            "project-1",
            "promotion-key",
            "c" * 64,
            JobState.QUEUED,
            now,
            now,
        ),
        Run(RunId("run-promotion"), JobId("job-promotion"), 1, RunState.PENDING, now, now, now),
    )
    claim = store.claim_next_run(
        owner="promotion-worker",
        lease_token=LeaseToken("lease-promotion"),
        attempt_id=AttemptId("attempt-promotion"),
        lease_seconds=30,
        now=now,
    )
    assert claim is not None
    baseline = BenchmarkResult("orders", 1, 3, (10.0, 9.0, 11.0), 10.0, "same")
    candidate = BenchmarkResult("orders", 1, 3, (9.0, 8.0, 10.0), 9.0, "same")
    reference = publish_promotion_evidence(
        store,
        OptimizationDecision("candidate-1", True, "approved", 10.0, 9.0),
        baseline=baseline,
        candidate=candidate,
        semantic_passed=True,
        quality_passed=True,
        run_id=RunId("run-promotion"),
        cell_id="promotion-orders",
        attempt_id=AttemptId("attempt-promotion"),
        owner="promotion-worker",
        lease_token=claim.lease_token,
        now=Instant(now),
        evidence_ref_factory=StoredEvidenceRef,
        storage_ref="memory://migration/orders-promotion.json",
    )
    assert store.read_evidence(RunId("run-promotion")) == (reference,)


def test_validation_result_becomes_provenance_bearing_evidence() -> None:
    report = validate_results([{"id": "a"}], [{"id": "a"}], asset_id="orders", level="full")
    evidence = validation_evidence(
        report,
        run_id=RunId("run-validation"),
        cell_id="validation-orders",
        storage_ref="memory://migration/orders-validation.json",
    )
    assert evidence.role == "migration-validation"
    assert evidence.payload["report_digest"] == report.digest
    assert evidence.payload["expected_digest"] == report.expected_digest
