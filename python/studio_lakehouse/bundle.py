"""Portable Bundle helpers for logical lakehouse table metadata."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from studio_core.bundle_inventory import (
    BUNDLE_INVENTORY_PATH,
    BundleInventory,
    BundleInventoryObject,
)
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.portability import RoninBundleManifest
from studio_storage.bundle import BundleFile, write_bundle
from studio_storage.bundle_payload import read_bundle_payload

from .tables import TableMetadata

INVENTORY_MEDIA_TYPE = "application/vnd.ronin.bundle-inventory+json"
TABLE_MEDIA_TYPE = "application/vnd.ronin.lakehouse-table+json"


def export_table_metadata_bundle(
    tables: Sequence[TableMetadata], path: Path
) -> RoninBundleManifest:
    objects, files = [], []
    for table in sorted(tables, key=lambda item: item.identifier.qualified_name):
        ref = f"table:{table.identifier.qualified_name}"
        object_path = f"objects/tables/{hashlib.sha256(ref.encode()).hexdigest()}.json"
        objects.append(BundleInventoryObject("table_metadata", ref, object_path))
        files.append(BundleFile(object_path, TABLE_MEDIA_TYPE, table.to_json().encode()))
    inventory = BundleInventory(tuple(objects))
    files.append(
        BundleFile(
            BUNDLE_INVENTORY_PATH,
            INVENTORY_MEDIA_TYPE,
            encode_canonical_json(inventory.to_payload()),
        )
    )
    return write_bundle(path, tuple(sorted(files, key=lambda item: item.path)))


def import_table_metadata_bundle(
    path: Path, *, remap_location: Callable[[TableMetadata], str] | None = None
) -> tuple[TableMetadata, ...]:
    inventory_file = read_bundle_payload(path, BUNDLE_INVENTORY_PATH)
    inventory = BundleInventory.from_payload(json.loads(inventory_file.file.data))
    tables = []
    for item in inventory.objects:
        if item.kind != "table_metadata":
            raise ValueError("unsupported lakehouse Bundle object")
        payload = read_bundle_payload(path, item.path)
        if (
            payload.manifest != inventory_file.manifest
            or payload.file.media_type != TABLE_MEDIA_TYPE
        ):
            raise ValueError("lakehouse Bundle integrity or media type mismatch")
        table = TableMetadata.from_json(payload.file.data.decode())
        if remap_location is not None:
            table = TableMetadata(
                table.identifier,
                table.format,
                remap_location(table),
                table.managed,
                table.schema,
                table.partition_spec,
                table.properties,
            )
        tables.append(table)
    return tuple(tables)


__all__ = ("export_table_metadata_bundle", "import_table_metadata_bundle")
