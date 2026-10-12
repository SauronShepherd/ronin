from __future__ import annotations

import pytest
from studio_core import (
    ActionType,
    KnowledgeObjectRef,
    Requirement,
    ResourceScope,
    execute_ontology_action,
)


def test_ontology_action_authorizes_and_dispatches_exact_inputs() -> None:
    action = ActionType(
        "approve",
        "Order",
        ("reason",),
        requirements=(Requirement("execute", ResourceScope("job", "order-1")),),
        idempotent=True,
    )
    target = KnowledgeObjectRef("Order", (("id", "1"),))
    result = execute_ontology_action(
        action,
        target,
        {"reason": "valid"},
        authorize=lambda _requirement: True,
        write=lambda _definition, _ref, _inputs: {"status": "approved"},
        idempotency_key="request-1",
    )
    assert result.output == {"status": "approved"}


def test_ontology_action_fails_closed_on_auth_and_input_contracts() -> None:
    action = ActionType(
        "approve",
        "Order",
        ("reason",),
        requirements=(Requirement("execute", ResourceScope("job", "order-1")),),
        idempotent=True,
    )
    target = KnowledgeObjectRef("Order", (("id", "1"),))
    with pytest.raises(PermissionError):
        execute_ontology_action(
            action,
            target,
            {"reason": "x"},
            authorize=lambda _: False,
            write=lambda *_: {},
            idempotency_key="x",
        )
    with pytest.raises(ValueError, match="exactly"):
        execute_ontology_action(
            action, target, {}, authorize=lambda _: True, write=lambda *_: {}, idempotency_key="x"
        )


def test_idempotent_ontology_action_replays_without_repeating_write() -> None:
    action = ActionType("approve", "Order", (), idempotent=True)
    target = KnowledgeObjectRef("Order", (("id", "1"),))
    writes = 0
    saved = {}

    def write(*_):
        nonlocal writes
        writes += 1
        return {"status": "approved"}

    first = execute_ontology_action(
        action,
        target,
        {},
        authorize=lambda _: True,
        write=write,
        idempotency_key="x",
        record_idempotent=lambda result: saved.update({"x": result}),
    )
    second = execute_ontology_action(
        action,
        target,
        {},
        authorize=lambda _: True,
        write=write,
        idempotency_key="x",
        load_idempotent=lambda key: saved.get(key),
    )
    assert first == second
    assert writes == 1


def test_ontology_action_rejects_target_key_reuse_and_invalid_write_result() -> None:
    action = ActionType("approve", "Order", (), idempotent=False)
    target = KnowledgeObjectRef("Order", (("id", "1"),))
    with pytest.raises(ValueError, match="target type"):
        execute_ontology_action(
            action,
            KnowledgeObjectRef("Customer", (("id", "1"),)),
            {},
            authorize=lambda _: True,
            write=lambda *_: {},
        )
    with pytest.raises(ValueError, match="mapping"):
        execute_ontology_action(
            action,
            target,
            {},
            authorize=lambda _: True,
            write=lambda *_: [],
        )


def test_ontology_action_rejects_blank_idempotency_and_mismatched_replay() -> None:
    action = ActionType("approve", "Order", (), idempotent=True)
    target = KnowledgeObjectRef("Order", (("id", "1"),))
    with pytest.raises(ValueError, match="idempotency_key"):
        execute_ontology_action(
            action, target, {}, authorize=lambda _: True, write=lambda *_: {}, idempotency_key="  "
        )
    replay = execute_ontology_action(
        ActionType("different", "Order", (), idempotent=False),
        target,
        {},
        authorize=lambda _: True,
        write=lambda *_: {"status": "old"},
    )
    with pytest.raises(ValueError, match="different"):
        execute_ontology_action(
            action,
            target,
            {},
            authorize=lambda _: True,
            write=lambda *_: {},
            idempotency_key="request-1",
            load_idempotent=lambda _key: replay,
        )


def test_ontology_action_error_messages_and_write_contract_are_exact() -> None:
    action = ActionType(
        "approve",
        "Order",
        ("reason",),
        requirements=(Requirement("execute", ResourceScope("job", "order-1")),),
        idempotent=True,
    )
    target = KnowledgeObjectRef("Order", (("id", "1"),))

    cases = (
        (
            lambda: execute_ontology_action(
                action,
                KnowledgeObjectRef("Customer", (("id", "1"),)),
                {"reason": "ok"},
                authorize=lambda _: True,
                write=lambda *_: {},
                idempotency_key="x",
            ),
            "ontology action target type does not match action definition",
        ),
        (
            lambda: execute_ontology_action(
                action,
                target,
                {},
                authorize=lambda _: True,
                write=lambda *_: {},
                idempotency_key="x",
            ),
            "ontology action inputs must exactly match declared input_fields",
        ),
        (
            lambda: execute_ontology_action(
                action,
                target,
                {"reason": "ok"},
                authorize=lambda _: True,
                write=lambda *_: {},
            ),
            "idempotent ontology actions require an idempotency_key",
        ),
        (
            lambda: execute_ontology_action(
                action,
                target,
                {"reason": "ok"},
                authorize=lambda _: False,
                write=lambda *_: {},
                idempotency_key="x",
            ),
            "ontology action authorization requirement was denied",
        ),
        (
            lambda: execute_ontology_action(
                action,
                target,
                {"reason": "ok"},
                authorize=lambda _: True,
                write=lambda *_: [],
                idempotency_key="x",
            ),
            "ontology action write executor must return an object mapping",
        ),
    )
    for invoke, message in cases:
        with pytest.raises((ValueError, PermissionError)) as error:
            invoke()
        assert str(error.value) == message
