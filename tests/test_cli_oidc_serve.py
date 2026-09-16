from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import studio_cli.entrypoint as entrypoint
from studio_cli.oidc_serve import build_oidc_server_from_env
from studio_core import Workspace, WorkspaceId
from studio_orchestrator import Instant
from studio_storage import SqliteWorkspaceStore

_NOW = Instant("2026-09-13T17:20:00.000000Z")
_WS = WorkspaceId("workspace-cli-oidc")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _configure_oidc(monkeypatch, tmp_path: Path, *, workspace: bool = True) -> Path:
    database = tmp_path / "ronin.sqlite3"
    jwks = tmp_path / "jwks.json"
    jwks.write_text(json.dumps({"keys": []}), encoding="utf-8")
    monkeypatch.setenv("RONIN_AUTH_MODE", "oidc")
    monkeypatch.setenv("RONIN_DB", str(database))
    monkeypatch.setenv("RONIN_HOST", "127.0.0.1")
    monkeypatch.setenv("RONIN_PORT", str(_free_port()))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", str(_WS))
    monkeypatch.setenv("RONIN_OIDC_ISSUER", "https://issuer.example")
    monkeypatch.setenv("RONIN_OIDC_AUDIENCE", "ronin")
    monkeypatch.setenv("RONIN_OIDC_JWKS_FILE", str(jwks))
    if workspace:
        store = SqliteWorkspaceStore(database, migration_now=_NOW)
        store.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    return database


def test_entrypoint_defaults_serve_to_existing_static_dispatcher(monkeypatch) -> None:
    monkeypatch.delenv("RONIN_AUTH_MODE", raising=False)
    calls: list[tuple[str, ...]] = []

    def delegated(args):
        calls.append(tuple(args))
        return 17

    monkeypatch.setattr(entrypoint, "_main", delegated)
    assert entrypoint.main(("serve",)) == 17
    assert calls == [("serve",)]


def test_entrypoint_selects_oidc_serve_only_when_explicit(monkeypatch) -> None:
    monkeypatch.setenv("RONIN_AUTH_MODE", "oidc")
    calls: list[str] = []
    monkeypatch.setattr(entrypoint, "serve_oidc_from_env", lambda: calls.append("oidc") or 23)

    assert entrypoint.main(("serve",)) == 23
    assert calls == ["oidc"]


def test_entrypoint_rejects_unknown_serve_mode_but_not_other_commands(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("RONIN_AUTH_MODE", "unknown")
    assert entrypoint.main(("serve",)) == 2
    assert "RONIN_AUTH_MODE must be static or oidc" in capsys.readouterr().err

    monkeypatch.setattr(entrypoint, "_main", lambda args: 31 if tuple(args) == ("doctor",) else 99)
    assert entrypoint.main(("doctor",)) == 31


def test_build_oidc_server_uses_preprovisioned_active_workspace(monkeypatch, tmp_path: Path) -> None:
    _configure_oidc(monkeypatch, tmp_path)
    server = build_oidc_server_from_env()
    try:
        assert server.workspace_id == _WS
    finally:
        server.server_close()


def test_build_oidc_server_rejects_missing_and_archived_workspace(
    monkeypatch, tmp_path: Path
) -> None:
    database = _configure_oidc(monkeypatch, tmp_path, workspace=False)
    with pytest.raises(ValueError, match="provisioned workspace"):
        build_oidc_server_from_env()

    store = SqliteWorkspaceStore(database, migration_now=_NOW)
    store.create_workspace(Workspace(_WS, "Workspace"), now=_NOW)
    store.update_workspace(Workspace(_WS, "Workspace", state="archived"), now=_NOW)
    with pytest.raises(ValueError, match="active workspace"):
        build_oidc_server_from_env()


def test_build_oidc_server_rejects_invalid_jwks_at_startup(monkeypatch, tmp_path: Path) -> None:
    _configure_oidc(monkeypatch, tmp_path)
    jwks = Path(str(tmp_path / "jwks.json"))
    jwks.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid RONIN_OIDC_JWKS_FILE"):
        build_oidc_server_from_env()


@pytest.mark.parametrize(
    "missing",
    ["RONIN_WORKSPACE_ID", "RONIN_OIDC_ISSUER", "RONIN_OIDC_AUDIENCE", "RONIN_OIDC_JWKS_FILE"],
)
def test_build_oidc_server_requires_oidc_configuration(
    monkeypatch, tmp_path: Path, missing: str
) -> None:
    _configure_oidc(monkeypatch, tmp_path)
    monkeypatch.delenv(missing)

    with pytest.raises(ValueError, match=missing):
        build_oidc_server_from_env()
