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
from studio_storage.bundle_payload import read_bundle_payload

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
ONTOLOGY_MEDIA_TYPE = "application/vnd.ronin.ontology-definition+json"


class OntologyBundleStore(Protocol):
    def list_all(self, workspace_id: WorkspaceId) -> tuple[OntologyDefinition, ...]: ...
    def put(
        self, workspace_id: WorkspaceId, ontology: OntologyDefinition, *, now: Instant | str
    ) -> OntologyDefinition: ...


def _path(ref: str) -> str:
    return f"objects/ontology/{hashlib.sha256(ref.encode('utf-8')).hexdigest()}.json"


def export_ontology_bundle(
    workspace_id: WorkspaceId, store: OntologyBundleStore, path: Path
) -> RoninBundleManifest:
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    for ontology in store.list_all(workspace_id):
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
    inventory_payload = read_bundle_payload(path, BUNDLE_INVENTORY_PATH)
    inventory = BundleInventory.from_payload(json.loads(inventory_payload.file.data))
    values: list[OntologyDefinition] = []
    for item in inventory.objects:
        if item.kind != "ontology":
            raise ValueError("unsupported ontology Bundle object")
        payload = read_bundle_payload(path, item.path)
        if (
            payload.manifest != inventory_payload.manifest
            or payload.file.media_type != ONTOLOGY_MEDIA_TYPE
        ):
            raise ValueError("ontology Bundle integrity or media type mismatch")
        values.append(OntologyDefinition.from_json(payload.file.data.decode("utf-8")))
    for value in values:
        store.put(workspace_id, value, now=now)
    return tuple(values)


__all__ = ("export_ontology_bundle", "import_ontology_bundle")
