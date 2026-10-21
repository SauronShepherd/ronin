from __future__ import annotations

from pathlib import Path

import pytest
from studio_cli import (
    CliError,
    _serve,
    _sql_engine_from_environment,
    _worker_config_from_environment,
)


def test_server_reports_postgres_initialization_failure_instead_of_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RONIN_POSTGRES_DSN", "postgresql://example.invalid/ronin")

    with pytest.raises(CliError, match="PostgreSQL backend initialization failed"):
        _serve()


def test_postgres_backend_requires_an_explicit_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "postgres")
    monkeypatch.delenv("RONIN_POSTGRES_DSN", raising=False)

    with pytest.raises(CliError, match="RONIN_POSTGRES_DSN is required"):
        _serve()


def test_worker_postgres_backend_requires_an_explicit_dsn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "postgres")
    monkeypatch.delenv("RONIN_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_IMAGE", f"ronin-probe@sha256:{'a' * 64}")

    with pytest.raises(CliError, match="RONIN_POSTGRES_DSN is required"):
        _worker_config_from_environment()


def test_worker_postgres_backend_uses_configured_dsn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dsn = "postgresql://ronin:secret@localhost:5432/ronin"
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("RONIN_POSTGRES_DSN", dsn)
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_IMAGE", f"ronin-probe@sha256:{'a' * 64}")

    assert _worker_config_from_environment().postgres_dsn == dsn


def test_worker_defaults_to_sqlite_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("RONIN_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("RONIN_POSTGRES_DSN", raising=False)
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_IMAGE", f"ronin-probe@sha256:{'a' * 64}")

    assert _worker_config_from_environment().postgres_dsn is None


def test_sql_parquet_root_is_optional_and_directory_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert _sql_engine_from_environment() is None
    monkeypatch.setenv("RONIN_SQL_PARQUET_ROOT", " ")
    assert _sql_engine_from_environment() is None
    monkeypatch.setenv("RONIN_SQL_PARQUET_ROOT", str(tmp_path))
    engine = _sql_engine_from_environment()
    assert engine is not None
    engine.close()
    monkeypatch.setenv("RONIN_SQL_PARQUET_ROOT", str(tmp_path / "missing"))
    with pytest.raises(CliError, match="existing directory"):
        _sql_engine_from_environment()
