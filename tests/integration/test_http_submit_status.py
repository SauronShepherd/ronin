from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

import pytest
from pyronin import APIError, HTTPTransport, Ronin
from pyronin import JobState as SDKJobState
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant, JobId
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


def test_real_http_sqlite_and_pyronin_submit_status_idempotency(tmp_path: Path) -> None:
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
        handle = client.submit(
            project="examples/demo",
            target="notebooks/etl",
            parameters={"limit": 7},
            idempotency_key="acceptance-k1",
        )

        assert handle.status() is SDKJobState.QUEUED
        stored = store.get_job(JobId(handle.id))
        assert stored is not None
        assert stored.target == "notebooks/etl"
        assert json.loads(stored.parameters_json) == {"limit": 7}

        replay = client.submit(
            project="examples/demo",
            target="notebooks/etl",
            parameters={"limit": 7},
            idempotency_key="acceptance-k1",
        )
        assert replay.id == handle.id

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

        with pytest.raises(APIError) as unknown_field:
            transport.request(
                "POST",
                "/v1/jobs",
                payload={
                    "project": "examples/demo",
                    "target": "notebooks/etl",
                    "unexpected": True,
                },
            )
        assert unknown_field.value.status_code == 400
        assert unknown_field.value.code == "invalid_request"

        with pytest.raises(APIError) as missing:
            client.get_job("job-does-not-exist")
        assert missing.value.status_code == 404
        assert missing.value.code == "job_not_found"

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
