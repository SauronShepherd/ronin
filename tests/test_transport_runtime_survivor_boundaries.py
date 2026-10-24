from __future__ import annotations

import pytest
from studio_core import (
    CapabilityRequirement,
    ExecutionProfile,
    OpenLineageTransport,
    RuntimeCapability,
    RuntimeCatalog,
    RuntimeProfile,
    RuntimeProfileRef,
    resolve_runtime,
    validate_openlineage_event,
)

EVENT = {
    "eventType": "COMPLETE",
    "eventTime": "2026-09-21T00:00:00Z",
    "run": {"runId": "run-1"},
    "job": {"namespace": "ns", "name": "job"},
    "producer": "https://github.com/SauronShepherd/ronin",
    "schemaURL": "https://openlineage.io/spec/1-0-5/OpenLineage.json#/definitions/RunEvent",
}


class _Sink:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.events: list[object] = []

    def publish(self, event) -> None:
        if self.failures:
            self.failures -= 1
            raise RuntimeError("transient")
        self.events.append(event)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("producer", "", "producer"),
        ("producer", " ronin ", "producer"),
        ("schemaVersion", None, "schemaVersion"),
        ("eventTime", "2026-09-21T00:00:00", "eventTime"),
        ("run", {"runId": "\t"}, "run.runId"),
        ("job", {"namespace": "ns", "name": "\t"}, "namespace and name"),
    ],
)
def test_openlineage_validation_rejects_boundary_values(
    field: str, value: object, message: str
) -> None:
    event = dict(EVENT)
    event[field] = value
    with pytest.raises(ValueError, match=message):
        validate_openlineage_event(event)


@pytest.mark.parametrize("event", [None, [], "event"])
def test_openlineage_validation_rejects_non_object_payloads(event: object) -> None:
    with pytest.raises(ValueError, match="event must be an object"):
        validate_openlineage_event(event)  # type: ignore[arg-type]


def test_openlineage_validation_allows_extra_fields_and_omitted_schema_version() -> None:
    validate_openlineage_event({**EVENT, "custom": {"value": True}})


def test_openlineage_transport_retries_until_success_and_only_deduplicates_after_success() -> None:
    sink = _Sink(failures=2)
    transport = OpenLineageTransport(sink, max_attempts=3)
    receipt = transport.publish(EVENT)
    assert receipt.attempts == 3
    assert receipt.deduplicated is False
    assert transport.publish(EVENT).deduplicated is True
    assert len(sink.events) == 1


def test_openlineage_transport_does_not_publish_invalid_events() -> None:
    sink = _Sink()
    with pytest.raises(ValueError, match="producer"):
        OpenLineageTransport(sink).publish({**EVENT, "producer": "other"})
    assert sink.events == []


@pytest.mark.parametrize("max_attempts", [True, False, 1.5, "3", None])
def test_openlineage_transport_requires_integer_attempt_bounds(
    max_attempts: object,
) -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        OpenLineageTransport(_Sink(), max_attempts=max_attempts)  # type: ignore[arg-type]


def _profile(
    adapter: str,
    name: str,
    *capabilities: RuntimeCapability,
    available: bool = True,
) -> RuntimeProfile:
    return RuntimeProfile(RuntimeProfileRef(adapter, name), capabilities, available)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("", "runtime capability namespace"),
        (" leading", "runtime capability namespace"),
        ("trailing ", "runtime capability namespace"),
        ("line\nfeed", "runtime capability namespace"),
        ("line\rfeed", "runtime capability namespace"),
    ],
)
def test_runtime_capability_namespace_text_is_fail_closed(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RuntimeCapability("engine", namespace=value)


def test_runtime_catalog_lookup_uses_bisect_boundaries() -> None:
    first = _profile("a", "first")
    last = _profile("z", "last")
    catalog = RuntimeCatalog((last, first))
    assert catalog.get(first.ref) is first
    assert catalog.get(last.ref) is last
    assert catalog.get(RuntimeProfileRef("a", "before")) is None
    assert catalog.get(RuntimeProfileRef("z", "after")) is None


@pytest.mark.parametrize(
    ("resolution", "expected_status", "expected_selected"),
    [
        ("strict", "no_match", None),
        ("compatible", "selected", "fallback"),
    ],
)
def test_requested_incompatible_profile_obeys_resolution_policy(
    resolution: str, expected_status: str, expected_selected: str | None
) -> None:
    requested = _profile("adapter", "requested", RuntimeCapability("engine", "old"))
    fallback = _profile("adapter", "fallback", RuntimeCapability("engine", "new"))
    result = resolve_runtime(
        ExecutionProfile(
            runtime=requested.ref,
            requirements=(CapabilityRequirement("engine", "new"),),
            resolution=resolution,  # type: ignore[arg-type]
        ),
        RuntimeCatalog((requested, fallback)),
    )
    assert result.status == expected_status
    if expected_selected is None:
        assert result.selected is None
    else:
        assert result.selected is not None
        assert result.selected.ref.profile_id == expected_selected


def test_unavailable_profile_is_incompatible_even_when_capabilities_match() -> None:
    profile = _profile("adapter", "offline", RuntimeCapability("engine"), available=False)
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("engine"),)),
        RuntimeCatalog((profile,)),
    )
    evaluation = result.evaluations[0]
    assert evaluation.checks[0].satisfied is True
    assert evaluation.compatible is False


@pytest.mark.parametrize(
    ("constraint", "satisfied", "reason"),
    [
        (">=4, <5", True, "constraint satisfied"),
        (">=5", False, "constraint not satisfied"),
        ("alpha", False, "constraint not satisfied"),
        ("!=alpha", True, "constraint satisfied"),
    ],
)
def test_runtime_constraint_whitespace_and_literal_terms(
    constraint: str, satisfied: bool, reason: str
) -> None:
    profile = _profile("adapter", "versioned", RuntimeCapability("version", "4.2"))
    result = resolve_runtime(
        ExecutionProfile(requirements=(CapabilityRequirement("version", constraint),)),
        RuntimeCatalog((profile,)),
    )
    check = result.evaluations[0].checks[0]
    assert check.satisfied is satisfied
    assert check.reason == reason


def test_runtime_constraint_with_empty_term_fails_as_not_satisfied() -> None:
    with pytest.raises(ValueError, match="empty term"):
        CapabilityRequirement("version", ">=4,")
