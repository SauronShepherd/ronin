"""Compatibility exports for canonical SQLite evidence storage."""

from __future__ import annotations

from studio_storage.fenced_sqlite import SqliteJobStore
from studio_storage.limits import MAX_EVIDENCE_REFS_PER_RUN

__all__ = ("MAX_EVIDENCE_REFS_PER_RUN", "SqliteJobStore")
