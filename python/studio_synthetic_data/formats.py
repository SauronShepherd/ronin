"""Extensible Govern Studio format-provider contracts and safe serializers."""

from __future__ import annotations

import importlib.util
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol

from .engine import CsvExporter, JsonlExporter, SyntheticTable


@dataclass(frozen=True, slots=True)
class FormatManifest:
    format_id: str
    family: str
    version: str
    capabilities: frozenset[str] = frozenset()
    protocol_versions: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", self.format_id):
            raise ValueError(f"invalid format id: {self.format_id}")
        if self.family not in {"file", "table"}:
            raise ValueError(f"invalid format family: {self.family}")


@dataclass(frozen=True, slots=True)
class FormatAvailability:
    format_id: str
    status: str
    missing_dependencies: tuple[str, ...] = ()
    reason: str = ""


class FormatProvider(Protocol):
    manifest: FormatManifest

    def export(self, table: SyntheticTable) -> str: ...


class JsonExporter:
    manifest = FormatManifest("json", "file", "1.0", frozenset({"nested_values"}))
    format_id = "json"

    def export(self, table: SyntheticTable) -> str:
        return json.dumps(list(table.rows), ensure_ascii=False, sort_keys=True, default=str) + "\n"


class XmlExporter:
    manifest = FormatManifest("xml", "file", "1.0", frozenset({"nested_values"}))
    format_id = "xml"

    def __init__(self, *, row_element: str = "row") -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", row_element):
            raise ValueError("invalid XML row element")
        self.row_element = row_element

    def export(self, table: SyntheticTable) -> str:
        root = ET.Element("table", {"name": table.name})
        for row in table.rows:
            item = ET.SubElement(root, self.row_element)
            for key, value in row.items():
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", key):
                    raise ValueError(f"invalid XML column name: {key}")
                child = ET.SubElement(item, key)
                if value is not None:
                    child.text = str(value)
        return ET.tostring(root, encoding="unicode") + "\n"


class TableFormatProvider(Protocol):
    manifest: FormatManifest

    def validate_protocol(self, requested: str) -> None: ...


class DeclarativeTableProvider:
    """Capability manifest for an optional table writer.

    The baseline deliberately refuses writes until a protocol implementation is
    installed; advertising a format must never imply that it is writable.
    """

    def __init__(self, manifest: FormatManifest) -> None:
        if manifest.family != "table":
            raise ValueError("table provider requires a table manifest")
        self.manifest = manifest

    def validate_protocol(self, requested: str) -> None:
        if requested not in self.manifest.protocol_versions:
            raise ValueError(f"unsupported {self.manifest.format_id} protocol: {requested}")

    def export(self, _table: SyntheticTable) -> str:
        raise RuntimeError(
            f"{self.manifest.format_id} writer is not installed; provider is declarative only"
        )


def builtin_table_format_manifests() -> tuple[FormatManifest, ...]:
    return (
        FormatManifest(
            "delta",
            "table",
            "1.0",
            frozenset({"acid", "snapshots", "schema_evolution"}),
            ("reader_v1", "writer_v2"),
            ("deltalake",),
        ),
        FormatManifest(
            "iceberg",
            "table",
            "1.0",
            frozenset({"snapshots", "schema_evolution", "time_travel"}),
            ("v1", "v2", "v3"),
            ("pyiceberg",),
        ),
        FormatManifest(
            "hudi",
            "table",
            "1.0",
            frozenset({"upserts", "snapshots", "schema_evolution"}),
            ("timeline_v1",),
            ("hudi",),
        ),
    )


def format_availability(
    manifests: tuple[FormatManifest, ...] | None = None,
) -> tuple[FormatAvailability, ...]:
    """Report actual local capability without importing optional providers."""
    all_manifests = manifests or builtin_table_format_manifests()
    result: list[FormatAvailability] = [
        FormatAvailability(format_id, "ready") for format_id in ("csv", "json", "jsonl", "xml")
    ]
    for manifest in all_manifests:
        missing = tuple(
            dependency
            for dependency in manifest.optional_dependencies
            if importlib.util.find_spec(dependency) is None
        )
        result.append(
            FormatAvailability(
                manifest.format_id,
                "ready" if not missing else "optional_missing",
                missing,
                "writer installed" if not missing else "install the optional provider",
            )
        )
    return tuple(sorted(result, key=lambda item: item.format_id))


def delta_provider() -> DeclarativeTableProvider:
    return DeclarativeTableProvider(builtin_table_format_manifests()[0])


def iceberg_provider() -> DeclarativeTableProvider:
    return DeclarativeTableProvider(builtin_table_format_manifests()[1])


def hudi_provider() -> DeclarativeTableProvider:
    return DeclarativeTableProvider(builtin_table_format_manifests()[2])


def builtin_format_providers() -> tuple[FormatProvider, ...]:
    return (
        CsvExporter(),
        JsonExporter(),
        JsonlExporter(),
        XmlExporter(),
    )


__all__ = [
    "FormatManifest",
    "FormatAvailability",
    "FormatProvider",
    "DeclarativeTableProvider",
    "JsonExporter",
    "TableFormatProvider",
    "XmlExporter",
    "builtin_format_providers",
    "builtin_table_format_manifests",
    "format_availability",
    "delta_provider",
    "iceberg_provider",
    "hudi_provider",
]
