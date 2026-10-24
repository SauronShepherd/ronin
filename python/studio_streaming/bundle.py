"""Portable stream definitions with explicit target bindings and offset policy."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol

from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.portability import BindingKind, BindingRequest, RoninBundleManifest
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import BundlePayloadReader

from .contracts import StreamDefinition

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
STREAM_DEFINITION_MEDIA_TYPE = "application/vnd.ronin.stream-definition+json"
CheckpointImportPolicy = Literal["reset", "resume"]


class StreamBundleImportStore(Protocol):
    def list_definitions(self, project_id: str) -> tuple[StreamDefinition, ...]: ...

    def commit_stream_bundle_import(
        self,
        project_id: str,
        definitions: tuple[StreamDefinition, ...],
        checkpoint_policies: Mapping[str, str],
    ) -> tuple[tuple[str, str], ...]: ...


@dataclass(frozen=True, slots=True)
class StreamBundleImportPlan:
    inventory: BundleInventory
    definitions: tuple[StreamDefinition, ...]

    @property
    def unresolved_bindings(self) -> tuple[BindingRequest, ...]:
        return self.inventory.unresolved_bindings


@dataclass(frozen=True, slots=True)
class StreamBundleImportReceipt:
    plan: StreamBundleImportPlan
    runtime_bindings: tuple[tuple[str, str], ...]


def _path(stream_id: str) -> str:
    digest = hashlib.sha256(stream_id.encode("utf-8")).hexdigest()
    return f"objects/streaming/definitions/{digest}.json"


def _binding_requests(definition: StreamDefinition) -> tuple[BindingRequest, ...]:
    return tuple(
        sorted(
            (
                BindingRequest("connection", f"connection:{definition.source.connection_id}"),
                BindingRequest("runtime", f"runtime-profile:{definition.runtime.profile_id}"),
                BindingRequest("storage", f"storage-target:{definition.sink.target_ref}"),
            )
        )
    )


def build_stream_bundle(
    project_id: str, store: StreamBundleImportStore
) -> tuple[BundleInventory, tuple[BundleFile, ...]]:
    definitions = tuple(sorted(store.list_definitions(project_id), key=lambda item: item.id))
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    for definition in definitions:
        logical_ref = f"stream:{project_id}/{definition.id}"
        path = _path(logical_ref)
        objects.append(
            BundleInventoryObject(
                "stream_definition",
                logical_ref,
                path,
                binding_requests=_binding_requests(definition),
            )
        )
        files.append(
            BundleFile(
                path,
                STREAM_DEFINITION_MEDIA_TYPE,
                definition.to_json().encode("utf-8"),
            )
        )
    inventory = BundleInventory(tuple(objects))
    inventory_file = BundleFile(
        BUNDLE_INVENTORY_PATH,
        INVENTORY_MEDIA_TYPE,
        encode_canonical_json(inventory.to_payload()),
    )
    return inventory, tuple(sorted((inventory_file, *files), key=lambda item: item.path))


def export_stream_bundle(
    project_id: str, store: StreamBundleImportStore, path: Path
) -> RoninBundleManifest:
    return write_bundle(path, build_stream_bundle(project_id, store)[1])


def plan_stream_bundle_import(path: Path) -> StreamBundleImportPlan:
    with BundlePayloadReader(path) as reader:
        inventory_payload = reader.read_payload(BUNDLE_INVENTORY_PATH)
        if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
            raise ValueError("stream Bundle inventory has unsupported media type")
        inventory = BundleInventory.from_payload(json.loads(inventory_payload.file.data))
        definitions: list[StreamDefinition] = []
        for item in inventory.objects:
            if item.kind != "stream_definition":
                raise ValueError("stream Bundle contains an unsupported object kind")
            payload = reader.read_payload(item.path)
            if payload.manifest != inventory_payload.manifest:
                raise ValueError("stream Bundle changed while import plan was constructed")
            if payload.file.media_type != STREAM_DEFINITION_MEDIA_TYPE:
                raise ValueError("stream Bundle definition has unsupported media type")
            definition = StreamDefinition.from_json(payload.file.data.decode("utf-8"))
            if item.logical_ref.rsplit("/", maxsplit=1)[-1] != definition.id:
                raise ValueError("stream Bundle logical identity does not match definition")
            if item.path != _path(item.logical_ref):
                raise ValueError("stream Bundle payload path does not match logical identity")
            if item.binding_requests != _binding_requests(definition):
                raise ValueError("stream Bundle bindings do not match the definition")
            definitions.append(definition)
        return StreamBundleImportPlan(inventory, tuple(definitions))


def _remap_definition(
    definition: StreamDefinition, bindings: Mapping[str, str]
) -> StreamDefinition:
    connection_ref = f"connection:{definition.source.connection_id}"
    runtime_ref = f"runtime-profile:{definition.runtime.profile_id}"
    storage_ref = f"storage-target:{definition.sink.target_ref}"

    def mapped_ref(source_ref: str, prefix: str, kind: BindingKind) -> str:
        target_ref = bindings[source_ref]
        BindingRequest(kind, source_ref, suggested_target_ref=target_ref)
        if not target_ref.startswith(prefix) or len(target_ref) == len(prefix):
            raise ValueError(f"stream Bundle binding target must use {prefix} prefix")
        return target_ref.removeprefix(prefix)

    return replace(
        definition,
        source=replace(
            definition.source,
            connection_id=mapped_ref(connection_ref, "connection:", "connection"),
        ),
        sink=replace(
            definition.sink,
            target_ref=mapped_ref(storage_ref, "storage-target:", "storage"),
        ),
        runtime=replace(
            definition.runtime,
            profile_id=mapped_ref(runtime_ref, "runtime-profile:", "runtime"),
        ),
    )


def commit_stream_bundle_import(
    path: Path,
    project_id: str,
    store: StreamBundleImportStore,
    *,
    binding_remaps: Mapping[str, str],
    checkpoint_policies: Mapping[str, CheckpointImportPolicy],
) -> StreamBundleImportReceipt:
    plan = plan_stream_bundle_import(path)
    expected_bindings = {item.source_ref for item in plan.unresolved_bindings}
    if set(binding_remaps) != expected_bindings:
        raise ValueError("stream Bundle requires an explicit target for every binding")
    remapped = tuple(_remap_definition(item, binding_remaps) for item in plan.definitions)
    if set(checkpoint_policies) != {item.id for item in remapped}:
        raise ValueError("stream Bundle requires an explicit reset or resume policy per stream")
    runtime_bindings = store.commit_stream_bundle_import(project_id, remapped, checkpoint_policies)
    return StreamBundleImportReceipt(plan, runtime_bindings)


__all__ = (
    "CheckpointImportPolicy",
    "StreamBundleImportPlan",
    "StreamBundleImportReceipt",
    "StreamBundleImportStore",
    "build_stream_bundle",
    "commit_stream_bundle_import",
    "export_stream_bundle",
    "plan_stream_bundle_import",
)
