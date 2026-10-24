"""Bounded payload reads from a fully verified Ronin Bundle archive."""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from studio_core.portability import BundleEntry, RoninBundleManifest

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
_DEFAULT_BUNDLE_READ_LIMITS = BundleReadLimits()


@dataclass(frozen=True, slots=True)
class VerifiedBundlePayload:
    """One bounded payload plus the manifest verified from the same archive handle."""

    manifest: RoninBundleManifest
    file: BundleFile


class BundlePayloadReader:
    """Verify one archive once, then read declared payloads from that same handle.

    Multi-object import planners need to inspect several entries. Reusing this
    reader keeps archive verification linear in the archive size and pins all
    payload reads to the file descriptor that was verified, avoiding repeated
    full-archive scans and path replacement between reads.
    """

    def __init__(self, path: Path, *, limits: BundleReadLimits = _DEFAULT_BUNDLE_READ_LIMITS):
        self._path = path
        self._limits = limits
        self._archive: zipfile.ZipFile | None = None
        self._infos: dict[str, zipfile.ZipInfo] | None = None
        self._manifest: RoninBundleManifest | None = None
        self._entries: dict[str, BundleEntry] | None = None
        self._opened = False

    def __enter__(self) -> BundlePayloadReader:
        if self._opened:
            raise RuntimeError("Bundle payload reader cannot be re-entered")
        self._opened = True
        archive: zipfile.ZipFile | None = None
        try:
            archive = zipfile.ZipFile(self._path, mode="r", allowZip64=True)
            infos = _checked_infos(archive, self._limits)
            manifest = _read_manifest(archive, infos, self._limits)
            _verify_payloads(archive, infos, manifest, self._limits)
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            if archive is not None:
                archive.close()
            raise BundleIntegrityError("bundle archive is unreadable") from exc
        except BaseException:
            if archive is not None:
                archive.close()
            raise
        self._archive = archive
        self._infos = infos
        self._manifest = manifest
        self._entries = {entry.path: entry for entry in manifest.entries}
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def manifest(self) -> RoninBundleManifest:
        if self._manifest is None:
            raise RuntimeError("Bundle payload reader is not open")
        return self._manifest

    def read_payload(
        self,
        entry_path: str,
        *,
        max_bytes: int = 8 * 1024 * 1024,
    ) -> VerifiedBundlePayload:
        """Read one declared payload and recheck its digest on the verified handle."""

        if max_bytes <= 0:
            raise ValueError("bundle payload max_bytes must be positive")
        archive, infos, entries = self._archive, self._infos, self._entries
        if archive is None or infos is None or entries is None:
            raise RuntimeError("Bundle payload reader is not open")
        requested = _archive_path(entry_path)
        if requested == BUNDLE_MANIFEST_PATH:
            raise BundleIntegrityError("bundle manifest is not a payload entry")
        entry = entries.get(requested)
        if entry is None:
            raise BundleIntegrityError("requested bundle payload is not declared by the manifest")
        if entry.size_bytes > max_bytes:
            raise BundleIntegrityError("requested bundle payload exceeds the in-memory read limit")

        digest = hashlib.sha256()
        observed = 0
        chunks: list[bytes] = []
        try:
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
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise BundleIntegrityError("bundle archive is unreadable") from exc
        if observed != entry.size_bytes or digest.hexdigest() != entry.digest:
            raise BundleIntegrityError("requested bundle payload changed during verified read")
        return VerifiedBundlePayload(
            self.manifest,
            BundleFile(requested, entry.media_type, b"".join(chunks)),
        )

    def close(self) -> None:
        archive, self._archive = self._archive, None
        self._infos = None
        self._manifest = None
        self._entries = None
        if archive is not None:
            archive.close()


def read_bundle_payload(
    path: Path,
    entry_path: str,
    *,
    max_bytes: int = 8 * 1024 * 1024,
    limits: BundleReadLimits = _DEFAULT_BUNDLE_READ_LIMITS,
) -> VerifiedBundlePayload:
    """Verify the entire archive, then read one manifest-declared payload bounded in memory."""

    if max_bytes <= 0:
        raise ValueError("bundle payload max_bytes must be positive")
    requested = _archive_path(entry_path)
    if requested == BUNDLE_MANIFEST_PATH:
        raise BundleIntegrityError("bundle manifest is not a payload entry")
    with BundlePayloadReader(path, limits=limits) as reader:
        return reader.read_payload(requested, max_bytes=max_bytes)


__all__ = ("BundlePayloadReader", "VerifiedBundlePayload", "read_bundle_payload")
