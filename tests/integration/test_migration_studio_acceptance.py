from __future__ import annotations

import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from studio_migration import (
    MigrationEvidence,
    benchmark,
    decide_promotion,
    discover_iics_zip,
    extract_blueprint,
    generate_project,
    publish_migration_evidence,
    publish_promotion_evidence,
    qualify_generated_project,
    select_scope,
)
from studio_orchestrator import (
    AttemptId,
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


def test_migration_studio_acceptance_flow_publishes_durable_evidence() -> None:
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        bundle.writestr("orders.dtemplate.json", json.dumps({"mappingId": "orders-map"}))
        bundle.writestr(
            "orders.mtt.json",
            json.dumps({"id": "orders-process", "mappingId": "orders-map"}),
        )
    inventory = discover_iics_zip([("export.zip", archive.getvalue())])
    selection = select_scope(inventory, ("iics:process:orders-process",))
    blueprint = extract_blueprint('{"topology":"package","conventions":{"io":"delta"}}')
    project = generate_project(inventory=inventory, selection=selection, blueprint=blueprint)
    qualification = qualify_generated_project(project)
    assert qualification.status == "passed"

    baseline = benchmark(
        lambda: sum(range(100)),
        name="orders",
        measured_runs=2,
        fingerprint_inputs={"dataset": "fixture"},
    )
    candidate = benchmark(
        lambda: sum(range(100)),
        name="orders",
        measured_runs=2,
        fingerprint_inputs={"dataset": "fixture"},
    )
    decision = decide_promotion(
        "orders-native-expressions",
        baseline=baseline,
        candidate=candidate,
        semantic_passed=True,
        quality_passed=qualification.status == "passed",
    )
    assert decision.promoted

    now = "2026-09-19T00:00:00.000000Z"
    store = InMemoryJobStore()
    store.create_job(
        Job(
            JobId("job-migration-acceptance"),
            "project-1",
            "acceptance",
            "a" * 64,
            JobState.QUEUED,
            now,
            now,
        ),
        Run(
            RunId("run-migration-acceptance"),
            JobId("job-migration-acceptance"),
            1,
            RunState.PENDING,
            now,
            now,
            now,
        ),
    )
    claim = store.claim_next_run(
        owner="migration-acceptance",
        lease_token=LeaseToken("lease-acceptance"),
        attempt_id=AttemptId("attempt-acceptance"),
        lease_seconds=30,
        now=now,
    )
    assert claim is not None
    evidence = MigrationEvidence(
        RunId("run-migration-acceptance"),
        "migration-qualification",
        "qualification",
        {
            "inventory_digest": inventory.digest,
            "scope_digest": selection.digest,
            "project_digest": project.project_digest,
            "qualification": qualification.to_payload(),
            "promotion": decision.to_payload(),
        },
    )
    reference = publish_migration_evidence(
        store,
        evidence,
        evidence_ref_factory=StoredEvidenceRef,
        attempt_id=AttemptId("attempt-acceptance"),
        owner="migration-acceptance",
        lease_token=claim.lease_token,
        now=now,
        storage_ref="memory://migration/acceptance.json",
    )
    promotion_reference = publish_promotion_evidence(
        store,
        decision,
        baseline=baseline,
        candidate=candidate,
        semantic_passed=True,
        quality_passed=qualification.status == "passed",
        run_id=RunId("run-migration-acceptance"),
        cell_id="migration-promotion",
        attempt_id=AttemptId("attempt-acceptance"),
        owner="migration-acceptance",
        lease_token=claim.lease_token,
        now=now,
        evidence_ref_factory=StoredEvidenceRef,
        storage_ref="memory://migration/promotion.json",
    )
    assert store.read_evidence(RunId("run-migration-acceptance")) == (
        reference,
        promotion_reference,
    )
