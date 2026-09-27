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
