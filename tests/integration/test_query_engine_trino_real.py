from __future__ import annotations

import json
import os
from collections.abc import Mapping
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from studio_data_engineering import QueryEngineRuntimeProvider, execute_query
from studio_query_engine import QueryRequest, TrinoHttpTransport
from studio_query_engine import (
    DiscoveredEngine,
    EngineCapabilities,
    EngineHandshake,
    QueryExecutionPolicy,
)
from studio_storage import LocalArtifactStore

_TRINO_URL = os.environ.get("RONIN_TRINO_TEST_URL")
pytestmark = pytest.mark.skipif(
    not _TRINO_URL,
    reason="real Trino query binding qualification requires RONIN_TRINO_TEST_URL",
)


class _LocalTrinoHttpClient:
    def request(self, method: str, url: str, *, body: str | None = None) -> Mapping[str, object]:
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("real Trino test client only accepts loopback HTTP")
        connection = HTTPConnection(parsed.hostname, parsed.port or 80, timeout=15)
        try:
            connection.request(
                method,
                parsed.path + (f"?{parsed.query}" if parsed.query else ""),
                body=body,
                headers={"X-Trino-User": "ronin-qualification"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read())
            if response.status != 200:
                raise RuntimeError(f"Trino returned HTTP {response.status}: {payload}")
        finally:
            connection.close()
        if not isinstance(payload, Mapping):
            raise AssertionError("Trino response must be a JSON object")
        return payload


def test_trino_real_prepared_scalar_bindings() -> None:
    assert _TRINO_URL is not None
    parsed = urlsplit(_TRINO_URL)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("real Trino qualification URL must use local loopback HTTP")
    base_url = _TRINO_URL if _TRINO_URL.endswith("/") else f"{_TRINO_URL}/"
    transport = TrinoHttpTransport(_LocalTrinoHttpClient(), base_url=base_url)
    request = QueryRequest(
        "SELECT CAST(? AS VARCHAR), CAST(? AS BIGINT), CAST(? AS BOOLEAN), "
        "CAST(? AS DOUBLE), COALESCE(CAST(? AS VARCHAR), CAST(NULL AS VARCHAR))",
        "trino-qualification",
        parameters=("O'Reilly", 2**63 - 1, True, 2.5, None),
    )
    handle, next_uri = transport.submit(request)
    pages = []

    for _ in range(100):
        status, page, following = transport.poll(handle, next_uri)
        if page is not None:
            pages.append(page)
        if status.state in {"succeeded", "failed", "cancelled"}:
            break
        assert following is not None
        next_uri = following
    else:
        transport.cancel(handle)
        pytest.fail("Trino query did not reach a terminal state within 100 polls")

    assert status.state == "succeeded", status.message
    assert pages
    assert all(page.columns == pages[0].columns for page in pages)
    assert tuple(row for page in pages for row in page.rows) == (
        ("O'Reilly", 2**63 - 1, True, 2.5, None),
    )


def test_trino_real_result_byte_budget_accepts_exact_limit_and_rejects_one_byte_less(
    tmp_path: Path,
) -> None:
    assert _TRINO_URL is not None
    base_url = _TRINO_URL if _TRINO_URL.endswith("/") else f"{_TRINO_URL}/"
    transport = TrinoHttpTransport(_LocalTrinoHttpClient(), base_url=base_url)
    provider = QueryEngineRuntimeProvider(
        DiscoveredEngine(
            EngineHandshake(
                "trino",
                "484",
                EngineCapabilities((("cancel", True), ("parameter_binding", True))),
                True,
            ),
            ("trino",),
            "ready",
        ),
        QueryExecutionPolicy((("trino", ("trino",)),), required_capability="cancel"),
    )
    expected = {"columns": ["_col0"], "rows": [["ok"]], "row_count": 1}
    exact_limit = len(json.dumps(expected, separators=(",", ":")).encode("utf-8"))

    accepted = execute_query(
        provider,
        transport,
        LocalArtifactStore(tmp_path / "accepted-artifacts"),
        QueryRequest(
            "SELECT CAST(? AS VARCHAR)",
            "trino",
            parameters=("ok",),
            max_result_bytes=exact_limit,
        ),
        engine="trino",
        project_id="qualification-project",
        run_id="result-budget-accepted",
        attempt_id="attempt-1",
    )
    rejected = execute_query(
        provider,
        transport,
        LocalArtifactStore(tmp_path / "rejected-artifacts"),
        QueryRequest(
            "SELECT CAST(? AS VARCHAR)",
            "trino",
            parameters=("ok",),
            max_result_bytes=exact_limit - 1,
        ),
        engine="trino",
        project_id="qualification-project",
        run_id="result-budget-rejected",
        attempt_id="attempt-1",
    )

    assert accepted.status.state == "succeeded"
    assert accepted.page is not None
    assert accepted.page.rows == (("ok",),)
    assert rejected.status.state == "failed"
    assert rejected.status.message == "query result exceeds the configured byte limit"
    assert rejected.page is None
