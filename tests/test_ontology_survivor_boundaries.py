from __future__ import annotations

import pytest
from studio_core import (
    ActionType,
    AssetId,
    AssetRef,
    AssetVersion,
    KnowledgeObject,
    KnowledgeObjectRef,
    LinkType,
    ObjectType,
    OntologyDefinition,
    OntologyId,
    PropertyDefinition,
    Requirement,
    ResourceScope,
    execute_ontology_action,
    materialize_object_type,
    resolve_link_type,
)


def _asset(name: str) -> AssetRef:
    return AssetRef(AssetId(name), AssetVersion("1"))


def _customer() -> ObjectType:
    return ObjectType(
        "Customer",
        _asset("customers"),
        ("customer_id",),
        (PropertyDefinition("id", "string", "customer_id", True),),
    )


def _order() -> ObjectType:
    return ObjectType(
        "Order",
        _asset("orders"),
        ("order_id",),
        (PropertyDefinition("id", "string", "order_id", True),),
    )


def test_ontology_contracts_round_trip_nested_payloads_and_asset_refs() -> None:
    requirement = Requirement("execute", ResourceScope("job", "job-1"))
    action = ActionType(
        "approve",
        "Order",
        ("reason",),
        (requirement,),
        write_asset=_asset("approvals"),
        idempotent=True,
    )
    link = LinkType(
        "customer-orders",
        "Customer",
        "Order",
        "one-to-many",
        ("customer_id",),
        ("order_id",),
        _asset("links"),
    )
    definition = OntologyDefinition(
        OntologyId("sales"),
        "v1",
        "Sales",
        (_order(), _customer()),
        (link,),
        (action,),
    )
    restored = OntologyDefinition.from_payload(definition.to_payload())
    assert restored == definition
    assert definition.asset_refs() == (
        _asset("approvals"),
        _asset("customers"),
        _asset("links"),
        _asset("orders"),
    )


@pytest.mark.parametrize(
    "cardinality",
    ["one-to-one", "one-to-many", "many-to-one", "many-to-many"],
)
def test_each_link_cardinality_accepts_a_single_matching_pair(cardinality: str) -> None:
    source_type = _customer()
    target_type = _order()
    source = materialize_object_type(source_type, ({"customer_id": "c1"},))
    target = materialize_object_type(target_type, ({"order_id": "o1"},))
    link = LinkType(
        "link",
        "Customer",
        "Order",
        cardinality,  # type: ignore[arg-type]
        ("customer_id",),
        ("order_id",),
    )
    # The source and target values intentionally match through the declared fields.
    source = tuple(KnowledgeObject(item.ref, (("customer_id", "c1"),)) for item in source)
    target = tuple(KnowledgeObject(item.ref, (("order_id", "c1"),)) for item in target)
    assert len(resolve_link_type(link, source, target)) == 1


def test_materialization_accepts_limit_boundary_and_stringifies_key_values() -> None:
    object_type = _customer()
    result = materialize_object_type(object_type, ({"customer_id": 7},), max_objects=1)
    assert result[0].ref == KnowledgeObjectRef("Customer", (("customer_id", "7"),))


@pytest.mark.parametrize("row", [None, [], {1: "customer"}])
def test_materialization_rejects_non_object_rows(row: object) -> None:
    with pytest.raises(ValueError, match="must be an object with string keys"):
        materialize_object_type(_customer(), (row,))  # type: ignore[arg-type]


def test_action_execution_without_idempotency_does_not_load_or_record_replay() -> None:
    action = ActionType("approve", "Order")
    target = KnowledgeObjectRef("Order", (("id", "o1"),))
    loaded: list[str] = []
    recorded: list[object] = []
    result = execute_ontology_action(
        action,
        target,
        {},
        authorize=lambda _: True,
        write=lambda *_: {"ok": True},
        load_idempotent=lambda key: loaded.append(key) or None,
        record_idempotent=recorded.append,
    )
    assert result.idempotency_key is None
    assert loaded == []
    assert recorded == []


@pytest.mark.parametrize("inputs", [None, [], {1: "reason"}])
def test_action_execution_rejects_non_object_or_non_string_input_keys(inputs: object) -> None:
    action = ActionType("approve", "Order")
    target = KnowledgeObjectRef("Order", (("id", "o1"),))
    with pytest.raises(ValueError, match="inputs must be an object with string keys"):
        execute_ontology_action(
            action,
            target,
            inputs,  # type: ignore[arg-type]
            authorize=lambda _: True,
            write=lambda *_: {},
        )


def test_action_execution_rejects_non_string_idempotency_key() -> None:
    action = ActionType("approve", "Order", idempotent=True)
    target = KnowledgeObjectRef("Order", (("id", "o1"),))
    with pytest.raises(ValueError, match="idempotency_key must be a string or null"):
        execute_ontology_action(
            action,
            target,
            {},
            authorize=lambda _: True,
            write=lambda *_: {},
            idempotency_key=1,  # type: ignore[arg-type]
        )


def test_action_replay_returns_saved_result_before_authorization_or_write() -> None:
    action = ActionType("approve", "Order", (), idempotent=True)
    target = KnowledgeObjectRef("Order", (("id", "o1"),))
    saved = execute_ontology_action(
        action,
        target,
        {},
        authorize=lambda _: True,
        write=lambda *_: {"ok": True},
        idempotency_key="request-1",
    )
    calls = {"authorize": 0, "write": 0}

    def authorize(_requirement) -> bool:
        calls["authorize"] += 1
        return False

    def write(*_):
        calls["write"] += 1
        return {}

    replay = execute_ontology_action(
        action,
        target,
        {},
        authorize=authorize,
        write=write,
        idempotency_key="request-1",
        load_idempotent=lambda _key: saved,
    )
    assert replay == saved
    assert calls == {"authorize": 0, "write": 0}
