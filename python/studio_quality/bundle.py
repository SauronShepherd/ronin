"""Portable Bundle export/import for quality contract definitions (not run history)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from studio_core import DataContract, WorkspaceId
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

QUALITY_MEDIA_TYPE = "application/vnd.ronin.quality-contract+json"
INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"


class QualityBundleStore(Protocol):
    def list_contracts(self, workspace_id: WorkspaceId) -> tuple[DataContract, ...]: ...
    def put_contract(
        self, workspace_id: WorkspaceId, contract: DataContract, *, now: Instant | str
    ) -> DataContract: ...


@dataclass(frozen=True, slots=True)
class QualityBundleImportPlan:
    inventory: BundleInventory
    contracts: tuple[DataContract, ...]


def _path(ref: str) -> str:
    return f"objects/quality/{hashlib.sha256(ref.encode('utf-8')).hexdigest()}.json"


def build_quality_bundle(
    workspace_id: WorkspaceId, store: QualityBundleStore
) -> tuple[BundleInventory, tuple[BundleFile, ...]]:
    contracts = tuple(
        sorted(
            store.list_contracts(workspace_id),
            key=lambda item: (str(item.asset.asset_id), str(item.asset.version)),
        )
    )
    objects: list[BundleInventoryObject] = []
    files: list[BundleFile] = []
    for contract in contracts:
        logical_ref = (
            f"quality-contract:{workspace_id}/{contract.asset.asset_id}@{contract.asset.version}"
        )
        path = _path(logical_ref)
        objects.append(BundleInventoryObject("quality_contract", logical_ref, path))
        files.append(BundleFile(path, QUALITY_MEDIA_TYPE, contract.to_json().encode("utf-8")))
    inventory = BundleInventory(tuple(objects))
    inventory_file = BundleFile(
        BUNDLE_INVENTORY_PATH, INVENTORY_MEDIA_TYPE, encode_canonical_json(inventory.to_payload())
    )
    return inventory, tuple(sorted((inventory_file, *files), key=lambda item: item.path))


def export_quality_bundle(
    workspace_id: WorkspaceId, store: QualityBundleStore, path: Path
) -> RoninBundleManifest:
    return write_bundle(path, build_quality_bundle(workspace_id, store)[1])


def plan_quality_bundle_import(path: Path) -> QualityBundleImportPlan:
    inventory_payload = read_bundle_payload(path, BUNDLE_INVENTORY_PATH)
    if inventory_payload.file.media_type != INVENTORY_MEDIA_TYPE:
        raise ValueError("quality Bundle inventory has unsupported media type")
    inventory = BundleInventory.from_payload(json.loads(inventory_payload.file.data))
    contracts: list[DataContract] = []
    for item in inventory.objects:
        if item.kind != "quality_contract":
            raise ValueError("unsupported quality Bundle object")
        payload = read_bundle_payload(path, item.path)
        if (
            payload.manifest != inventory_payload.manifest
            or payload.file.media_type != QUALITY_MEDIA_TYPE
        ):
            raise ValueError("quality Bundle object integrity or media type mismatch")
        contracts.append(DataContract.from_json(payload.file.data.decode("utf-8")))
    return QualityBundleImportPlan(inventory, tuple(contracts))


def commit_quality_bundle_import(
    path: Path, workspace_id: WorkspaceId, store: QualityBundleStore, *, now: Instant | str
) -> QualityBundleImportPlan:
    plan = plan_quality_bundle_import(path)
    existing = {contract.asset: contract for contract in store.list_contracts(workspace_id)}
    for contract in plan.contracts:
        if contract.asset in existing and existing[contract.asset] != contract:
            raise ValueError(
                f"quality contract conflicts with existing definition: {contract.asset}"
            )
    for contract in plan.contracts:
        store.put_contract(workspace_id, contract, now=now)
    return plan


__all__ = (
    "QualityBundleImportPlan",
    "build_quality_bundle",
    "commit_quality_bundle_import",
    "export_quality_bundle",
    "plan_quality_bundle_import",
)
