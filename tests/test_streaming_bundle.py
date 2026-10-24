from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from studio_execution.bundle_streaming import (
    commit_stream_bundle_import,
    export_stream_bundle,
    plan_stream_bundle_import,
)
from studio_streaming import (
    SqliteStreamCheckpointStore,
    StreamCheckpoint,
    StreamDefinition,
    StreamDefinitionConflict,
    StreamPosition,
    StreamRuntimeBinding,
    StreamSchemaField,
    StreamSinkDefinition,
    StreamSourceDefinition,
)


def _definition(
    stream_id: str = "events",
    *,
    connection_id: str = "kafka-source",
    target_ref: str = "table.events",
    profile_id: str = "local",
) -> StreamDefinition:
    return StreamDefinition(
        stream_id,
        "Events",
        StreamSourceDefinition(connection_id, "topic.events", (1, 0)),
        StreamSinkDefinition("table", target_ref),
        (StreamSchemaField("event_id", "int64", nullable=False),),
        StreamRuntimeBinding(profile_id, batch_limit=250, timeout_seconds=2.5),
    )


def _bindings(
    *,
    connection_id: str = "kafka-target",
    target_ref: str = "table.events-target",
    profile_id: str = "prod",
) -> dict[str, str]:
    return {
        "connection:kafka-source": f"connection:{connection_id}",
        "storage-target:table.events": f"storage-target:{target_ref}",
        "runtime-profile:local": f"runtime-profile:{profile_id}",
    }


def test_stream_definition_is_canonical_and_rejects_runtime_secrets() -> None:
    definition = _definition()
    payload = definition.to_json()
    assert StreamDefinition.from_json(payload) == definition
    assert StreamDefinition.from_json(payload).to_json() == payload
    integer_timeout = StreamRuntimeBinding("local", timeout_seconds=2)
    assert StreamRuntimeBinding.from_payload(integer_timeout.to_payload()).to_payload() == {
        "profile_id": "local",
        "batch_limit": 1000,
        "timeout_seconds": 2.0,
    }
    with pytest.raises(ValueError, match="schema must not be empty"):
        StreamDefinition(
            "events",
            "Events",
            definition.source,
            definition.sink,
            (),
            definition.runtime,
        )
    with pytest.raises(ValueError, match="credential material"):
        StreamRuntimeBinding("password=secret")


def test_stream_bundle_requires_bindings_and_reset_then_uses_fresh_checkpoint(
    tmp_path: Path,
) -> None:
    source = SqliteStreamCheckpointStore(tmp_path / "source.sqlite")
    source_definition = _definition()
    source_runtime_id = dict(
        source.commit_stream_bundle_import("project-a", (source_definition,), {"events": "reset"})
    )["events"]
    advanced = StreamCheckpoint((StreamPosition(0, 99),))
    assert source.compare_and_set(source_runtime_id, StreamCheckpoint(), advanced)

    first = tmp_path / "first.roninbundle"
    second = tmp_path / "second.roninbundle"
    export_stream_bundle("project-a", source, first)
    export_stream_bundle("project-a", source, second)
    assert first.read_bytes() == second.read_bytes()
    plan = plan_stream_bundle_import(first)
    assert plan.definitions == (source_definition,)
    assert {item.kind for item in plan.unresolved_bindings} == {
        "connection",
        "runtime",
        "storage",
    }
    assert b"checkpoint" not in first.read_bytes()

    target = SqliteStreamCheckpointStore(tmp_path / "target.sqlite")
    with pytest.raises(ValueError, match="explicit target"):
        commit_stream_bundle_import(
            first,
            "project-b",
            target,
            binding_remaps={},
            checkpoint_policies={"events": "reset"},
        )
    with pytest.raises(ValueError, match="explicit reset or resume"):
        commit_stream_bundle_import(
            first,
            "project-b",
            target,
            binding_remaps=_bindings(),
            checkpoint_policies={},
        )
    assert target.list_definitions("project-b") == ()

    # An old checkpoint keyed by the logical id is not selected by the new runtime binding.
    assert target.compare_and_set("events", StreamCheckpoint(), advanced)
    receipt = commit_stream_bundle_import(
        first,
        "project-b",
        target,
        binding_remaps=_bindings(),
        checkpoint_policies={"events": "reset"},
    )
    runtime_id = dict(receipt.runtime_bindings)["events"]
    assert runtime_id != "events"
    assert target.get(runtime_id) == StreamCheckpoint()
    assert target.get("events") == advanced
    assert target.get_definition("project-b", "events") == _definition(
        connection_id="kafka-target",
        target_ref="table.events-target",
        profile_id="prod",
    )


def test_stream_bundle_resume_requires_matching_definition_and_keeps_offsets(
    tmp_path: Path,
) -> None:
    source = SqliteStreamCheckpointStore(tmp_path / "source.sqlite")
    source.commit_stream_bundle_import("project-a", (_definition(),), {"events": "reset"})
    bundle = tmp_path / "streams.roninbundle"
    export_stream_bundle("project-a", source, bundle)

    target = SqliteStreamCheckpointStore(tmp_path / "target.sqlite")
    remaps = _bindings()
    first = commit_stream_bundle_import(
        bundle,
        "project-b",
        target,
        binding_remaps=remaps,
        checkpoint_policies={"events": "reset"},
    )
    runtime_id = dict(first.runtime_bindings)["events"]
    saved = StreamCheckpoint((StreamPosition(0, 17),))
    assert target.compare_and_set(runtime_id, StreamCheckpoint(), saved)

    resumed = commit_stream_bundle_import(
        bundle,
        "project-b",
        target,
        binding_remaps=remaps,
        checkpoint_policies={"events": "resume"},
    )
    assert dict(resumed.runtime_bindings)["events"] == runtime_id
    assert target.get(runtime_id) == saved

    changed_remaps = _bindings(connection_id="kafka-other")
    with pytest.raises(StreamDefinitionConflict, match="cannot safely resume"):
        commit_stream_bundle_import(
            bundle,
            "project-b",
            target,
            binding_remaps=changed_remaps,
            checkpoint_policies={"events": "resume"},
        )
    assert target.get(runtime_id) == saved
    assert target.get_definition("project-b", "events") == _definition(
        connection_id="kafka-target",
        target_ref="table.events-target",
        profile_id="prod",
    )

    reset = commit_stream_bundle_import(
        bundle,
        "project-b",
        target,
        binding_remaps=changed_remaps,
        checkpoint_policies={"events": "reset"},
    )
    assert dict(reset.runtime_bindings)["events"] == runtime_id
    assert target.get(runtime_id) == StreamCheckpoint()
    assert target.get_definition("project-b", "events") == _definition(
        connection_id="kafka-other",
        target_ref="table.events-target",
        profile_id="prod",
    )


def test_stream_bundle_import_rolls_back_every_definition_on_late_resume_conflict(
    tmp_path: Path,
) -> None:
    source = SqliteStreamCheckpointStore(tmp_path / "source.sqlite")
    definitions = (_definition("alpha"), _definition("beta"))
    source.commit_stream_bundle_import(
        "project-a", definitions, {"alpha": "reset", "beta": "reset"}
    )
    bundle = tmp_path / "streams.roninbundle"
    export_stream_bundle("project-a", source, bundle)

    target = SqliteStreamCheckpointStore(tmp_path / "target.sqlite")
    bindings = {
        "connection:kafka-source": "connection:kafka-target",
        "storage-target:table.events": "storage-target:table.events-target",
        "runtime-profile:local": "runtime-profile:prod",
    }
    with pytest.raises(StreamDefinitionConflict, match="cannot safely resume"):
        commit_stream_bundle_import(
            bundle,
            "project-b",
            target,
            binding_remaps=bindings,
            checkpoint_policies={"alpha": "reset", "beta": "resume"},
        )
    assert target.list_definitions("project-b") == ()
    assert target.get(target.runtime_stream_id("project-b", "alpha")) == StreamCheckpoint()


def test_stream_checkpoint_digest_corruption_fails_closed_on_read_and_resume(
    tmp_path: Path,
) -> None:
    source = SqliteStreamCheckpointStore(tmp_path / "source.sqlite")
    source.commit_stream_bundle_import("project-a", (_definition(),), {"events": "reset"})
    bundle = tmp_path / "streams.roninbundle"
    export_stream_bundle("project-a", source, bundle)

    target_path = tmp_path / "target.sqlite"
    target = SqliteStreamCheckpointStore(target_path)
    receipt = commit_stream_bundle_import(
        bundle,
        "project-b",
        target,
        binding_remaps=_bindings(),
        checkpoint_policies={"events": "reset"},
    )
    runtime_id = dict(receipt.runtime_bindings)["events"]
    saved = StreamCheckpoint((StreamPosition(0, 7),))
    assert target.compare_and_set(runtime_id, StreamCheckpoint(), saved)
    with closing(sqlite3.connect(target_path)) as connection, connection:
        connection.execute(
            "UPDATE stream_checkpoints SET checkpoint_digest=? WHERE stream_id=?",
            ("0" * 64, runtime_id),
        )

    with pytest.raises(ValueError, match="digest does not match"):
        target.get(runtime_id)
    with pytest.raises(StreamDefinitionConflict, match="cannot safely resume"):
        commit_stream_bundle_import(
            bundle,
            "project-b",
            target,
            binding_remaps=_bindings(),
            checkpoint_policies={"events": "resume"},
        )
    assert target.get_definition("project-b", "events") == _definition(
        connection_id="kafka-target",
        target_ref="table.events-target",
        profile_id="prod",
    )


def test_stream_runtime_checkpoints_are_scoped_by_project_and_definition(
    tmp_path: Path,
) -> None:
    store = SqliteStreamCheckpointStore(tmp_path / "streaming.sqlite")
    first = dict(
        store.commit_stream_bundle_import("project-a", (_definition(),), {"events": "reset"})
    )["events"]
    second = dict(
        store.commit_stream_bundle_import("project-b", (_definition(),), {"events": "reset"})
    )["events"]
    assert first != second

    checkpoint = StreamCheckpoint((StreamPosition(0, 8),))
    assert store.compare_and_set(first, StreamCheckpoint(), checkpoint)
    assert store.get(first) == checkpoint
    assert store.get(second) == StreamCheckpoint()
    assert store.get_definition("project-a", "events") == _definition()
    assert store.get_definition("project-b", "events") == _definition()
