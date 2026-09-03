"""Stable notebook-cell identity derived from explicit authoring/import provenance."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, TypeAlias

from .dependencies import CellId

CellIdentityBoundary: TypeAlias = Literal["authoring", "import"]


@dataclass(frozen=True, order=True, slots=True)
class CellIdentityAnchor:
    """Stable provenance supplied by the boundary that owns a notebook document."""

    boundary: CellIdentityBoundary
    namespace: str
    reference: str

    def __post_init__(self) -> None:
        if self.boundary not in {"authoring", "import"}:
            raise ValueError("cell identity boundary must be authoring or import")
        _require_identity_text(self.namespace, "namespace")
        _require_identity_text(self.reference, "reference")

    def cell_id(self) -> CellId:
        payload = (
            f"ronin-notebook-cell-v1\0{self.boundary}\0{self.namespace}\0{self.reference}".encode()
        )
        return CellId(sha256(payload).hexdigest())


def allocate_cell_ids(anchors: Sequence[CellIdentityAnchor]) -> tuple[CellId, ...]:
    """Derive stable cell IDs from explicit unique provenance anchors."""
    if len(set(anchors)) != len(anchors):
        raise ValueError("cell identity anchors must be unique within an allocation batch")
    return tuple(anchor.cell_id() for anchor in anchors)


def _require_identity_text(value: str, name: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"cell identity {name} must be non-empty and trimmed")
    if "\n" in value or "\r" in value:
        raise ValueError(f"cell identity {name} must be single-line")
