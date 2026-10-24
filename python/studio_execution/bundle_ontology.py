"""Deterministic Bundle portability for governed ontology definitions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

from studio_core import OntologyDefinition, WorkspaceId
from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.portability import RoninBundleManifest
from studio_orchestrator import Instant
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import BundlePayloadReader

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
ONTOLOGY_MEDIA_TYPE = "application/vnd.ronin.ontology-definition+json"


class OntologyBundleStore(Protocol):
    def list_all(self, workspace_id: WorkspaceId) -> tuple[OntologyDefinition, ...]: ...
    def put_many(
        self,
        workspace_id: WorkspaceId,
        ontologies: tuple[OntologyDefinition, ...],
        *,
        now: Instant | str,
    ) -> tuple[OntologyDefinition, ...]: ...


def _path(ref: str) -> str:
    return f"objects/ontology/{hashlib.sha256(ref.encode('utf-8')).hexdigest()}.json"


def export_ontology_bundle(
    workspace_id: WorkspaceId, store: OntologyBundleStore, path: Path
) -> RoninBundleManifest:
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    ontologies = sorted(
        store.list_all(workspace_id), key=lambda item: (item.id.value, item.version)
    )
    for ontology in ontologies:
        ref = f"ontology:{workspace_id}/{ontology.id}@{ontology.version}"
        object_path = _path(ref)
        objects.append(BundleInventoryObject("ontology", ref, object_path))
        files.append(
            BundleFile(object_path, ONTOLOGY_MEDIA_TYPE, ontology.to_json().encode("utf-8"))
        )
    inventory = BundleInventory(tuple(objects))
    files.append(
        BundleFile(
            BUNDLE_INVENTORY_PATH,
            INVENTORY_MEDIA_TYPE,
            encode_canonical_json(inventory.to_payload()),
        )
    )
    return write_bundle(path, tuple(sorted(files, key=lambda item: item.path)))


def import_ontology_bundle(
    path: Path, workspace_id: WorkspaceId, store: OntologyBundleStore, *, now: Instant | str
) -> tuple[OntologyDefinition, ...]:
    with BundlePayloadReader(path) as reader:
        inventory_payload = reader.read_payload(BUNDLE_INVENTORY_PATH)
        if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
            raise ValueError("ontology Bundle inventory has unsupported media type")
        inventory = BundleInventory.from_payload(json.loads(inventory_payload.file.data))
        values: list[OntologyDefinition] = []
        for item in inventory.objects:
            if item.kind != "ontology":
                raise ValueError("unsupported ontology Bundle object")
            payload = reader.read_payload(item.path)
            if (
                payload.manifest != inventory_payload.manifest
                or payload.file.media_type != ONTOLOGY_MEDIA_TYPE
            ):
                raise ValueError("ontology Bundle integrity or media type mismatch")
            values.append(OntologyDefinition.from_json(payload.file.data.decode("utf-8")))
    return store.put_many(workspace_id, tuple(values), now=now)


__all__ = ("export_ontology_bundle", "import_ontology_bundle")
