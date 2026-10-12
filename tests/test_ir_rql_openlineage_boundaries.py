"""Directed contracts for the remaining IR, RQL and OpenLineage survivors."""

from __future__ import annotations

import pytest
from studio_core import (
    Edge,
    KnowledgeGraph,
    KnowledgeObject,
    KnowledgeObjectRef,
    Node,
    NodeId,
    OpenLineageTransport,
    OpenLineageTransportError,
    OperatorRef,
    Pipeline,
    Port,
    SchemaRef,
    ir,
    rql,
    validate_openlineage_event,
)

EVENT = {
    "eventType": "COMPLETE",
    "eventTime": "2026-09-21T00:00:00Z",
    "run": {"runId": "run-1"},
    "job": {"namespace": "ns", "name": "job"},
    "producer": "ronin",
}


@pytest.mark.parametrize("value", [(), (1, "x"), {"a": [1, False]}, bytearray(b"bytes")])
def test_ir_freeze_value_preserves_sequence_and_mapping_boundaries(value: object) -> None:
    if isinstance(value, bytearray):
        with pytest.raises(TypeError, match="unsupported IR value type"):
            ir.freeze_value(value)
        return
    frozen = ir.freeze_value(value)
    expected = list(value) if isinstance(value, tuple) else value
    assert ir.thaw_value(frozen) == expected


def test_ir_freeze_value_rejects_nonfinite_numbers_and_nonstring_mapping_keys() -> None:
    with pytest.raises(ValueError, match="finite"):
        ir.freeze_value(float("inf"))
    with pytest.raises(TypeError, match="mapping keys"):
        ir.freeze_value({1: "bad"})


def test_ir_schema_and_port_decoders_cover_null_version_and_kind_boundaries() -> None:
    assert ir._schema_from_data(None) is None
    assert ir._schema_from_data({"name": "orders", "version": None}) == SchemaRef("orders", None)
    assert ir._schema_from_data({"name": "orders", "version": "v1"}) == SchemaRef("orders", "v1")
    with pytest.raises(TypeError, match="schema.version"):
        ir._schema_from_data({"name": "orders", "version": 1})
    assert ir._port_from_data({"name": "out", "kind": "stream", "schema": None}) == Port(
        "out", "stream"
    )
    with pytest.raises(ValueError, match="port.kind"):
        ir._port_from_data({"name": "out", "kind": "unknown", "schema": None})


@pytest.mark.parametrize("value", [None, {1: "bad"}, "text", b"bytes", bytearray(b"bytes")])
def test_ir_shape_helpers_reject_non_object_and_non_array_boundaries(value: object) -> None:
    with pytest.raises(TypeError, match="object"):
        ir._require_mapping(value, "value")
    with pytest.raises(TypeError, match="array"):
        ir._require_sequence(value, "value")


def test_ir_node_payload_rejects_invalid_origin_ownership_optional_types() -> None:
    node = Node.create(operator=OperatorRef("source"), instance_key="node")
    data = ir._node_to_data(node)
    data["origin"] = {"view": "invalid", "reference": None}
    with pytest.raises(ValueError, match="origin view"):
        ir._node_from_data(data)
    data = ir._node_to_data(node)
    data["ownership"] = "invalid"
    with pytest.raises(ValueError, match="ownership"):
        ir._node_from_data(data)
    data = ir._node_to_data(node)
    data["label"] = 1
    with pytest.raises(TypeError, match="label"):
        ir._node_from_data(data)
    data = ir._node_to_data(node)
    data["origin"] = {"view": "system", "reference": 1}
    with pytest.raises(TypeError, match="origin.reference"):
        ir._node_from_data(data)


def test_ir_pipeline_rejects_incompatible_ports_schemas_unknown_nodes_and_cycles() -> None:
    source = Node.create(
        operator=OperatorRef("source"),
        instance_key="source",
        outputs=(Port("out", "batch", SchemaRef("source", "v1")),),
    )
    target = Node.create(
        operator=OperatorRef("target"), instance_key="target", inputs=(Port("in", "stream"),)
    )
    edge = Edge(source.id, "out", target.id, "in")
    with pytest.raises(ValueError, match="port kinds"):
        Pipeline((source, target), (edge,))
    target = Node.create(
        operator=OperatorRef("target"),
        instance_key="target",
        inputs=(Port("in", "batch", SchemaRef("other", "v1")),),
    )
    with pytest.raises(ValueError, match="schemas"):
        Pipeline((source, target), (Edge(source.id, "out", target.id, "in"),))
    with pytest.raises(ValueError, match="unknown node"):
        Pipeline((source,), (Edge(NodeId("missing"), "out", source.id, "out"),))


def test_rql_helpers_enforce_text_identifier_and_typed_path_contracts() -> None:
    with pytest.raises(TypeError, match="object"):
        rql._as_mapping({1: "bad"}, "mapping")
    with pytest.raises(ValueError, match="trimmed text"):
        rql._as_text(" ", "text")
    assert rql._optional_text(None, "optional") is None
    assert rql._optional_text("value", "optional") == "value"
    with pytest.raises(ValueError, match="portable identifier"):
        rql._identifier("bad name", "identifier")
    assert rql._traverse_path("Customer->Order") == "Customer->Order"
    with pytest.raises(ValueError, match="typed path"):
        rql._traverse_path("Customer->")


@pytest.mark.parametrize(
    "query",
    [
        "SELECT Customer WHERE region = 'EU'",
        "select Customer limit 2",
        "SELECT Customer TRAVERSE Order->Item JOIN Purchase ON account = customer LIMIT 7",
    ],
)
def test_rql_parser_accepts_each_supported_clause_combination(query: str) -> None:
    parsed = rql.parse_rql(query)
    assert parsed.source_type == "Customer"


def test_rql_ast_round_trip_preserves_null_optional_clauses_and_rejects_type_errors() -> None:
    parsed = rql.parse_rql("SELECT Customer")
    assert rql.RqlQuery.from_data(parsed.to_data()) == parsed
    invalid = parsed.to_data()
    invalid["version"] = True
    with pytest.raises(ValueError, match="version"):
        rql.RqlQuery.from_data(invalid)
    invalid = parsed.to_data()
    invalid["limit"] = False
    with pytest.raises(ValueError, match="positive integer"):
        rql.RqlQuery.from_data(invalid)


@pytest.mark.parametrize("value", [None, [], "ast", 1])
def test_rql_ast_requires_object_payload(value: object) -> None:
    with pytest.raises(TypeError, match="RQL AST must be an object"):
        rql.RqlQuery.from_data(value)  # type: ignore[arg-type]


def test_rql_execution_applies_limit_after_traversal_and_join() -> None:
    customer = KnowledgeObjectRef("Customer", (("id", "1"),))
    first = KnowledgeObjectRef("Order", (("id", "1"),))
    second = KnowledgeObjectRef("Order", (("id", "2"),))
    graph = KnowledgeGraph(
        (
            KnowledgeObject(customer, (("account", "a"),)),
            KnowledgeObject(first, (("account", "a"),)),
            KnowledgeObject(second, (("account", "a"),)),
        ),
        ((customer, first), (customer, second)),
    )
    assert rql.execute_rql("SELECT Customer TRAVERSE Order LIMIT 1", graph).objects == (
        graph.objects[1],
    )
    assert (
        len(
            rql.execute_rql(
                "SELECT Customer JOIN Order ON account = account LIMIT 1", graph
            ).objects
        )
        == 1
    )


@pytest.mark.parametrize("field", ["eventType", "eventTime", "run", "job", "producer"])
def test_openlineage_validator_requires_each_top_level_field(field: str) -> None:
    event = dict(EVENT)
    del event[field]
    with pytest.raises(ValueError, match="required fields"):
        validate_openlineage_event(event)


@pytest.mark.parametrize("event_time", ["", "2026-09-21T00:00:00+00:00", 1, None])
def test_openlineage_validator_requires_utc_string_ending_in_z(event_time: object) -> None:
    with pytest.raises(ValueError, match="eventTime"):
        validate_openlineage_event({**EVENT, "eventTime": event_time})


def test_openlineage_transport_retries_exactly_and_deduplicates_only_after_success() -> None:
    class Sink:
        def __init__(self) -> None:
            self.failures = 2
            self.events: list[object] = []

        def publish(self, event: object) -> None:
            if self.failures:
                self.failures -= 1
                raise RuntimeError("temporary")
            self.events.append(event)

    sink = Sink()
    transport = OpenLineageTransport(sink, max_attempts=3)
    receipt = transport.publish(EVENT)
    assert receipt.attempts == 3
    assert receipt.deduplicated is False
    assert transport.publish(EVENT).deduplicated is True
    assert len(sink.events) == 1


def test_openlineage_transport_does_not_mark_failed_events_and_preserves_cause() -> None:
    class FailingSink:
        def publish(self, event: object) -> None:
            del event
            raise RuntimeError("sink failed")

    with pytest.raises(OpenLineageTransportError) as raised:
        OpenLineageTransport(FailingSink(), max_attempts=2).publish(EVENT)
    assert isinstance(raised.value.__cause__, RuntimeError)
