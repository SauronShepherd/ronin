from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

import pytest

from studio_orchestrator import (
    AttemptId,
    EvidenceAvailability,
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
from studio_storage import SqliteJobStore

_NOW = Instant("2026-09-08T06:30:00.000000Z")


def _claimed_store(tmp_path: Path) -> tuple[SqliteJobStore, RunId, AttemptId, LeaseToken]:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=_NOW)
    job_id = JobId("job-evidence-states")
    run_id = RunId("run-evidence-states")
    store.create_job(
        Job(
            id=job_id,
            project_id="demo",
            idempotency_key="evidence-states",
            request_digest="a" * 64,
            state=JobState.QUEUED,
            created_at=_NOW,
            updated_at=_NOW,
            target="notebook",
            parameters_json="{}",
        ),
        Run(
            id=run_id,
            job_id=job_id,
            ordinal=1,
            state=RunState.PENDING,
            not_before=_NOW,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )
    attempt_id = AttemptId("attempt-evidence-states")
    lease_token = LeaseToken("lease-evidence-states")
    assert (
        store.claim_next_run(
            owner="worker",
            lease_token=lease_token,
            attempt_id=attempt_id,
            lease_seconds=30,
            now=_NOW,
        )
        is not None
    )
    return store, run_id, attempt_id, lease_token


def test_all_availability_states_round_trip_without_fabricating_identity(tmp_path: Path) -> None:
    store, run_id, attempt_id, lease_token = _claimed_store(tmp_path)
    refs = (
        StoredEvidenceRef(
            run_id,
            "cell-a",
            "log",
            "sha256",
            "1" * 64,
            "application/json",
            10,
            "local-evidence://a/log.json",
            EvidenceAvailability.AVAILABLE,
        ),
        StoredEvidenceRef(
            run_id,
            "cell-b",
            "resource",
            "sha256",
            "2" * 64,
            "application/json",
            20,
            None,
            EvidenceAvailability.MISSING,
        ),
        StoredEvidenceRef(
            run_id,
            "cell-c",
            "output",
            "sha256",
            "3" * 64,
            "application/octet-stream",
            30,
            None,
            EvidenceAvailability.TOMBSTONED,
        ),
        StoredEvidenceRef(
            run_id,
            "cell-d",
            "trace",
            None,
            None,
            None,
            None,
            None,
            EvidenceAvailability.UNAVAILABLE,
            "collector_failed",
        ),
    )
    for ref in refs:
        store.put_evidence(
            attempt_id,
            ref,
            owner="worker",
            lease_token=lease_token,
            now=Instant("2026-09-08T06:30:01.000000Z"),
        )

    stored = store.read_evidence(run_id)
    assert {ref.availability for ref in stored} == set(EvidenceAvailability)
    unavailable = next(
        ref for ref in stored if ref.availability is EvidenceAvailability.UNAVAILABLE
    )
    assert unavailable.portable_identity is None
    assert unavailable.storage_ref is None
    assert unavailable.unavailable_reason == "collector_failed"
    assert "storage_ref" not in unavailable.public_payload()
    assert "locator" not in unavailable.public_payload()

    with sqlite3.connect(tmp_path / "ronin.db") as connection:
        row = connection.execute(
            "SELECT digest_algorithm,digest,size_bytes,storage_ref FROM evidence_refs "
            "WHERE availability='unavailable'"
        ).fetchone()
    assert row == (None, None, None, None)


def test_unavailable_evidence_rejects_fake_content_identity() -> None:
    with pytest.raises(ValueError, match="cannot carry content identity"):
        StoredEvidenceRef(
            RunId("run"),
            "cell",
            "log",
            "sha256",
            "0" * 64,
            None,
            0,
            None,
            EvidenceAvailability.UNAVAILABLE,
            "not_collected",
        )


def test_missing_and_tombstoned_preserve_logical_identity() -> None:
    for availability in (EvidenceAvailability.MISSING, EvidenceAvailability.TOMBSTONED):
        ref = StoredEvidenceRef(
            RunId("run"),
            "cell",
            "resource",
            "sha256",
            "a" * 64,
            "application/json",
            42,
            None,
            availability,
        )
        assert ref.portable_identity == (
            "resource",
            "sha256",
            "a" * 64,
            "application/json",
            42,
        )
        with pytest.raises(ValueError, match="not currently available"):
            ref.to_execution_reference()


def test_stored_evidence_validation_rejects_malformed_metadata() -> None:
    run_id = RunId("run-validation")

    with pytest.raises(ValueError, match="role must be non-empty and trimmed"):
        StoredEvidenceRef(
            run_id,
            "cell",
            " log ",
            "sha256",
            "a" * 64,
            None,
            1,
            "local-evidence://log",
        )

    with pytest.raises(ValueError, match="unsupported evidence availability"):
        StoredEvidenceRef(
            run_id,
            "cell",
            "log",
            "sha256",
            "a" * 64,
            None,
            1,
            "local-evidence://log",
            cast(EvidenceAvailability, "unknown"),
        )

    for reason in (None, "", " padded "):
        with pytest.raises(ValueError, match="non-empty trimmed reason"):
            StoredEvidenceRef(
                run_id,
                "cell",
                "log",
                None,
                None,
                None,
                None,
                None,
                EvidenceAvailability.UNAVAILABLE,
                reason,
            )

    with pytest.raises(ValueError, match="require content identity"):
        StoredEvidenceRef(
            run_id,
            "cell",
            "log",
            None,
            None,
            None,
            None,
            None,
            EvidenceAvailability.AVAILABLE,
        )

    with pytest.raises(ValueError, match="unsupported evidence digest algorithm"):
        StoredEvidenceRef(
            run_id,
            "cell",
            "log",
            "md5",
            "a" * 64,
            None,
            1,
            "local-evidence://log",
        )

    for digest in ("A" * 64, "g" * 64, "a" * 63):
        with pytest.raises(ValueError, match="lowercase SHA-256 hex"):
            StoredEvidenceRef(
                run_id,
                "cell",
                "log",
                "sha256",
                digest,
                None,
                1,
                "local-evidence://log",
            )

    with pytest.raises(ValueError, match="size must be non-negative"):
        StoredEvidenceRef(
            run_id,
            "cell",
            "log",
            "sha256",
            "a" * 64,
            None,
            -1,
            "local-evidence://log",
        )

    with pytest.raises(ValueError, match="only unavailable evidence"):
        StoredEvidenceRef(
            run_id,
            "cell",
            "log",
            "sha256",
            "a" * 64,
            None,
            1,
            "local-evidence://log",
            EvidenceAvailability.AVAILABLE,
            "unexpected_reason",
        )


def test_available_evidence_without_locator_is_not_kernel_portable() -> None:
    ref = StoredEvidenceRef(
        RunId("run-no-locator"),
        "cell",
        "log",
        "sha256",
        "a" * 64,
        "application/json",
        1,
        None,
        EvidenceAvailability.AVAILABLE,
    )
    assert ref.portable_identity is not None
    with pytest.raises(ValueError, match="unavailable as a portable execution reference"):
        ref.to_execution_reference()
