import pytest
from studio_query_engine import (
    QUERY_ENGINE_NAMESPACE,
    QUERY_ENGINE_VERSION,
    CancellationResult,
    EngineCapabilities,
    EngineHandshake,
    QueryEvidence,
    QueryEngineTransport,
    QueryRequest,
    QueryResultPage,
    QueryStatus,
)


def test_provider_neutral_transport_port_is_runtime_checkable_by_shape() -> None:
    class Transport:
        def submit(self, request):
            return None

        def poll(self, handle, next_uri):
            return None

        def cancel(self, handle):
            return None

    # Protocols are intentionally structural; this assertion keeps the
    # contract independent of any provider implementation or import.
    assert QueryEngineTransport is not None
    assert all(hasattr(Transport, method) for method in ("submit", "poll", "cancel"))


def test_query_engine_contract_is_provider_neutral_and_canonical() -> None:
    capabilities = EngineCapabilities((("cancel", True), ("joins", None)))
    handshake = EngineHandshake("local-duckdb", "1.2", capabilities, True)
    request = QueryRequest("SELECT 1", "local", "best_effort", max_rows=5)

    assert capabilities.get("joins") is None
    assert handshake.to_payload()["provider_id"] == "local-duckdb"
    assert handshake.to_payload()["contract"] == f"{QUERY_ENGINE_NAMESPACE}/{QUERY_ENGINE_VERSION}"
    assert request.canonical_json().startswith('{"max_rows":5')


def test_query_result_and_status_are_bounded_and_shape_checked() -> None:
    result = QueryResultPage(("id", "name"), ((1, "one"),), "page-2")
    assert result.next_page_token == "page-2"  # noqa: S105 - pagination token fixture
    assert QueryStatus("running").state == "running"
    assert CancellationResult(True, "cancelled").cancelled

    with pytest.raises(ValueError, match="row width"):
        QueryResultPage(("id",), ((1, "extra"),))
    with pytest.raises(ValueError, match="max_rows"):
        QueryRequest("SELECT 1", "local", max_rows=0)
    with pytest.raises(ValueError, match="integer"):
        QueryRequest("SELECT 1", "local", max_rows=True)


def test_query_evidence_rejects_duplicate_timings() -> None:
    with pytest.raises(ValueError, match="timings"):
        QueryEvidence("a" * 64, "provider", None, None, (("queue", 1), ("queue", 2)))


def test_query_evidence_rejects_boolean_numeric_evidence() -> None:
    with pytest.raises(ValueError, match="timings"):
        QueryEvidence("a" * 64, "provider", None, None, (("queue", True),))
    with pytest.raises(ValueError, match="engine_stats"):
        QueryEvidence("a" * 64, "provider", None, None, engine_stats=(("rows", False),))


@pytest.mark.parametrize("digest", ["digest", "A" * 64, "0" * 63])
def test_query_evidence_rejects_non_sha256_digests(digest: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        QueryEvidence(digest, "provider", None, None)
