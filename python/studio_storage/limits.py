"""Shared bounds for supported v0.1 storage adapters."""

from __future__ import annotations

MAX_EVIDENCE_REFS_PER_RUN = 100
MAX_CELL_RESULTS_PER_RUN = 10_000

__all__ = ("MAX_CELL_RESULTS_PER_RUN", "MAX_EVIDENCE_REFS_PER_RUN")
