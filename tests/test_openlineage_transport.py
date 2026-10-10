import pytest
from studio_core import (
    OpenLineageTransport,
    OpenLineageTransportError,
    validate_openlineage_event,
)
from studio_server.openlineage_http import HttpOpenLineageSink


class Sink:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.events: list[dict[str, object]] = []

    def publish(self, event: dict[str, object]) -> None:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("temporary")
        self.events.append(event)


EVENT = {
    "eventType": "COMPLETE",
    "eventTime": "2026-09-21T00:00:00Z",
    "run": {"runId": "run-1"},
    "job": {"namespace": "ns", "name": "job"},
    "producer": "ronin",
}


def test_transport_retries_and_deduplicates() -> None:
    sink = Sink(2)
    transport = OpenLineageTransport(sink, max_attempts=3)
    first = transport.publish(EVENT)
    second = transport.publish(EVENT)
    assert first.attempts == 3
    assert not first.deduplicated
    assert second.deduplicated
    assert second.attempts == 0
    assert len(sink.events) == 1


def test_transport_fails_after_bounded_attempts() -> None:
    with pytest.raises(OpenLineageTransportError):
        OpenLineageTransport(Sink(3), max_attempts=2).publish(EVENT)


def test_schema_validator_rejects_incompatible_events() -> None:
    with pytest.raises(ValueError, match="producer"):
        validate_openlineage_event({**EVENT, "producer": "other"})
    with pytest.raises(ValueError, match="run.runId"):
        validate_openlineage_event({**EVENT, "run": {}})
    with pytest.raises(ValueError, match="schemaVersion"):
        validate_openlineage_event({**EVENT, "schemaVersion": "2.0"})


def test_schema_validator_accepts_supported_explicit_version() -> None:
    validate_openlineage_event({**EVENT, "schemaVersion": "1.0"})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("eventType", None, "required fields"),
        ("eventTime", None, "required fields"),
        ("run", None, "required fields"),
        ("job", None, "required fields"),
        ("producer", None, "required fields"),
    ],
)
def test_schema_validator_requires_every_top_level_contract_field(
    field: str, value: object, message: str
) -> None:
    del value
    event = dict(EVENT)
    event.pop(field)
    with pytest.raises(ValueError, match=message):
        validate_openlineage_event(event)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("eventType", "UNKNOWN", "event type"),
        ("eventTime", "2026-09-21T00:00:00+00:00", "eventTime"),
        ("eventTime", 123, "eventTime"),
        ("run", [], "run and job"),
        ("job", [], "run and job"),
        ("run", {"runId": ""}, "run.runId"),
        ("run", {"runId": 123}, "run.runId"),
        ("job", {"namespace": "", "name": "job"}, "namespace and name"),
        ("job", {"namespace": "ns", "name": ""}, "namespace and name"),
        ("job", {"namespace": "ns", "name": 123}, "namespace and name"),
    ],
)
def test_schema_validator_rejects_invalid_event_shapes(
    field: str, value: object, message: str
) -> None:
    event = dict(EVENT)
    event[field] = value
    with pytest.raises(ValueError, match=message):
        validate_openlineage_event(event)


def test_transport_rejects_invalid_attempt_bounds() -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        OpenLineageTransport(Sink(), max_attempts=0)
    with pytest.raises(ValueError, match="between 1 and 10"):
        OpenLineageTransport(Sink(), max_attempts=11)


def test_transport_preserves_last_sink_error_as_cause() -> None:
    transport = OpenLineageTransport(Sink(2), max_attempts=2)
    with pytest.raises(OpenLineageTransportError) as raised:
        transport.publish(EVENT)
    assert isinstance(raised.value.__cause__, RuntimeError)


def test_http_sink_posts_canonical_json_with_bounded_configuration() -> None:
    calls = []

    class Response:
        status = 202

    def opener(request, *, timeout):
        calls.append((request, timeout))
        return Response()

    HttpOpenLineageSink("http://127.0.0.1:8080/events", timeout_seconds=2, opener=opener).publish(
        EVENT
    )
    assert calls[0][1] == 2
    assert calls[0][0].get_method() == "POST"
    assert calls[0][0].get_header("Content-type") == "application/json"
    assert calls[0][0].get_header("X-ronin-event-digest")
    assert calls[0][0].data == (
        b'{"eventTime":"2026-09-21T00:00:00Z","eventType":"COMPLETE",'
        b'"job":{"name":"job","namespace":"ns"},"producer":"ronin",'
        b'"run":{"runId":"run-1"}}'
    )


def test_http_sink_rejects_insecure_remote_endpoint_and_sanitizes_failure() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        HttpOpenLineageSink("http://example.test/events")

    def failing_opener(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("authorization token leaked")

    with pytest.raises(OpenLineageTransportError, match="request failed"):
        HttpOpenLineageSink("https://lineage.example.test/events", opener=failing_opener).publish(
            EVENT
        )
