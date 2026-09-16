"""Safe backup and restore primitives for the reference SQLite deployment."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


def backup_sqlite(source: Path, destination: Path) -> Path:
    """Create a consistent SQLite backup and atomically publish it."""
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("backup destination must differ from source")
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with (
            closing(sqlite3.connect(source)) as source_db,
            closing(sqlite3.connect(temporary)) as target_db,
        ):
            source_db.backup(target_db)
            if target_db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("SQLite backup failed integrity check")
            target_db.commit()
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def restore_sqlite(backup: Path, destination: Path) -> Path:
    """Restore a verified backup to a new or replaced SQLite database atomically."""
    backup = backup.resolve()
    destination = destination.resolve()
    if backup == destination:
        raise ValueError("restore destination must differ from backup")
    if not backup.is_file():
        raise FileNotFoundError(backup)
    with closing(sqlite3.connect(backup)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("SQLite backup failed integrity check")
    return backup_sqlite(backup, destination)


__all__ = ["backup_sqlite", "restore_sqlite"]
