from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools import ronin_appliance_backup as appliance_backup


def _valid_bundle(tmp_path: Path) -> Path:
    import json

    from tools.ronin_appliance_backup import _data_inventory, _sha256_file

    bundle = tmp_path / "bundle"
    data = bundle / "data"
    data.mkdir(parents=True)
    database = bundle / "postgres.dump"
    database.write_bytes(b"valid dump")
    digest = hashlib.sha256(database.read_bytes()).hexdigest()
    database.with_name("postgres.dump.sha256").write_text(
        f"{digest}  postgres.dump\n", encoding="ascii"
    )
    entries, tree_digest = _data_inventory(data)
    (bundle / "ronin-appliance-backup.json").write_text(
        json.dumps(
            {
                "schema": "ronin.appliance-backup/v1",
                "database_file": "postgres.dump",
                "database_sha256": _sha256_file(database),
                "data_directory": "data",
                "data_tree_sha256": tree_digest,
                "data_files": entries,
                "artifact_backend": "local",
            }
        ),
        encoding="utf-8",
    )
    return bundle


def test_invalid_appliance_dump_sidecar_is_rejected_before_quiescing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = _valid_bundle(tmp_path)
    (bundle / "postgres.dump.sha256").write_text("0" * 64 + "  postgres.dump\n", encoding="ascii")
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(appliance_backup, "_compose_config", forbidden)
    with pytest.raises(ValueError, match="checksum mismatch"):
        appliance_backup.restore_appliance(tmp_path / "compose.yaml", bundle, force=True)
    assert called is False


def test_compose_resume_order_restores_dependencies_before_worker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    observed: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> None:
        observed.append(command)

    monkeypatch.setattr(appliance_backup, "_run", fake_run)
    appliance_backup._resume(tmp_path / "compose.yaml", {}, ["worker", "server", "runner-broker"])

    assert observed == [
        [
            "docker",
            "compose",
            "-f",
            str(tmp_path / "compose.yaml"),
            "start",
            "runner-broker",
            "server",
            "worker",
        ]
    ]


def test_compose_config_rejects_external_s3_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config: dict[str, Any] = {
        "services": {
            "postgres": {},
            "server": {"volumes": [{"target": "/var/lib/ronin"}]},
            "worker": {"environment": {"RONIN_ARTIFACT_BACKEND": "s3"}},
        }
    }

    def fake_run(_command: list[str], **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(stdout=json.dumps(config))

    monkeypatch.setattr(appliance_backup, "_run", fake_run)
    with pytest.raises(ValueError, match="back up the configured S3 store separately"):
        appliance_backup._compose_config(tmp_path / "compose.yaml", {})


def test_failed_appliance_restore_keeps_writers_stopped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    events: list[str] = []
    compose_file = tmp_path / "compose.yaml"
    bundle = tmp_path / "bundle"
    database = tmp_path / "postgres.dump"
    data = tmp_path / "data"
    config: dict[str, Any] = {
        "services": {"postgres": {}, "server": {}, "worker": {}, "runner-broker": {}}
    }
    monkeypatch.setattr(appliance_backup, "_validate_bundle", lambda _bundle: (database, data))
    monkeypatch.setattr(appliance_backup, "_compose_config", lambda *_args: config)
    monkeypatch.setattr(
        appliance_backup,
        "_running_writer_services",
        lambda *_args: ["worker", "server", "runner-broker"],
    )
    monkeypatch.setattr(appliance_backup, "_quiesce", lambda *_args: events.append("stop"))
    monkeypatch.setattr(
        appliance_backup,
        "_replace_data_volume",
        lambda *_args, **_kwargs: events.append("replace-volume"),
    )

    def fail_restore(*_args: object, **_kwargs: object) -> None:
        events.append("restore-database")
        raise RuntimeError("restore failed")

    monkeypatch.setattr(appliance_backup, "restore_postgres", fail_restore)
    monkeypatch.setattr(appliance_backup, "_resume", lambda *_args: events.append("start"))

    with pytest.raises(RuntimeError, match="restore failed"):
        appliance_backup.restore_appliance(compose_file, bundle, force=True)

    assert events == ["stop", "replace-volume", "restore-database"]
