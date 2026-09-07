from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

import pytest
from pyronin import APIError, HTTPTransport, Ronin
from pyronin import JobState as SDKJobState
from studio_execution import DurableExecutionService
from studio_orchestrator import AttemptId, Instant, JobId, LeaseToken, StoredExecutionEvent
from studio_server import SUPPORTED_ROUTES, RoninHTTPServer
from studio_storage import SqliteJobStore

_MIGRATION_NOW = Instant("2026-09-07T06:00:00.000000Z")
_AUTHORIZATION = "".join(("integration", "-credential"))


def test_openapi_routes_and_sdk_states_match_implemented_contract() -> None:
    document = json.loads(Path("api/openapi-v1.json").read_text(encoding="utf-8"))
    documented_routes = {
        (method.upper(), path)
        for path, path_item in document["paths"].items()
        for method in path_item
        if method in {"get", "post"}
    }
    assert documented_routes == SUPPORTED_ROUTES

    states = document["components"]["schemas"]["Job"]["properties"]["state"]["enum"]
    assert set(states) == {state.value for state in SDKJobState}
    assert document["security"] == [{"bearerAuth": []}]
    event = document["components"]["schemas"]["JobEvent"]
    assert event["additionalProperties"] is False
    assert set(event["required"]) == {
        "sequence",
        "attempt_id",
        "attempt_sequence",
        "kind",
        "message",
        "occurred_at",
    }


def test_real_http_sqlite_and_pyronin_submit_list_status_events_cancel_idempotency(
    tmp_path: Path,
) -> None:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(store, max_workers=2, max_in_flight=4)
    server = RoninHTTPServer(("127.0.0.1", 0), service, token=_AUTHORIZATION)
    server_thread = Thread(target=server.serve_forever, name="ronin-http-test", daemon=True)
    server_thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        unauthenticated = Ronin(base_url)
        with pytest.raises(APIError) as unauthorized:
            unauthenticated.get_job("missing")
        assert unauthorized.value.status_code == 401
        assert unauthorized.value.code == "unauthorized"

        transport = HTTPTransport(
            base_url,
            token=_AUTHORIZATION,
            allow_insecure_localhost=True,
            max_retries=0,
        )
        client = Ronin(transport=transport)
        first = client.submit(
            project="examples/demo",
            target="notebooks/etl",
            parameters={"limit": 7},
            idempotency_key="acceptance-k1",
        )

        run_id = store.get_run_id_for_job(JobId(first.id))
        assert run_id is not None
        first_attempt = AttemptId("attempt-http-events-1")
        first_lease = LeaseToken("lease-http-events-1")
        claimed = store.claim_next_run(
            owner="worker-http-events-1",
            lease_token=first_lease,
            attempt_id=first_attempt,
            lease_seconds=1,
            now=Instant("2099-01-01T00:00:00.000000Z"),
        )
        assert claimed is not None
        assert claimed.run.id == run_id
        store.append_events(
            first_attempt,
            (
                StoredExecutionEvent(
                    first_attempt,
                    0,
                    "cell.succeeded",
                    "cell-1",
                    Instant("2099-01-01T00:00:00.100000Z"),
                ),
                StoredExecutionEvent(
                    first_attempt,
                    1,
                    "cell.succeeded",
                    "cell-2",
                    Instant("2099-01-01T00:00:00.200000Z"),
                ),
            ),
            owner="worker-http-events-1",
            lease_token=first_lease,
            now=Instant("2099-01-01T00:00:00.500000Z"),
        )
        assert store.reclaim_expired(now=Instant("2099-01-01T00:00:02.000000Z")) == (run_id,)
        second_attempt = AttemptId("attempt-http-events-2")
        second_lease = LeaseToken("lease-http-events-2")
        reclaimed = store.claim_next_run(
            owner="worker-http-events-2",
            lease_token=second_lease,
            attempt_id=second_attempt,
            lease_seconds=30,
            now=Instant("2099-01-01T00:00:03.000000Z"),
        )
        assert reclaimed is not None
        assert reclaimed.run.id == run_id
        store.append_events(
            second_attempt,
            (
                StoredExecutionEvent(
                    second_attempt,
                    0,
                    "cell.succeeded",
                    "cell-3",
                    Instant("2099-01-01T00:00:03.100000Z"),
                ),
            ),
            owner="worker-http-events-2",
            lease_token=second_lease,
            now=Instant("2099-01-01T00:00:03.500000Z"),
        )

        events_one = first.events(limit=2)
        assert [item.sequence for item in events_one.items] == [0, 1]
        assert [item.attempt_id for item in events_one.items] == [
            str(first_attempt),
            str(first_attempt),
        ]
        assert [item.attempt_sequence for item in events_one.items] == [0, 1]
        events_two = first.events(since=events_one.next_since, limit=2)
        assert [item.sequence for item in events_two.items] == [2]
        assert events_two.items[0].attempt_id == str(second_attempt)
        assert events_two.items[0].attempt_sequence == 0

        second = client.submit(
            project="examples/demo",
            target="notebooks/etl",
            parameters={"limit": 8},
            idempotency_key="acceptance-k2",
        )

        assert first.status() is SDKJobState.RUNNING
        stored = store.get_job(JobId(first.id))
        assert stored is not None
        assert stored.target == "notebooks/etl"
        assert json.loads(stored.parameters_json) == {"limit": 7}

        first_page = client.list_jobs(project="examples/demo", limit=1)
        assert len(first_page.items) == 1
        assert first_page.next_cursor is not None
        second_page = client.list_jobs(
            project="examples/demo",
            limit=1,
            cursor=first_page.next_cursor,
        )
        assert len(second_page.items) == 1
        assert {first_page.items[0].id, second_page.items[0].id} == {first.id, second.id}

        replay = client.submit(
            project="examples/demo",
            target="notebooks/etl",
            parameters={"limit": 7},
            idempotency_key="acceptance-k1",
        )
        assert replay.id == first.id

        cancelled = second.cancel()
        assert cancelled.id == second.id
        assert cancelled.state is SDKJobState.CANCELLED
        assert second.status() is SDKJobState.CANCELLED

        with pytest.raises(APIError) as cross_run_since:
            second.events(since=events_one.next_since)
        assert cross_run_since.value.status_code == 400
        assert cross_run_since.value.code == "invalid_request"

        with pytest.raises(APIError) as conflict:
            client.submit(
                project="examples/demo",
                target="notebooks/other",
                parameters={"limit": 7},
                idempotency_key="acceptance-k1",
            )
        assert conflict.value.status_code == 409
        assert conflict.value.code == "idempotency_conflict"

        with pytest.raises(APIError) as invalid:
            transport.request(
                "POST",
                "/v1/jobs",
                payload={"project": "", "target": "notebooks/etl"},
            )
        assert invalid.value.status_code == 400
        assert invalid.value.code == "invalid_request"

        with pytest.raises(APIError) as bad_list:
            transport.request("GET", "/v1/jobs", query={"limit": "0"})
        assert bad_list.value.status_code == 400
        assert bad_list.value.code == "invalid_request"

        with pytest.raises(APIError) as bad_events:
            transport.request("GET", f"/v1/jobs/{first.id}/events", query={"limit": "0"})
        assert bad_events.value.status_code == 400
        assert bad_events.value.code == "invalid_request"

        with pytest.raises(APIError) as missing:
            client.get_job("job-does-not-exist")
        assert missing.value.status_code == 404
        assert missing.value.code == "job_not_found"

        with pytest.raises(APIError) as missing_events:
            client.get_events("job-does-not-exist")
        assert missing_events.value.status_code == 404
        assert missing_events.value.code == "job_not_found"

        with pytest.raises(APIError) as missing_cancel:
            transport.request("POST", "/v1/jobs/job-does-not-exist/cancel")
        assert missing_cancel.value.status_code == 404
        assert missing_cancel.value.code == "job_not_found"

        with pytest.raises(APIError) as route_missing:
            transport.request("GET", "/v1/unknown")
        assert route_missing.value.status_code == 404
        assert route_missing.value.code == "not_found"
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5.0)
        assert not server_thread.is_alive()


def test_http_server_rejects_invalid_static_token(tmp_path: Path) -> None:
    store = SqliteJobStore(tmp_path / "ronin.db", migration_now=_MIGRATION_NOW)
    service = DurableExecutionService(store)
    invalid = "".join((" bad", "-credential"))
    with pytest.raises(ValueError, match="token must be non-empty"):
        RoninHTTPServer(("127.0.0.1", 0), service, token=invalid)
