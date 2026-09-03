"""Pure import helpers for stable portable notebook identity."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .dependencies import CellKind, Notebook, NotebookCell
from .identity import CellIdentityAnchor, allocate_cell_ids
from .serialization import NotebookDocument


@dataclass(frozen=True, slots=True)
class NotebookImportCell:
    """Provider-neutral imported cell keyed by a source-stable external reference."""

    reference: str
    kind: CellKind
    source: str
    dependency_references: tuple[str, ...] = ()
    language: str | None = None

    def __post_init__(self) -> None:
        if not self.reference or self.reference.strip() != self.reference:
            raise ValueError("import cell reference must be non-empty and trimmed")
        if "\n" in self.reference or "\r" in self.reference:
            raise ValueError("import cell reference must be single-line")
        canonical_dependencies = tuple(sorted(self.dependency_references))
        if len(set(canonical_dependencies)) != len(canonical_dependencies):
            raise ValueError("import dependency references must be unique")
        if self.reference in canonical_dependencies:
            raise ValueError("import cell may not depend on itself")
        object.__setattr__(self, "dependency_references", canonical_dependencies)


def import_notebook(namespace: str, cells: Sequence[NotebookImportCell]) -> NotebookDocument:
    """Build a canonical document from explicit stable source-cell references."""
    identities = tuple(CellIdentityAnchor("import", namespace, cell.reference) for cell in cells)
    cell_ids = allocate_cell_ids(identities)
    by_reference = {
        cell.reference: cell_id for cell, cell_id in zip(cells, cell_ids, strict=True)
    }
    if len(by_reference) != len(cells):
        raise ValueError("import cell references must be unique")

    imported_cells: list[NotebookCell] = []
    for cell, cell_id in zip(cells, cell_ids, strict=True):
        missing = tuple(
            reference for reference in cell.dependency_references if reference not in by_reference
        )
        if missing:
            raise ValueError(
                f"import cell {cell.reference} has unknown dependency references: {list(missing)}"
            )
        imported_cells.append(
            NotebookCell(
                id=cell_id,
                kind=cell.kind,
                source=cell.source,
                dependencies=tuple(by_reference[reference] for reference in cell.dependency_references),
                language=cell.language,
            )
        )
    return NotebookDocument(Notebook(tuple(imported_cells)), identities)
