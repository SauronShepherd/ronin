from __future__ import annotations

from pathlib import Path

import pytest
from studio_cli import CliError, _serve, _sql_engine_from_environment


def test_server_rejects_postgres_dsn_instead_of_silent_sqlite_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RONIN_POSTGRES_DSN", "postgresql://example.invalid/ronin")

    with pytest.raises(CliError, match="refusing to fall back to SQLite"):
        _serve()


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
