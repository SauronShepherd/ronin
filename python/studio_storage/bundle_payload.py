"""Bounded payload reads from a fully verified Ronin Bundle archive."""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path

from studio_core.portability import RoninBundleManifest

from .bundle import (
    BUNDLE_MANIFEST_PATH,
    BundleFile,
    BundleIntegrityError,
    BundleReadLimits,
    _archive_path,
    _checked_infos,
    _read_manifest,
    _verify_payloads,
)

_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class VerifiedBundlePayload:
    """One bounded payload plus the manifest verified from the same archive handle."""

    manifest: RoninBundleManifest
    file: BundleFile


def read_bundle_payload(
    path: Path,
    entry_path: str,
    *,
    max_bytes: int = 8 * 1024 * 1024,
    limits: BundleReadLimits = BundleReadLimits(),
) -> VerifiedBundlePayload:
    """Verify the entire archive, then read one manifest-declared payload bounded in memory."""

    if max_bytes <= 0:
        raise ValueError("bundle payload max_bytes must be positive")
    requested = _archive_path(entry_path)
    if requested == BUNDLE_MANIFEST_PATH:
        raise BundleIntegrityError("bundle manifest is not a payload entry")

    try:
        with zipfile.ZipFile(path, mode="r", allowZip64=True) as archive:
            infos = _checked_infos(archive, limits)
            manifest = _read_manifest(archive, infos, limits)
            _verify_payloads(archive, infos, manifest, limits)
            entries = {entry.path: entry for entry in manifest.entries}
            entry = entries.get(requested)
            if entry is None:
                raise BundleIntegrityError("requested bundle payload is not declared by the manifest")
            if entry.size_bytes > max_bytes:
                raise BundleIntegrityError("requested bundle payload exceeds the in-memory read limit")

            digest = hashlib.sha256()
            observed = 0
            chunks: list[bytes] = []
            with archive.open(infos[requested], mode="r") as source:
                while True:
                    chunk = source.read(min(_CHUNK_BYTES, max_bytes - observed + 1))
                    if not chunk:
                        break
                    observed += len(chunk)
                    if observed > entry.size_bytes or observed > max_bytes:
                        raise BundleIntegrityError(
                            "requested bundle payload expanded beyond its declared limit"
                        )
                    digest.update(chunk)
                    chunks.append(chunk)
            if observed != entry.size_bytes or digest.hexdigest() != entry.digest:
                raise BundleIntegrityError("requested bundle payload changed during verified read")
            return VerifiedBundlePayload(
                manifest,
                BundleFile(entry.path, entry.media_type, b"".join(chunks)),
            )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise BundleIntegrityError("bundle archive is unreadable") from exc


__all__ = ("VerifiedBundlePayload", "read_bundle_payload")
