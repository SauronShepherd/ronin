"""Operational readiness checks for the supported SQLite control-plane store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_storage.sqlite import _SCHEMA_VERSION


def sqlite_ready(path: Path) -> bool:
    """Return whether the existing database is current and answers a bounded read."""
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=2.0)
    except (OSError, sqlite3.Error, ValueError):
        return False
    try:
        row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        if row is None or row[0] != _SCHEMA_VERSION:
            return False
        probe = connection.execute("SELECT 1 FROM jobs LIMIT 1").fetchone()
        if probe is None:
            probe = connection.execute("SELECT 1").fetchone()
        return probe == (1,)
    except sqlite3.Error:
        return False
    finally:
        connection.close()


__all__ = ("sqlite_ready",)
