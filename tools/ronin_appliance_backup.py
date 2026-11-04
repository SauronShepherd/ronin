"""Create and restore a quiesced Ronin Compose appliance backup bundle.

The bundle covers the PostgreSQL logical dump and the local ``/var/lib/ronin``
volume. S3-backed artifacts live outside that volume and must be backed up by
the configured object-store provider separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.ronin_postgres_backup import backup as backup_postgres
from tools.ronin_postgres_backup import restore as restore_postgres
from tools.ronin_postgres_backup import verify_backup_checksum

_WRITER_SERVICES = ("worker", "server", "runner-broker")
_RESUME_ORDER = ("runner-broker", "server", "worker")
_VOLUME_ROOT = "/var/lib/ronin"
_MANIFEST_NAME = "ronin-appliance-backup.json"


def _run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True, env=env)  # noqa: S603


def _compose_prefix(compose_file: Path) -> list[str]:
    return ["docker", "compose", "-f", str(compose_file)]


def _compose_config(compose_file: Path, env: dict[str, str]) -> dict[str, Any]:
    result = _run(_compose_prefix(compose_file) + ["config", "--format", "json"], env=env)
    config: dict[str, Any] = json.loads(result.stdout)
    services = config.get("services")
    if not isinstance(services, dict) or not {"postgres", "server"}.issubset(services):
        raise ValueError("appliance Compose file must define postgres and server services")
    server = services["server"]
    mounts = server.get("volumes", []) if isinstance(server, dict) else []
    if not any(isinstance(mount, dict) and mount.get("target") == _VOLUME_ROOT for mount in mounts):
        raise ValueError(f"server must persist the {_VOLUME_ROOT} data volume")
    worker = services.get("worker", {})
    worker_env = worker.get("environment", {}) if isinstance(worker, dict) else {}
    backend = (
        worker_env.get("RONIN_ARTIFACT_BACKEND", "local")
        if isinstance(worker_env, dict)
        else "local"
    )
    if str(backend).strip().casefold() != "local":
        raise ValueError(
            "appliance bundles cover local artifacts only; back up the configured "
            "S3 store separately"
        )
    return config


def _running_writer_services(
    compose_file: Path, env: dict[str, str], services: dict[str, Any]
) -> list[str]:
    result = _run(
        _compose_prefix(compose_file) + ["ps", "--status", "running", "--services"], env=env
    )
    running = set(result.stdout.splitlines())
    return [service for service in _WRITER_SERVICES if service in services and service in running]


def _quiesce(compose_file: Path, env: dict[str, str], writers: list[str]) -> None:
    if writers:
        _run(_compose_prefix(compose_file) + ["stop", "--timeout", "60", *writers], env=env)


def _resume(compose_file: Path, env: dict[str, str], writers: list[str]) -> None:
    ordered = [service for service in _RESUME_ORDER if service in writers]
    if ordered:
        _run(_compose_prefix(compose_file) + ["start", *ordered], env=env)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _data_inventory(root: Path) -> tuple[list[dict[str, str]], str]:
    if not root.is_dir():
        raise FileNotFoundError(f"appliance data volume copy is missing: {root}")
    entries: list[dict[str, str]] = []
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise ValueError(f"appliance data volume contains an unsupported symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        file_digest = _sha256_file(path)
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(bytes.fromhex(file_digest))
        entries.append({"path": relative, "sha256": file_digest})
    return entries, digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def backup_appliance(compose_file: Path, destination: Path) -> Path:
    compose_file = compose_file.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("appliance backup destination must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    config = _compose_config(compose_file, env)
    services = config["services"]
    writers = _running_writer_services(compose_file, env, services)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    )
    published = False
    try:
        _quiesce(compose_file, env, writers)
        database = temporary / "postgres.dump"
        backup_postgres(compose_file, database)
        data = temporary / "data"
        data.mkdir()
        _run(
            _compose_prefix(compose_file) + ["cp", f"server:{_VOLUME_ROOT}/.", str(data)],
            env=env,
        )
        data_files, data_digest = _data_inventory(data)
        manifest = {
            "schema": "ronin.appliance-backup/v1",
            "created_at": datetime.now(UTC).isoformat(),
            "database_file": database.name,
            "database_sha256": _sha256_file(database),
            "data_directory": data.name,
            "data_tree_sha256": data_digest,
            "data_files": data_files,
            "artifact_backend": "local",
        }
        _atomic_json(temporary / _MANIFEST_NAME, manifest)
        temporary.replace(destination)
        published = True
    finally:
        if not published:
            shutil.rmtree(temporary, ignore_errors=True)
        _resume(compose_file, env, writers)
    return destination


def _validate_bundle(bundle: Path) -> tuple[Path, Path]:
    manifest_path = bundle / _MANIFEST_NAME
    database = bundle / "postgres.dump"
    data = bundle / "data"
    if not manifest_path.is_file() or not database.is_file() or not data.is_dir():
        raise ValueError("appliance backup bundle is incomplete")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "ronin.appliance-backup/v1"
        or manifest.get("database_file") != database.name
        or manifest.get("artifact_backend") != "local"
    ):
        raise ValueError("unsupported appliance backup manifest")
    sidecar_digest = verify_backup_checksum(database)
    if sidecar_digest != manifest.get("database_sha256"):
        raise ValueError("appliance database dump checksum mismatch")
    entries, tree_digest = _data_inventory(data)
    if tree_digest != manifest.get("data_tree_sha256") or entries != manifest.get("data_files"):
        raise ValueError("appliance data volume checksum mismatch")
    return database, data


def _replace_data_volume(
    compose_file: Path, env: dict[str, str], data: Path, *, restore_id: str
) -> None:
    stage_name = f".ronin-restore-{restore_id}"
    stage_path = f"{_VOLUME_ROOT}/{stage_name}"
    _run(
        _compose_prefix(compose_file) + ["cp", str(data) + "/.", f"server:{stage_path}"],
        env=env,
    )
    script = (
        "import os,pathlib,shutil;"
        f"root=pathlib.Path({_VOLUME_ROOT!r});stage=root/{stage_name!r};"
        "assert stage.is_dir() and stage.parent==root;"
        "[(shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()) "
        "for p in root.iterdir() if p!=stage];"
        "[(shutil.move(str(p),str(root/p.name))) for p in stage.iterdir()];"
        "stage.rmdir();"
        "[(os.chown(p,65532,65532,follow_symlinks=False)) for p in root.rglob('*')];"
        "os.chown(root,65532,65532)"
    )
    _run(
        _compose_prefix(compose_file)
        + [
            "run",
            "--rm",
            "--no-deps",
            "--user",
            "0:0",
            "--entrypoint",
            "python",
            "server",
            "-c",
            script,
        ],
        env=env,
    )


def restore_appliance(compose_file: Path, bundle: Path, *, force: bool) -> None:
    if not force:
        raise ValueError("appliance restore is destructive; pass --force explicitly")
    compose_file = compose_file.resolve()
    bundle = bundle.resolve()
    database, data = _validate_bundle(bundle)
    env = os.environ.copy()
    config = _compose_config(compose_file, env)
    services = config["services"]
    writers = _running_writer_services(compose_file, env, services)
    restore_id = uuid.uuid4().hex[:12]
    restored = False
    try:
        _quiesce(compose_file, env, writers)
        _replace_data_volume(compose_file, env, data, restore_id=restore_id)
        restore_postgres(compose_file, database, force=True)
        restored = True
    finally:
        if restored:
            _resume(compose_file, env, writers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, default=Path("compose.yaml"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backup-appliance", type=Path, metavar="DIRECTORY")
    mode.add_argument("--restore-appliance", type=Path, metavar="DIRECTORY")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    _required = os.environ.get("RONIN_TOKEN", "").strip()
    if not _required:
        raise ValueError("RONIN_TOKEN must be set to a non-empty trimmed value")
    if not os.environ.get("RONIN_RUNNER_BROKER_TOKEN", "").strip():
        raise ValueError("RONIN_RUNNER_BROKER_TOKEN must be set to a non-empty trimmed value")
    if args.backup_appliance is not None:
        backup_appliance(args.compose_file, args.backup_appliance)
    else:
        restore_appliance(args.compose_file, args.restore_appliance, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
