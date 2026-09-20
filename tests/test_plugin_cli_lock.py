from __future__ import annotations

import json
from pathlib import Path

from studio_cli import main


def test_plugins_lock_and_validate_round_trip(tmp_path: Path, capsys) -> None:
    lock_path = tmp_path / "plugin-lock.json"

    assert main(["plugins", "lock", "--file", str(lock_path)]) == 0
    created = capsys.readouterr()
    assert "plugin lock written" in created.out
    assert json.loads(lock_path.read_text(encoding="utf-8"))["schema_version"] == 1

    assert main(["plugins", "validate", "--file", str(lock_path)]) == 0
    validated = capsys.readouterr()
    assert "validated" in validated.out


def test_plugins_rollback_restores_snapshot(tmp_path: Path, capsys) -> None:
    snapshot = tmp_path / "snapshot.json"
    target = tmp_path / "active.json"

    assert main(["plugins", "lock", "--file", str(snapshot)]) == 0
    capsys.readouterr()
    assert main(["plugins", "rollback", str(snapshot), "--file", str(target)]) == 0

    assert target.read_text(encoding="utf-8") == snapshot.read_text(encoding="utf-8")
    assert "plugin lock restored" in capsys.readouterr().out
