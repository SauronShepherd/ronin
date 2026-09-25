import sqlite3

import pytest

from studio_ai_studio.contracts import (
    AdapterKind,
    EndpointConfig,
    EndpointId,
    ObservedState,
    PublicModelName,
)
from studio_ai_studio.state import ProbeObservation, transition
from studio_ai_studio.storage import AIStudioConflict, SQLiteAIStudioStore


def endpoint() -> EndpointConfig:
    return EndpointConfig(
        EndpointId("ollama"),
        AdapterKind.OLLAMA,
        "http://127.0.0.1:11434",
        (PublicModelName("qwen"),),
    )


def test_migration_is_idempotent_and_versioned_update_is_optimistic():
    store = SQLiteAIStudioStore(sqlite3.connect(":memory:"))
    version = store.put_endpoint(endpoint())
    assert store.put_endpoint(endpoint(), expected_version=version) == 2
    with pytest.raises(AIStudioConflict):
        store.put_endpoint(endpoint(), expected_version=version)
    assert store.get_endpoint(EndpointId("ollama"))[2] == 2


def test_readiness_and_capacity_are_distinct():
    assert transition(ObservedState.READY, ProbeObservation(True, False)) is ObservedState.SATURATED
    assert transition(ObservedState.SATURATED, ProbeObservation(True, True)) is ObservedState.READY
    assert transition(ObservedState.READY, ProbeObservation(False)) is ObservedState.FAILED
