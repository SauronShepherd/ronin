from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

from pyronin import HTTPTransport, Ronin
from studio_cli import main
from studio_execution import DurableExecutionService
from studio_orchestrator import (
    AttemptId,
    AttemptState,
    Instant,
    JobId,
    LeaseToken,
    StoredExecutionEvent,
)
from studio_server import RoninHTTPServer
from studio_storage import SqliteJobStore

_NOW = Instant("2099-01-01T00:00:00.000000Z")
_TOKEN = "cli-integration-token"


def test_cli_operator_surface_reuses_real_http_contract_and_terminal_idempotency(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=_NOW)
    service = DurableExecutionService(store, max_workers=2, max_in_flight=4)
    server = RoninHTTPServer(("127.0.0.1", 0), service, token=_TOKEN)
    thread = Thread(target=server.serve_forever, name="ronin-cli-http", daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("RONIN_URL", base_url)
    monkeypatch.setenv("RONIN_TOKEN", _TOKEN)

    try:
        assert main(
            [
                "submit",
                "examples/demo",
                "-t",
                "notebooks/etl.ronin.json",
                "--idempotency-key",
                "cli-k1",
                "--param",
                "limit=7",
                "--json",
            ]
        ) == 0
        submitted = json.loads(capsys.readouterr().out)
        assert submitted["state"] == "queued"
        job_id = submitted["id"]
        run_id = store.get_run_id_for_job(JobId(job_id))
        assert run_id is not None

        first_attempt = AttemptId("attempt-cli-1")
        first_lease = LeaseToken("lease-cli-1")
        first_claim = store.claim_next_run(
            owner="worker-cli-1",
            lease_token=first_lease,
            attempt_id=first_attempt,
            lease_seconds=1,
            now=_NOW,
        )
        assert first_claim is not None
        store.append_events(
            first_attempt,
            (
                StoredExecutionEvent(first_attempt, 0, "cell.succeeded", "cell-1", Instant("2099-01-01T00:00:00.100000Z")),
                StoredExecutionEvent(first_attempt, 1, "cell.succeeded", "cell-2", Instant("2099-01-01T00:00:00.200000Z")),
            ),
            owner="worker-cli-1",
            lease_token=first_lease,
            now=Instant("2099-01-01T00:00:00.500000Z"),
        )
        assert store.reclaim_expired(now=Instant("2099-01-01T00:00:02.000000Z")) == (run_id,)

        second_attempt = AttemptId("attempt-cli-2")
        second_lease = LeaseToken("lease-cli-2")
        second_claim = store.claim_next_run(
            owner="worker-cli-2",
            lease_token=second_lease,
            attempt_id=second_attempt,
            lease_seconds=30,
            now=Instant("2099-01-01T00:00:03.000000Z"),
        )
        assert second_claim is not None
        store.append_events(
            second_attempt,
            (
                StoredExecutionEvent(second_attempt, 0, "cell.succeeded", "cell-3", Instant("2099-01-01T00:00:03.100000Z")),
                StoredExecutionEvent(second_attempt, 1, "worker.attempt.succeeded", "terminal", Instant("2099-01-01T00:00:03.200000Z")),
            ),
            owner="worker-cli-2",
            lease_token=second_lease,
            now=Instant("2099-01-01T00:00:03.500000Z"),
        )
        store.complete_attempt(
            second_attempt,
            state=AttemptState.SUCCEEDED,
            failure_code=None,
            owner="worker-cli-2",
            lease_token=second_lease,
            now=Instant("2099-01-01T00:00:04.000000Z"),
        )

        assert main(["status", job_id, "--json"]) == 0
        status = json.loads(capsys.readouterr().out)
        assert status == {"failure_code": None, "id": job_id, "state": "succeeded"}

        assert main(["logs", job_id, "--json"]) == 0
        events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert [event["sequence"] for event in events] == [0, 1, 2, 3]
        assert [event["attempt_id"] for event in events] == [
            str(first_attempt),
            str(first_attempt),
            str(second_attempt),
            str(second_attempt),
        ]
        assert events[-1]["kind"] == "worker.attempt.succeeded"

        assert main(["jobs", "--project", "examples/demo", "--json"]) == 0
        page = json.loads(capsys.readouterr().out)
        assert [job["id"] for job in page["items"]] == [job_id]

        assert main(
            [
                "submit",
                "examples/demo",
                "-t",
                "notebooks/etl.ronin.json",
                "--idempotency-key",
                "cli-k1",
                "--param",
                "limit=7",
                "--json",
            ]
        ) == 0
        replay = json.loads(capsys.readouterr().out)
        assert replay["id"] == job_id
        assert replay["state"] == "succeeded"
        assert store.get_run_id_for_job(JobId(job_id)) == run_id
        assert len(store.list_jobs(project_id="examples/demo", state=None, limit=10, cursor=None).items) == 1

        sdk = Ronin(
            transport=HTTPTransport(
                base_url,
                token=_TOKEN,
                allow_insecure_localhost=True,
                max_retries=0,
            )
        )
        assert sdk.get_job(job_id).state.value == status["state"]
        sdk_replay = sdk.submit(
            project="examples/demo",
            target="notebooks/etl.ronin.json",
            parameters={"limit": 7},
            idempotency_key="cli-k1",
        )
        assert sdk_replay.id == job_id
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        assert not thread.is_alive()


def test_cancel_command_exposes_backend_state_without_claiming_container_cleanup(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=_NOW)
    service = DurableExecutionService(store)
    server = RoninHTTPServer(("127.0.0.1", 0), service, token=_TOKEN)
    thread = Thread(target=server.serve_forever, name="ronin-cli-cancel", daemon=True)
    thread.start()
    monkeypatch.setenv("RONIN_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("RONIN_TOKEN", _TOKEN)
    try:
        assert main(["submit", "examples/demo", "-t", "notebooks/etl", "--json"]) == 0
        job_id = json.loads(capsys.readouterr().out)["id"]
        assert main(["cancel", job_id, "--json"]) == 0
        cancelled = json.loads(capsys.readouterr().out)
        assert cancelled["id"] == job_id
        assert cancelled["state"] == "cancelled"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        assert not thread.is_alive()
