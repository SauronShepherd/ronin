"""Immutable notebook cells and deterministic dependency analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

CellKind: TypeAlias = Literal["code", "markdown", "sql"]
ViolationCode: TypeAlias = Literal[
    "unknown_dependency",
    "non_executable_dependency",
    "dependency_cycle",
]


@dataclass(frozen=True, order=True, slots=True)
class CellId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value:
            raise ValueError("cell id must be non-empty and trimmed")
        if "\n" in self.value or "\r" in self.value:
            raise ValueError("cell id must be single-line")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class NotebookCell:
    id: CellId
    kind: CellKind
    source: str
    dependencies: tuple[CellId, ...] = ()
    language: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"code", "markdown", "sql"}:
            raise ValueError("unsupported notebook cell kind")
        canonical_dependencies = tuple(sorted(self.dependencies))
        if len(set(canonical_dependencies)) != len(canonical_dependencies):
            raise ValueError("cell dependencies must be unique")
        if self.id in canonical_dependencies:
            raise ValueError("cell may not depend on itself")
        if self.kind == "markdown":
            if self.language is not None:
                raise ValueError("markdown cells may not declare an execution language")
            if canonical_dependencies:
                raise ValueError("markdown cells may not declare execution dependencies")
        if self.kind in {"code", "sql"}:
            if (
                self.language is None
                or not self.language
                or self.language.strip() != self.language
            ):
                raise ValueError("executable cells require a non-empty trimmed language")
        object.__setattr__(self, "dependencies", canonical_dependencies)


@dataclass(frozen=True, slots=True)
class Notebook:
    cells: tuple[NotebookCell, ...] = ()

    def __post_init__(self) -> None:
        ids = tuple(cell.id for cell in self.cells)
        if len(set(ids)) != len(ids):
            raise ValueError("notebook cell ids must be unique")


@dataclass(frozen=True, order=True, slots=True)
class CellDependencyViolation:
    code: ViolationCode
    cell_id: CellId
    dependency_id: CellId | None
    message: str


@dataclass(frozen=True, slots=True)
class NotebookDependencyAnalysis:
    execution_order: tuple[CellId, ...]
    levels: tuple[tuple[CellId, ...], ...]
    violations: tuple[CellDependencyViolation, ...]

    @property
    def is_valid(self) -> bool:
        return not self.violations


def analyze_notebook_dependencies(notebook: Notebook) -> NotebookDependencyAnalysis:
    """Resolve explicit executable-cell dependencies into stable execution evidence."""
    index = {cell.id: position for position, cell in enumerate(notebook.cells)}
    by_id = {cell.id: cell for cell in notebook.cells}
    executable_cells = tuple(cell for cell in notebook.cells if cell.kind != "markdown")
    violations: list[CellDependencyViolation] = []

    for cell in executable_cells:
        for dependency_id in cell.dependencies:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                violations.append(
                    CellDependencyViolation(
                        code="unknown_dependency",
                        cell_id=cell.id,
                        dependency_id=dependency_id,
                        message=f"cell {cell.id} depends on unknown cell {dependency_id}",
                    )
                )
            elif dependency.kind == "markdown":
                violations.append(
                    CellDependencyViolation(
                        code="non_executable_dependency",
                        cell_id=cell.id,
                        dependency_id=dependency_id,
                        message=(
                            f"cell {cell.id} depends on non-executable cell {dependency_id}"
                        ),
                    )
                )

    if violations:
        return NotebookDependencyAnalysis(
            (),
            (),
            tuple(
                sorted(
                    violations,
                    key=lambda item: (
                        item.code,
                        item.cell_id.value,
                        item.dependency_id.value if item.dependency_id is not None else "",
                    ),
                )
            ),
        )

    incoming = {cell.id: len(cell.dependencies) for cell in executable_cells}
    outgoing = {cell.id: [] for cell in executable_cells}
    for cell in executable_cells:
        for dependency_id in cell.dependencies:
            outgoing[dependency_id].append(cell.id)

    ready = sorted(
        (cell_id for cell_id, count in incoming.items() if count == 0),
        key=lambda cell_id: index[cell_id],
    )
    order: list[CellId] = []
    levels: list[tuple[CellId, ...]] = []
    while ready:
        current_level = tuple(ready)
        levels.append(current_level)
        order.extend(current_level)
        next_ready: list[CellId] = []
        for current in current_level:
            for dependent in sorted(outgoing[current], key=lambda cell_id: index[cell_id]):
                incoming[dependent] -= 1
                if incoming[dependent] == 0:
                    next_ready.append(dependent)
        ready = sorted(next_ready, key=lambda cell_id: index[cell_id])

    if len(order) != len(executable_cells):
        cyclic = tuple(cell.id for cell in executable_cells if incoming[cell.id] > 0)
        cycle_violations = tuple(
            CellDependencyViolation(
                code="dependency_cycle",
                cell_id=cell_id,
                dependency_id=None,
                message=f"cell {cell_id} participates in a dependency cycle",
            )
            for cell_id in cyclic
        )
        return NotebookDependencyAnalysis((), (), cycle_violations)

    return NotebookDependencyAnalysis(tuple(order), tuple(levels), ())
