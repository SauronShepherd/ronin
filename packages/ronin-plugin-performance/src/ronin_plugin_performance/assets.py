"""Bounded asset inventory helpers for small-file and layout diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def inventory_asset(
    path: str | Path, *, max_files: int = 100_000, max_depth: int = 32
) -> dict[str, Any]:
    """Collect non-mutating file metrics from a local asset directory.

    The function intentionally reports truncation instead of pretending the
    inventory is complete when safety bounds are reached.
    """
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        files = [root]
    else:
        files = []
        for candidate in root.rglob("*"):
            if candidate.is_file() and len(candidate.relative_to(root).parts) <= max_depth:
                files.append(candidate)
            if len(files) >= max_files:
                break
    sizes = [item.stat().st_size for item in files]
    total = sum(sizes)
    return {
        "id": str(root),
        "file_count": len(files),
        "bytes": total,
        "average_file_bytes": total / len(files) if files else 0,
        "min_file_bytes": min(sizes) if sizes else 0,
        "max_file_bytes": max(sizes) if sizes else 0,
        "truncated": len(files) >= max_files and root.is_dir(),
        "max_files": max_files,
        "max_depth": max_depth,
    }
