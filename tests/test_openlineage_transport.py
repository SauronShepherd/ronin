from urllib.request import Request

import pytest
from studio_core import (
    MAX_OPENLINEAGE_EVENT_BYTES,
    OpenLineageTransport,
    OpenLineageTransportError,
    validate_openlineage_event,
)
from studio_core.openlineage import (
    OPENLINEAGE_COLUMN_LINEAGE_SCHEMA,
    OPENLINEAGE_LINEAGE_FACET_SCHEMA,
)
from studio_server.openlineage_http import HttpOpenLineageSink, _RejectRedirects


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
    "producer": "https://github.com/SauronShepherd/ronin",
    "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent",
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
        validate_openlineage_event({**EVENT, "producer": "not a uri"})
    with pytest.raises(ValueError, match="run.runId"):
        validate_openlineage_event({**EVENT, "run": {}})
    with pytest.raises(ValueError, match="schemaVersion"):
        validate_openlineage_event({**EVENT, "schemaVersion": "2.0"})


def test_schema_validator_accepts_supported_explicit_version() -> None:
    validate_openlineage_event({**EVENT, "schemaVersion": "1.0"})


@pytest.mark.parametrize(
    ("event", "message"),
    [
        (
            {
                **EVENT,
                "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/DatasetEvent",
            },
            "RunEvent",
        ),
        (
            {
                "eventTime": "2026-09-21T00:00:00Z",
                "dataset": {"namespace": "ns", "name": "output"},
                "producer": "https://github.com/SauronShepherd/ronin",
                "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent",
            },
            "DatasetEvent",
        ),
    ],
)
def test_schema_validator_rejects_schema_urls_for_the_wrong_event_kind(
    event: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_openlineage_event(event)


@pytest.mark.parametrize(
    "event",
    [
        {
            **EVENT,
            "dataset": {"namespace": "ns", "name": "output"},
        },
        {
            "eventTime": "2026-09-21T00:00:00Z",
            "dataset": {"namespace": "ns", "name": "output"},
            "producer": "https://github.com/SauronShepherd/ronin",
            "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/DatasetEvent",
            "run": {"runId": "run-1"},
        },
    ],
)
def test_schema_validator_rejects_mixed_run_and_dataset_event_shapes(
    event: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="payload cannot contain"):
        validate_openlineage_event(event)


def test_schema_validator_accepts_iso8601_offsets_and_requires_valid_run_event_uri() -> None:
    validate_openlineage_event({**EVENT, "eventTime": "2026-09-21T02:00:00+02:00"})
    for field in ("producer", "schemaURL"):
        with pytest.raises(ValueError, match="absolute URI"):
            validate_openlineage_event({**EVENT, field: "relative/path"})


@pytest.mark.parametrize("event_type", ["START", "RUNNING", "COMPLETE", "ABORT", "FAIL", "OTHER"])
def test_schema_validator_accepts_every_supported_event_type(event_type: str) -> None:
    validate_openlineage_event({**EVENT, "eventType": event_type})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("eventType", None, "required fields"),
        ("eventTime", None, "required fields"),
        ("run", None, "required fields"),
        ("job", None, "required fields"),
        ("producer", None, "required fields"),
        ("schemaURL", None, "required fields"),
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
        ("eventTime", "not-a-timestampZ", "eventTime"),
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


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("eventTime", "", "eventTime"),
        ("eventTime", "not-a-timestamp", "eventTime"),
        ("run", {"runId": "  "}, "run.runId"),
        ("job", {"namespace": "ns", "name": "  "}, "namespace and name"),
    ],
)
def test_schema_validator_rejects_empty_required_values(
    field: str, value: object, message: str
) -> None:
    event = dict(EVENT)
    event[field] = value
    with pytest.raises(ValueError, match=message):
        validate_openlineage_event(event)


def test_transport_digest_is_canonical_and_invalid_events_are_not_published() -> None:
    sink = Sink()
    transport = OpenLineageTransport(sink)
    reordered = {
        "producer": "https://github.com/SauronShepherd/ronin",
        "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent",
        "job": {"name": "job", "namespace": "ns"},
        "run": {"runId": "run-1"},
        "eventTime": "2026-09-21T00:00:00Z",
        "eventType": "COMPLETE",
    }
    first = transport.publish(EVENT)
    second = transport.publish(reordered)
    assert first.event_digest == second.event_digest
    assert second.deduplicated
    assert len(sink.events) == 1
    with pytest.raises(ValueError, match="producer"):
        transport.publish({**EVENT, "producer": "not a uri"})
    assert len(sink.events) == 1


def test_http_sink_posts_canonical_json_with_bounded_configuration() -> None:
    calls = []

    class Response:
        status = 202
        closed = False

        def close(self) -> None:
            self.closed = True

    response = Response()

    def opener(request, *, timeout):
        calls.append((request, timeout))
        return response

    HttpOpenLineageSink("http://127.0.0.1:8080/events", timeout_seconds=2, opener=opener).publish(
        EVENT
    )
    assert calls[0][1] == 2
    assert response.closed
    assert calls[0][0].get_method() == "POST"
    assert calls[0][0].get_header("Content-type") == "application/json"
    assert calls[0][0].get_header("X-ronin-event-digest")
    assert calls[0][0].data == (
        b'{"eventTime":"2026-09-21T00:00:00Z","eventType":"COMPLETE",'
        b'"job":{"name":"job","namespace":"ns"},'
        b'"producer":"https://github.com/SauronShepherd/ronin",'
        b'"run":{"runId":"run-1"},'
        b'"schemaURL":"https://openlineage.io/spec/1-0-5/OpenLineage.json#'
        b'/definitions/RunEvent"}'
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


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:secret@lineage.example.test/events",
        "https://lineage.example.test/events#fragment",
        "https://lineage.example.test:99999/events",
        "https://[invalid/events",
    ],
)
def test_http_sink_rejects_ambiguous_or_credential_bearing_urls(endpoint: str) -> None:
    with pytest.raises(ValueError, match="endpoint"):
        HttpOpenLineageSink(endpoint)


def test_http_sink_does_not_follow_redirects() -> None:
    handler = _RejectRedirects()
    request = Request("https://lineage.example.test/events")
    assert handler.redirect_request(request, None, 302, "Found", {}, "https://other.test") is None


@pytest.mark.parametrize("timeout", [True, False, 0, -1, 61, float("inf"), 10**100])
def test_http_sink_rejects_invalid_timeout_bounds(timeout: object) -> None:
    with pytest.raises(ValueError, match="timeout"):
        HttpOpenLineageSink("https://lineage.example.test/events", timeout_seconds=timeout)


def test_openlineage_event_payload_has_a_hard_byte_limit() -> None:
    event = {**EVENT, "extension": "x" * MAX_OPENLINEAGE_EVENT_BYTES}
    with pytest.raises(ValueError, match="1048576-byte limit"):
        validate_openlineage_event(event)


def test_openlineage_facets_require_schema_and_producer_metadata() -> None:
    event = {
        **EVENT,
        "outputs": [
            {
                "namespace": "ns",
                "name": "output",
                "facets": {"columnLineage": {"fields": {}}},
            }
        ],
    }
    with pytest.raises(ValueError, match="facet producer and schemaURL"):
        validate_openlineage_event(event)


@pytest.mark.parametrize(
    ("facet_name", "schema_url"),
    [
        (
            "columnLineage",
            "https://openlineage.io/spec/facets/1-0-0/LineageFacet.json#/$defs/LineageDatasetFacet",
        ),
        (
            "lineage",
            "https://openlineage.io/spec/facets/1-2-0/ColumnLineageDatasetFacet.json",
        ),
    ],
)
def test_openlineage_known_facet_names_require_their_schema_url(
    facet_name: str, schema_url: str
) -> None:
    facet: dict[str, object]
    if facet_name == "columnLineage":
        facet = {
            "_producer": "https://github.com/SauronShepherd/ronin",
            "_schemaURL": schema_url,
            "fields": {
                "target": {
                    "inputFields": [{"namespace": "ns", "name": "source", "field": "origin"}]
                }
            },
        }
    else:
        facet = {
            "_producer": "https://github.com/SauronShepherd/ronin",
            "_schemaURL": schema_url,
            "inputs": [{"namespace": "ns", "name": "source", "type": "DATASET"}],
        }
    event = {
        **EVENT,
        "outputs": [{"namespace": "ns", "name": "output", "facets": {facet_name: facet}}],
    }

    with pytest.raises(ValueError, match=f"{facet_name} facet schemaURL is unsupported"):
        validate_openlineage_event(event)


@pytest.mark.parametrize(
    ("entity_name", "facet_name", "schema_url", "facet_data"),
    [
        (
            "run",
            "lineage",
            OPENLINEAGE_LINEAGE_FACET_SCHEMA,
            {"inputs": [{"namespace": "ns", "name": "source", "type": "DATASET"}]},
        ),
        (
            "job",
            "columnLineage",
            OPENLINEAGE_COLUMN_LINEAGE_SCHEMA,
            {
                "fields": {
                    "target": {
                        "inputFields": [{"namespace": "ns", "name": "source", "field": "origin"}]
                    }
                }
            },
        ),
    ],
)
def test_dataset_lineage_facets_are_rejected_on_run_and_job_entities(
    entity_name: str,
    facet_name: str,
    schema_url: str,
    facet_data: dict[str, object],
) -> None:
    event = dict(EVENT)
    event[entity_name] = {
        **event[entity_name],
        "facets": {
            facet_name: {
                "_producer": "https://github.com/SauronShepherd/ronin",
                "_schemaURL": schema_url,
                **facet_data,
            }
        },
    }

    with pytest.raises(ValueError, match="facet is only supported on datasets"):
        validate_openlineage_event(event)


def test_openlineage_validation_messages_are_stable() -> None:
    cases = (
        ({**EVENT, "producer": "not a uri"}, "OpenLineage producer must be an absolute URI"),
        ({**EVENT, "schemaVersion": "2.0"}, "OpenLineage schemaVersion is unsupported"),
        ({**EVENT, "eventType": "UNKNOWN"}, "OpenLineage event type is unsupported"),
        (
            {**EVENT, "eventTime": "not-a-timestampZ"},
            "OpenLineage eventTime must be a timezone-aware ISO 8601 timestamp",
        ),
        ({**EVENT, "run": []}, "OpenLineage run and job must be objects"),
        ({**EVENT, "run": {}}, "OpenLineage run.runId is required"),
        (
            {**EVENT, "job": {"namespace": "", "name": "job"}},
            "OpenLineage job namespace and name are required",
        ),
    )
    for event, message in cases:
        with pytest.raises(ValueError, match=".") as error:
            validate_openlineage_event(event)
        assert str(error.value) == message


def test_transport_attempt_bounds_are_inclusive_and_message_is_stable() -> None:
    assert OpenLineageTransport(Sink(), max_attempts=1).publish(EVENT).attempts == 1
    assert OpenLineageTransport(Sink(), max_attempts=10).publish(EVENT).attempts == 1
    for value in (0, 11):
        with pytest.raises(ValueError, match=".") as error:
            OpenLineageTransport(Sink(), max_attempts=value)
        assert str(error.value) == "max_attempts must be between 1 and 10"


def test_transport_deduplication_cache_is_bounded_and_evicts_oldest_entries() -> None:
    sink = Sink()
    transport = OpenLineageTransport(sink, max_deduplication_entries=1)
    first = transport.publish(EVENT)
    second = transport.publish({**EVENT, "eventType": "START"})

    assert first.deduplicated is False
    assert second.deduplicated is False
    assert transport.publish({**EVENT, "eventType": "START"}).deduplicated is True
    evicted = transport.publish(EVENT)
    assert evicted.deduplicated is False
    assert evicted.attempts == 1
    assert len(sink.events) == 3


@pytest.mark.parametrize("value", [True, False, 0, -1, 100_001, 1.5, "2", None])
def test_transport_rejects_invalid_deduplication_cache_bounds(value: object) -> None:
    with pytest.raises(ValueError, match="max_deduplication_entries"):
        OpenLineageTransport(Sink(), max_deduplication_entries=value)  # type: ignore[arg-type]


def test_transport_deduplicates_only_after_successful_publish() -> None:
    sink = Sink(1)
    transport = OpenLineageTransport(sink, max_attempts=1)
    with pytest.raises(OpenLineageTransportError):
        transport.publish(EVENT)
    sink.failures = 0
    receipt = transport.publish(EVENT)
    assert receipt.deduplicated is False
    assert receipt.attempts == 1
    assert len(sink.events) == 1
    assert transport.publish(EVENT).deduplicated is True


def test_transport_receipt_is_stable_and_digest_changes_with_event_content() -> None:
    first_sink = Sink()
    second_sink = Sink()
    first = OpenLineageTransport(first_sink).publish(EVENT)
    changed = OpenLineageTransport(second_sink).publish({**EVENT, "eventType": "START"})

    assert first.attempts == 1
    assert first.deduplicated is False
    assert len(first.event_digest) == 64
    assert first.event_digest != changed.event_digest
    assert first_sink.events == [EVENT]
    assert second_sink.events == [{**EVENT, "eventType": "START"}]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "eventTime",
            "2026-09-21T00:00:00",
            "OpenLineage eventTime must be a timezone-aware ISO 8601 timestamp",
        ),
        ("run", [], "OpenLineage run and job must be objects"),
        ("job", [], "OpenLineage run and job must be objects"),
        ("run", {"runId": "  "}, "OpenLineage run.runId is required"),
        (
            "job",
            {"namespace": "ns", "name": "  "},
            "OpenLineage job namespace and name are required",
        ),
    ],
)
def test_openlineage_invalid_shape_messages_are_exact(
    field: str, value: object, message: str
) -> None:
    event = dict(EVENT)
    event[field] = value
    with pytest.raises(ValueError, match=".") as error:
        validate_openlineage_event(event)
    assert str(error.value) == message
