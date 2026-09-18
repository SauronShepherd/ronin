from __future__ import annotations

import pytest
from studio_cli.local_composed import build_local_composed_from_env
from studio_server import LocalServerComposition


def _environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_TOKEN", "control-token")
    monkeypatch.setenv(
        "RONIN_TOKEN_SCOPES",
        (
            '{"version": 1, "grants": [{"actions": ['
            '"cancel", "evidence:read", "execute", "events", "list", "read", "submit"'
            '], "constraints": {}, "resource": '
            '{"identifier": null, "kind": "*"}, "version": 1}]}'
        ),
    )
    monkeypatch.setenv("RONIN_TOKEN", "job-token")


def test_build_local_composed_from_env_creates_two_surface_composition(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)

    composition = build_local_composed_from_env()

    assert isinstance(composition, LocalServerComposition)
    assert composition.job_server.server_address[1] == 8080
    assert composition.control_plane_server.server_address[1] == 8081
    composition.stop()


def test_build_local_composed_rejects_unknown_permission(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PERMISSIONS", "workspace.read,unknown")

    with pytest.raises(ValueError, match="unsupported permissions"):
        build_local_composed_from_env()


def test_build_local_composed_rejects_invalid_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _environment(monkeypatch, tmp_path)
    monkeypatch.setenv("RONIN_PORT", "0")

    with pytest.raises(ValueError, match="between 1 and 65535"):
        build_local_composed_from_env()
