import pytest
from studio_query_engine import QueryFailure, QueryRequest, TrinoHttpTransport


class _Client:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, str | None]] = []

    def request(self, method: str, url: str, *, body: str | None = None) -> dict[str, object]:
        self.calls.append((method, url, body))
        return self.responses.pop(0)


def test_trino_transport_submits_polls_pages_and_cancels() -> None:
    client = _Client(
        [
            {"id": "q-1", "nextUri": "http://engine/q-1/1"},
            {"columns": [{"name": "id"}], "data": [[1]], "nextUri": "http://engine/q-1/2"},
            {"columns": [{"name": "id"}], "data": [[2]]},
            {"cancelled": True},
        ]
    )
    transport = TrinoHttpTransport(client, base_url="http://engine/")
    handle, next_uri = transport.submit(QueryRequest("SELECT 1", "trino"))
    status, page, next_uri = transport.poll(handle, next_uri)
    final_status, final_page, _ = transport.poll(handle, next_uri)
    cancellation = transport.cancel(handle)

    assert status.state == "running"
    assert page is not None
    assert page.rows == ((1,),)
    assert final_status.state == "succeeded"
    assert final_page is not None
    assert final_page.rows == ((2,),)
    assert cancellation.cancelled
    assert client.calls[0][0:2] == ("POST", "http://engine/v1/statement")


def test_trino_transport_normalizes_provider_errors_and_provider_mismatch() -> None:
    client = _Client(
        [{"id": "q-1", "nextUri": "http://engine/q-1"}, {"error": {"message": "bad sql"}}]
    )
    transport = TrinoHttpTransport(client, base_url="http://engine/")
    handle, uri = transport.submit(QueryRequest("BAD", "trino"))
    status, page, next_uri = transport.poll(handle, uri)
    assert status.state == "failed"
    assert status.message == "bad sql"
    assert page is None
    assert next_uri is None

    with pytest.raises(QueryFailure, match="another provider"):
        transport.poll(handle.__class__(handle.query_id, "other", handle.provider_query_id), uri)


def test_trino_transport_enforces_request_row_bound() -> None:
    client = _Client(
        [
            {"id": "q-1", "nextUri": "http://engine/q-1"},
            {"columns": [{"name": "id"}], "data": [[1], [2]]},
        ]
    )
    transport = TrinoHttpTransport(client, base_url="http://engine/")
    handle, uri = transport.submit(QueryRequest("SELECT 1", "trino", max_rows=1))
    with pytest.raises(QueryFailure, match="too many rows"):
        transport.poll(handle, uri)


@pytest.mark.parametrize("unsafe_uri", ["http://other/q-1", "http://user:pass@engine/q-1"])
def test_trino_transport_rejects_provider_uri_escape(unsafe_uri: str) -> None:
    client = _Client([{"id": "q-1", "nextUri": unsafe_uri}])
    transport = TrinoHttpTransport(client, base_url="http://engine/")
    with pytest.raises(QueryFailure, match="safe HTTP URI|escaped"):
        transport.submit(QueryRequest("SELECT 1", "trino"))


@pytest.mark.parametrize("base_url", ["engine/", "ftp://engine/", "http://user:pass@engine/"])
def test_trino_transport_rejects_unsafe_base_url(base_url: str) -> None:
    with pytest.raises(ValueError, match="URL|credentials"):
        TrinoHttpTransport(_Client([]), base_url=base_url)
