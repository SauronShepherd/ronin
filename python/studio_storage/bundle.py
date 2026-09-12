"""Deterministic, fail-closed Ronin Bundle archive IO.

The canonical manifest lives in ``studio_core.portability``. This adapter owns only
local archive persistence and verification; it does not add vendor semantics.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from studio_core.portability import BundleEntry, MigrationReport, RoninBundleManifest

BUNDLE_MANIFEST_PATH = "ronin-bundle.json"
_CHUNK_BYTES = 1024 * 1024
_ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})


class BundleIntegrityError(ValueError):
    """Raised when an archive does not match its canonical manifest."""


@dataclass(frozen=True, slots=True)
class BundleReadLimits:
    """Resource limits applied before and while reading an untrusted bundle."""

    max_entries: int = 10_000
    max_manifest_bytes: int = 8 * 1024 * 1024
    max_entry_bytes: int = 1024 * 1024 * 1024
    max_total_bytes: int = 16 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_entries", self.max_entries),
            ("max_manifest_bytes", self.max_manifest_bytes),
            ("max_entry_bytes", self.max_entry_bytes),
            ("max_total_bytes", self.max_total_bytes),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class BundleFile:
    """One caller-supplied portable file to place in a Ronin Bundle."""

    path: str
    media_type: str
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise TypeError("bundle file data must be bytes")
        # Reuse canonical path/media validation without making this adapter part
        # of identity construction.
        BundleEntry(self.path, self.media_type, "sha256", "0" * 64, len(self.data))
        if self.path == BUNDLE_MANIFEST_PATH:
            raise ValueError("bundle payload path is reserved for the manifest")


def _archive_path(value: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise BundleIntegrityError("archive member path is invalid")
    if value.startswith("/") or "\\" in value:
        raise BundleIntegrityError("archive member path must be relative and use forward slashes")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise BundleIntegrityError("archive member path contains unsafe components")
    return value


def _zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _canonical_files(files: Iterable[BundleFile]) -> tuple[BundleFile, ...]:
    items = tuple(sorted(files, key=lambda item: item.path))
    paths = [item.path for item in items]
    if len(paths) != len(set(paths)):
        raise ValueError("bundle file paths must be unique")
    return items


def _manifest_for(
    files: tuple[BundleFile, ...],
    migration_reports: Iterable[MigrationReport],
) -> RoninBundleManifest:
    entries = tuple(
        BundleEntry(
            path=item.path,
            media_type=item.media_type,
            digest_algorithm="sha256",
            digest=hashlib.sha256(item.data).hexdigest(),
            size_bytes=len(item.data),
        )
        for item in files
    )
    return RoninBundleManifest(entries, tuple(migration_reports))


def write_bundle(
    path: Path,
    files: Iterable[BundleFile],
    *,
    migration_reports: Iterable[MigrationReport] = (),
) -> RoninBundleManifest:
    """Write a byte-deterministic ``.roninbundle`` ZIP archive atomically.

    Stored (uncompressed) ZIP entries, fixed metadata, canonical JSON and sorted
    paths make the archive bytes deterministic for identical inputs.
    """

    items = _canonical_files(files)
    manifest = _manifest_for(items, migration_reports)
    manifest_bytes = manifest.to_json().encode("utf-8")

    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with temporary.open("w+b") as handle:
            with zipfile.ZipFile(handle, mode="w", allowZip64=True) as archive:
                archive.writestr(_zip_info(BUNDLE_MANIFEST_PATH), manifest_bytes)
                for item in items:
                    archive.writestr(_zip_info(item.path), item.data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def _checked_infos(
    archive: zipfile.ZipFile,
    limits: BundleReadLimits,
) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > limits.max_entries + 1:
        raise BundleIntegrityError("bundle contains too many archive members")
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise BundleIntegrityError("bundle archive member paths must be unique")

    checked: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in infos:
        name = _archive_path(info.filename)
        if info.is_dir():
            raise BundleIntegrityError("bundle archive must not contain directory entries")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise BundleIntegrityError("bundle archive must not contain symbolic links")
        if info.flag_bits & 0x1:
            raise BundleIntegrityError("encrypted bundle entries are not supported")
        if info.compress_type not in _ALLOWED_COMPRESSION:
            raise BundleIntegrityError("unsupported bundle compression method")
        if info.file_size < 0 or info.file_size > limits.max_entry_bytes:
            raise BundleIntegrityError("bundle archive member exceeds the configured size limit")
        total += info.file_size
        if total > limits.max_total_bytes:
            raise BundleIntegrityError("bundle exceeds the configured total size limit")
        checked[name] = info
    return checked


def _read_manifest(
    archive: zipfile.ZipFile,
    infos: dict[str, zipfile.ZipInfo],
    limits: BundleReadLimits,
) -> RoninBundleManifest:
    info = infos.get(BUNDLE_MANIFEST_PATH)
    if info is None:
        raise BundleIntegrityError("bundle manifest is missing")
    if info.file_size > limits.max_manifest_bytes:
        raise BundleIntegrityError("bundle manifest exceeds the configured size limit")
    try:
        payload = archive.read(info).decode("utf-8")
        manifest = RoninBundleManifest.from_json(payload)
    except (UnicodeDecodeError, ValueError) as exc:
        raise BundleIntegrityError("bundle manifest is invalid") from exc
    if any(entry.path == BUNDLE_MANIFEST_PATH for entry in manifest.entries):
        raise BundleIntegrityError("bundle manifest cannot describe itself as a payload entry")
    return manifest


def _verify_payloads(
    archive: zipfile.ZipFile,
    infos: dict[str, zipfile.ZipInfo],
    manifest: RoninBundleManifest,
    limits: BundleReadLimits,
) -> None:
    expected = {BUNDLE_MANIFEST_PATH, *(entry.path for entry in manifest.entries)}
    if set(infos) != expected:
        raise BundleIntegrityError("archive members do not exactly match the bundle manifest")

    total = 0
    for entry in manifest.entries:
        if entry.digest_algorithm != "sha256":
            raise BundleIntegrityError("unsupported bundle digest algorithm")
        info = infos[entry.path]
        if info.file_size != entry.size_bytes:
            raise BundleIntegrityError("bundle entry size does not match the manifest")
        if entry.size_bytes > limits.max_entry_bytes:
            raise BundleIntegrityError("bundle entry exceeds the configured size limit")
        total += entry.size_bytes
        if total > limits.max_total_bytes:
            raise BundleIntegrityError("bundle payload exceeds the configured total size limit")

        digest = hashlib.sha256()
        observed = 0
        with archive.open(info, mode="r") as source:
            while True:
                chunk = source.read(_CHUNK_BYTES)
                if not chunk:
                    break
                observed += len(chunk)
                if observed > entry.size_bytes or observed > limits.max_entry_bytes:
                    raise BundleIntegrityError("bundle entry expanded beyond its declared size")
                digest.update(chunk)
        if observed != entry.size_bytes:
            raise BundleIntegrityError("bundle entry byte count does not match the manifest")
        if digest.hexdigest() != entry.digest:
            raise BundleIntegrityError("bundle entry digest verification failed")


def verify_bundle(
    path: Path,
    *,
    limits: BundleReadLimits = BundleReadLimits(),
) -> RoninBundleManifest:
    """Verify archive structure plus every payload digest without extracting it."""

    try:
        with zipfile.ZipFile(path, mode="r", allowZip64=True) as archive:
            infos = _checked_infos(archive, limits)
            manifest = _read_manifest(archive, infos, limits)
            _verify_payloads(archive, infos, manifest, limits)
            return manifest
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise BundleIntegrityError("bundle archive is unreadable") from exc


def _safe_target(root: Path, relative: str) -> Path:
    candidate = root.joinpath(*relative.split("/"))
    resolved_parent = candidate.parent.resolve()
    try:
        resolved_parent.relative_to(root.resolve())
    except ValueError as exc:
        raise BundleIntegrityError("bundle extraction would escape the target directory") from exc
    return candidate


def extract_bundle(
    path: Path,
    target: Path,
    *,
    limits: BundleReadLimits = BundleReadLimits(),
) -> RoninBundleManifest:
    """Verify and atomically extract payload entries into a new target directory."""

    manifest = verify_bundle(path, limits=limits)
    destination = target.expanduser().resolve()
    if destination.exists():
        raise FileExistsError("bundle extraction target already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".ronin-bundle-", dir=destination.parent))
    try:
        with zipfile.ZipFile(path, mode="r", allowZip64=True) as archive:
            for entry in manifest.entries:
                output = _safe_target(temporary, entry.path)
                output.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                written = 0
                with archive.open(entry.path, mode="r") as source, output.open("xb") as sink:
                    while True:
                        chunk = source.read(_CHUNK_BYTES)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > entry.size_bytes:
                            raise BundleIntegrityError(
                                "bundle entry expanded beyond its declared size during extraction"
                            )
                        digest.update(chunk)
                        sink.write(chunk)
                    sink.flush()
                    os.fsync(sink.fileno())
                if written != entry.size_bytes or digest.hexdigest() != entry.digest:
                    raise BundleIntegrityError("bundle entry changed during extraction")
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


__all__ = (
    "BUNDLE_MANIFEST_PATH",
    "BundleFile",
    "BundleIntegrityError",
    "BundleReadLimits",
    "extract_bundle",
    "verify_bundle",
    "write_bundle",
)
