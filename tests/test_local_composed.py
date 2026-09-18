from __future__ import annotations

from pathlib import Path

import pytest
from studio_cli.local_composed import build_local_composed_from_env


def _set_required_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", "workspace-test")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_TOKEN", "control-token")
    monkeypatch.setenv("RONIN_TOKEN", "job-token")
    monkeypatch.setenv(
        "RONIN_TOKEN_SCOPES",
        '{"grants":[{"actions":["read"],"resource":{"identifier":null,"kind":"*"},"version":1}],"version":1}',
    )
    monkeypatch.setenv("RONIN_PORT", "18080")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", "18081")


def test_build_local_composed_from_environment(monkeypatch, tmp_path: Path) -> None:
    _set_required_environment(monkeypatch, tmp_path)

    composition = build_local_composed_from_env()
    try:
        assert composition.job_server.server_address[1] == 18080
        assert composition.control_plane_server.server_address[1] == 18081
        assert not composition.ready
    finally:
        composition.job_server.server_close()
        composition.control_plane_server.server_close()


def test_build_local_composed_rejects_unsupported_permissions(monkeypatch, tmp_path: Path) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PERMISSIONS", "workspace.superuser")

    with pytest.raises(ValueError, match="unsupported permissions"):
        build_local_composed_from_env()


@pytest.mark.parametrize(
    ("name", "value"), [("RONIN_PORT", "0"), ("RONIN_CONTROL_PLANE_PORT", "65536")]
)
def test_build_local_composed_rejects_invalid_ports(
    monkeypatch, tmp_path: Path, name: str, value: str
) -> None:
    _set_required_environment(monkeypatch, tmp_path)
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match="must be between 1 and 65535"):
        build_local_composed_from_env()
