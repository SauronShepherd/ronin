from __future__ import annotations

from pathlib import Path
from threading import Thread

from pyronin import EvidenceAvailability as SDKEvidenceAvailability
from pyronin import HTTPTransport, Ronin
from studio_execution import DurableExecutionService
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
from studio_server import RoninHTTPServer
from studio_storage import SqliteJobStore

_NOW = Instant("2026-09-08T06:45:00.000000Z")


def test_http_and_sdk_expose_portable_evidence_without_storage_locator(tmp_path: Path) -> None:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=_NOW)
    job_id = JobId("job-http-evidence")
    run_id = RunId("run-http-evidence")
    store.create_job(
        Job(
            id=job_id,
            project_id="demo",
            idempotency_key="http-evidence",
            request_digest="f" * 64,
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
    attempt_id = AttemptId("attempt-http-evidence")
    lease_token = LeaseToken("lease-http-evidence")
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
    for ref in (
        StoredEvidenceRef(
            run_id,
            "cell-1",
            "log",
            "sha256",
            "a" * 64,
            "application/json",
            101,
            "local-evidence://secret/backend/path",
        ),
        StoredEvidenceRef(
            run_id,
            "cell-2",
            "resource",
            None,
            None,
            None,
            None,
            None,
            EvidenceAvailability.UNAVAILABLE,
            "measurement_not_supported",
        ),
    ):
        store.put_evidence(
            attempt_id,
            ref,
            owner="worker",
            lease_token=lease_token,
            now=Instant("2026-09-08T06:45:01.000000Z"),
        )

    service = DurableExecutionService(store, max_workers=2, max_in_flight=4)
    auth_value = "evidence-token"
    server = RoninHTTPServer(("127.0.0.1", 0), service, token=auth_value)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = HTTPTransport(
            f"http://127.0.0.1:{server.server_port}",
            token=auth_value,
            allow_insecure_localhost=True,
            max_retries=0,
        )
        raw = transport.request("GET", "/v1/jobs/job-http-evidence/evidence")
        assert isinstance(raw, dict)
        items = raw["items"]
        assert isinstance(items, list)
        assert all("storage_ref" not in item and "locator" not in item for item in items)

        sdk_items = Ronin(transport=transport).get_evidence("job-http-evidence")
        assert [item.availability for item in sdk_items] == [
            SDKEvidenceAvailability.AVAILABLE,
            SDKEvidenceAvailability.UNAVAILABLE,
        ]
        assert sdk_items[0].portable_identity == (
            "log",
            "sha256",
            "a" * 64,
            "application/json",
            101,
        )
        assert sdk_items[1].portable_identity is None
        assert sdk_items[1].reason == "measurement_not_supported"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        assert not thread.is_alive()
