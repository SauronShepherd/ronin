"""Precise public contracts for survivor-prone validation and canonicalization paths.

These tests deliberately assert observable product behavior (stable diagnostics,
canonical payloads, and boundary decisions), rather than mutation-tool details.
"""

from __future__ import annotations

import pytest
from studio_core import (
    AssetId,
    AssetRef,
    AssetVersion,
    LinkType,
    Node,
    NodeId,
    ObjectType,
    OperatorRef,
    Port,
    PropertyDefinition,
    SchemaRef,
    audit,
    bundle_inventory,
    catalog,
    connections,
    environments,
    execute_ontology_action,
    freeze_value,
    genai,
    materialize_object_type,
    ml,
    portability,
    projects,
    quality,
    reproducible_manifest,
    resolve_link_type,
    role_assignments,
    scheduler,
    scheduler_events,
    source_control,
    workspaces,
)
from studio_core.ir import _node_semantic_payload


@pytest.mark.parametrize(
    ("validator", "empty_message"),
    [
        (audit._require_text, "field must be non-empty, trimmed, and single-line"),
        (bundle_inventory._require_text, "field must be non-empty, trimmed, and single-line"),
        (catalog._require_text, "field must be non-empty, trimmed, and single-line"),
        (connections._require_text, "field must be non-empty, trimmed, and single-line"),
        (environments._require_text, "field must be non-empty, trimmed, and single-line"),
        (genai._text, "field must be non-empty, trimmed, and single-line"),
        (ml._text, "field must be non-empty, trimmed, and single-line"),
        (portability._require_text, "field must be non-empty, trimmed, and single-line"),
        (quality._require_text, "field must be non-empty, trimmed, and single-line"),
        (scheduler._require_text, "field must be non-empty, trimmed, and single-line"),
        (scheduler_events._require_text, "field must be non-empty, trimmed, and single-line"),
        (source_control._text, "field must be non-empty and single-line"),
    ],
)
def test_shared_text_contracts_report_the_field_and_reject_empty_values(
    validator, empty_message: str
) -> None:
    with pytest.raises(ValueError, match=rf"^{empty_message}$"):
        validator("", "field")


def test_role_text_rejects_empty_and_non_string_values_with_stable_diagnostics() -> None:
    with pytest.raises(ValueError, match=r"^field must be non-empty trimmed text$"):
        role_assignments._text("", "field")
    with pytest.raises(ValueError, match=r"^field must be non-empty trimmed text$"):
        role_assignments._text(123, "field")


def test_connection_text_and_option_key_diagnostics_are_exact() -> None:
    with pytest.raises(ValueError, match=r"^field must be non-empty, trimmed, and single-line$"):
        connections._require_text("", "field")
    with pytest.raises(ValueError, match=r"^field must be non-empty, trimmed, and single-line$"):
        connections._require_text("value\x00other", "field")
    with pytest.raises(
        ValueError, match=r"^secret-bearing connection settings must use secret_refs$"
    ):
        connections._require_safe_option_key("PASSWORD")


@pytest.mark.parametrize(
    "validator",
    [
        audit._require_text,
        bundle_inventory._require_text,
        catalog._require_text,
        connections._require_text,
        environments._require_text,
        genai._text,
        ml._text,
        portability._require_text,
        quality._require_text,
        scheduler._require_text,
        scheduler_events._require_text,
        source_control._text,
    ],
)
@pytest.mark.parametrize("value", [" field", "field ", "field\nvalue", "field\rvalue"])
def test_shared_text_contracts_reject_each_noncanonical_shape(validator, value: str) -> None:
    with pytest.raises(ValueError, match="."):
        validator(value, "field")


def test_projects_and_workspaces_distinguish_trim_and_line_break_errors() -> None:
    for validator in (projects._require_text, workspaces._require_text):
        with pytest.raises(ValueError, match=r"^field must be non-empty and trimmed$"):
            validator("", "field")
        with pytest.raises(ValueError, match=r"^field must not contain line breaks$"):
            validator("field\nvalue", "field")


def test_reproducible_and_role_text_contracts_distinguish_trim_and_line_breaks() -> None:
    for validator in (reproducible_manifest._text, role_assignments._text):
        with pytest.raises(ValueError, match=r"^field must be non-empty trimmed text$"):
            validator("", "field")
        with pytest.raises(ValueError, match=r"^field must be single-line text$"):
            validator("field\nvalue", "field")


def test_canonical_node_identity_includes_all_semantic_contract_fields() -> None:
    operator = OperatorRef("source.table", 2)
    params = (("table", freeze_value("orders")),)
    outputs = (Port("out", "batch", SchemaRef("orders", "v1")),)
    payload = _node_semantic_payload(operator, params, (), outputs)
    assert payload == (
        '{"inputs":[],"operator":{"name":"source.table","version":2},'
        '"outputs":[{"kind":"batch","name":"out",'
        '"schema":{"name":"orders","version":"v1"}}],'
        '"params":{"table":"orders"}}'
    )
    node = Node.create(
        operator=operator, instance_key="source", params={"table": "orders"}, outputs=outputs
    )
    assert node.id == NodeId("3640c5e541bfdf374437b6082a42772ab4d8d0444d304b6a85b7895916a89512")


def test_freeze_value_preserves_exact_mapping_error_and_type_name() -> None:
    with pytest.raises(TypeError, match=r"^IR mapping keys must be strings$"):
        freeze_value({1: "bad"})
    with pytest.raises(TypeError, match=r"^unsupported IR value type: object$"):
        freeze_value(object())


def test_ontology_link_resolution_is_sorted_and_action_write_receives_target() -> None:
    source_type = ObjectType(
        "Customer",
        AssetRef(AssetId("customers"), AssetVersion("1")),
        ("id",),
        (PropertyDefinition("id", "string", "id", True),),
    )
    target_type = ObjectType(
        "Order",
        AssetRef(AssetId("orders"), AssetVersion("1")),
        ("customer_id",),
        (PropertyDefinition("customer_id", "string", "customer_id", True),),
    )
    sources = materialize_object_type(source_type, ({"id": 2}, {"id": 1}))
    targets = materialize_object_type(target_type, ({"customer_id": 1}, {"customer_id": 2}))
    link = LinkType("orders", "Customer", "Order", "many-to-many", ("id",), ("customer_id",))
    pairs = resolve_link_type(link, sources, targets)
    assert pairs == tuple(sorted(pairs, key=lambda pair: (pair[0], pair[1])))

    from studio_core import ActionType

    action = ActionType("ship", "Order")
    target = targets[0].ref
    calls = []
    result = execute_ontology_action(
        action,
        target,
        {},
        authorize=lambda _requirement: True,
        write=lambda received_action, received_target, inputs: (
            calls.append((received_action, received_target, dict(inputs))) or {"status": "ok"}
        ),
    )
    assert result.target == target
    assert calls == [(action, target, {})]
