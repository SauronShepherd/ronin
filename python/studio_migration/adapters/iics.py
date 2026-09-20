"""Safe, deterministic discovery of exported Informatica IICS artifacts."""

from __future__ import annotations

import hashlib
import io
import json
import posixpath
import zipfile
from collections.abc import Iterable, Mapping

from ..model import MigrationUnit, SourceArtifact, SourceInventory

IICS_ADAPTER_VERSION = "ronin-iics-0.1"
MAX_ENTRY_COUNT = 10_000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def _safe_member(name: str) -> str:
    normalized = posixpath.normpath(name.replace("\\", "/"))
    if normalized in {"", "."} or normalized.startswith("../") or normalized.startswith("/"):
        raise ValueError("IICS archive contains an unsafe path")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("IICS archive contains an unsafe path")
    return normalized


def _read_archive(
    archives: Iterable[tuple[str, bytes]],
) -> tuple[tuple[SourceArtifact, ...], dict[str, bytes]]:
    artifacts: list[SourceArtifact] = []
    members: dict[str, bytes] = {}
    for archive_name, raw in sorted(archives, key=lambda item: item[0]):
        if not archive_name or "\\" in archive_name or "/" in archive_name:
            raise ValueError("archive names must be safe basenames")
        artifacts.append(
            SourceArtifact(
                archive_name, hashlib.sha256(raw).hexdigest(), len(raw), "application/zip"
            )
        )
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_ENTRY_COUNT:
                    raise ValueError("IICS archive exceeds entry-count limit")
                total = 0
                for info in infos:
                    member = _safe_member(info.filename)
                    if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("IICS archive contains a directory or symlink entry")
                    total += info.file_size
                    if total > MAX_UNCOMPRESSED_BYTES:
                        raise ValueError("IICS archive exceeds decompressed-size limit")
                    if member in members:
                        raise ValueError(f"duplicate IICS archive member: {member}")
                    members[member] = archive.read(info)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"invalid IICS ZIP archive: {archive_name}") from exc
    return tuple(artifacts), members


def _identity(value: Mapping[str, object], *fields: str) -> str | None:
    for field in fields:
        candidate = value.get(field)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def discover_iics_zip(archives: Iterable[tuple[str, bytes]]) -> SourceInventory:
    """Discover IICS units without executing archive content."""
    artifacts, members = _read_archive(archives)
    units: dict[str, MigrationUnit] = {}
    template_ids: set[str] = set()
    documents: list[tuple[str, Mapping[str, object]]] = []
    for path, raw in sorted(members.items()):
        if not path.casefold().endswith(".json"):
            continue
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"IICS JSON member is invalid: {path}") from exc
        if isinstance(value, Mapping):
            documents.append((path, value))
            if path.casefold().endswith(("dtemplate.json", "mappingtemplate.json")):
                identity = _identity(value, "assetFrsGuid", "mappingId", "id", "name")
                if identity:
                    template_ids.add(identity)
    for path, document in documents:
        lower = path.casefold()
        kind = "process" if "process" in lower or lower.endswith("mtt.json") else None
        if kind is None and ("mapping" in lower or "dtemplate" in lower):
            kind = "mapping"
        if kind is None:
            continue
        identity_fields = (
            ("id", "name", "mappingId", "assetFrsGuid")
            if kind == "process"
            else ("mappingId", "assetFrsGuid", "id", "name")
        )
        identity = _identity(document, *identity_fields) or path
        key = f"iics:{kind}:{identity}"
        notes = [f"discovered_from:{path}"]
        state = "ready"
        refs: tuple[str, ...] = ()
        mapping_id = document.get("mappingId")
        if isinstance(mapping_id, str) and mapping_id.strip():
            refs = (mapping_id.strip(),)
            if mapping_id.strip() not in template_ids:
                state = "review_required"
                notes.append("mappingId could not be resolved to DTEMPLATE.assetFrsGuid")
        units[key] = MigrationUnit(key, kind, identity, state, (), refs, tuple(notes))
    if not units:
        raise ValueError("IICS archives contain no discoverable DTEMPLATE, MTT or mapping JSON")
    package_names = sorted({path.split("/")[0] for path in members})
    for package in package_names:
        key = f"iics:package:{package}"
        units[key] = MigrationUnit(key, "package", package, "ready")
    return SourceInventory("iics", IICS_ADAPTER_VERSION, artifacts, tuple(units.values()))


__all__ = ("IICS_ADAPTER_VERSION", "discover_iics_zip")
