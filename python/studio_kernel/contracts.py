"""Typed kernel preparation and execution-evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from studio_core import ResolvedRuntimeSnapshot
from studio_notebook import CellId, NotebookCell, NotebookDocument, analyze_notebook_dependencies

from .reproducibility import ExecutionAttemptId, ExecutionReproducibilitySnapshot

ExecutionState: TypeAlias = Literal["succeeded", "failed", "cancelled"]
EvidenceKind: TypeAlias = Literal[
    "log",
    "metric",
    "trace",
    "lineage",
    "output",
    "resource",
    "cost",
]


def _require_text(value: str, name: str) -> None:
    if not value or value.strip() != value or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")


@dataclass(frozen=True, slots=True)
class RepositoryRevision:
    """Portable Git identity captured before notebook execution."""

    commit: str
    dirty_patch_sha256: str | None = None

    def __post_init__(self) -> None:
        if len(self.commit) not in {40, 64} or any(
            ch not in "0123456789abcdef" for ch in self.commit
        ):
            raise ValueError(
                "repository commit must be a lowercase 40- or 64-character hex object id"
            )
        if self.dirty_patch_sha256 is not None and (
            len(self.dirty_patch_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in self.dirty_patch_sha256)
        ):
            raise ValueError("dirty patch digest must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True, order=True, slots=True)
class KernelDirectiveField:
    name: str
    value: str

    def __post_init__(self) -> None:
        _require_text(self.name, "directive field name")
        if "\x00" in self.value:
            raise ValueError("directive field value must not contain NUL")


@dataclass(frozen=True, slots=True)
class KernelDirective:
    """Adapter-owned normalized instruction separate from authored notebook intent."""

    adapter_id: str
    kind: str
    fields: tuple[KernelDirectiveField, ...] = ()
    required_permissions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.adapter_id, "kernel adapter id")
        _require_text(self.kind, "kernel directive kind")
        fields = tuple(sorted(self.fields))
        if len({field.name for field in fields}) != len(fields):
            raise ValueError("kernel directive field names must be unique")
        permissions = tuple(sorted(self.required_permissions))
        if len(set(permissions)) != len(permissions):
            raise ValueError("kernel directive permissions must be unique")
        for permission in permissions:
            _require_text(permission, "kernel directive permission")
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "required_permissions", permissions)


@dataclass(frozen=True, slots=True)
class PreparedCell:
    cell_id: CellId
    executable_source: str
    directive: KernelDirective


class KernelRequestAdapter(Protocol):
    """Adapter boundary for language/magic parsing and request preparation."""

    @property
    def adapter_id(self) -> str: ...

    def prepare(self, cell: NotebookCell) -> PreparedCell: ...


@dataclass(frozen=True, slots=True)
class CellExecutionRequest:
    cell_id: CellId
    authored_source: str
    executable_source: str
    language: str
    dependencies: tuple[CellId, ...]
    directive: KernelDirective


@dataclass(frozen=True, slots=True)
class NotebookExecutionRequest:
    document: NotebookDocument
    runtime: ResolvedRuntimeSnapshot
    repository: RepositoryRevision
    attempt_id: ExecutionAttemptId
    reproducibility: ExecutionReproducibilitySnapshot
    cells: tuple[CellExecutionRequest, ...]


@dataclass(frozen=True, order=True, slots=True)
class ExecutionEvidenceReference:
    kind: EvidenceKind
    ref: str

    def __post_init__(self) -> None:
        if self.kind not in {"log", "metric", "trace", "lineage", "output", "resource", "cost"}:
            raise ValueError("unsupported execution evidence kind")
        _require_text(self.ref, "execution evidence reference")


@dataclass(frozen=True, slots=True)
class CellExecutionResult:
    cell_id: CellId
    state: ExecutionState
    failure_code: str | None = None
    evidence: tuple[ExecutionEvidenceReference, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("unsupported cell execution state")
        if self.state == "failed":
            if self.failure_code is None:
                raise ValueError("failed cell execution requires a normalized failure code")
            _require_text(self.failure_code, "failure code")
        elif self.failure_code is not None:
            raise ValueError("non-failed cell execution may not contain a failure code")
        evidence = tuple(sorted(self.evidence))
        if len(set(evidence)) != len(evidence):
            raise ValueError("cell execution evidence references must be unique")
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True, slots=True)
class NotebookExecutionEvidence:
    request: NotebookExecutionRequest
    results: tuple[CellExecutionResult, ...]

    def __post_init__(self) -> None:
        requested = {cell.cell_id for cell in self.request.cells}
        result_ids = tuple(result.cell_id for result in self.results)
        if len(set(result_ids)) != len(result_ids):
            raise ValueError("notebook execution results must have unique cell ids")
        if not set(result_ids).issubset(requested):
            raise ValueError("notebook execution results must reference requested cells")

    @property
    def is_complete(self) -> bool:
        return len(self.results) == len(self.request.cells)


def prepare_notebook_execution(
    document: NotebookDocument,
    runtime: ResolvedRuntimeSnapshot,
    repository: RepositoryRevision,
    adapter: KernelRequestAdapter,
    *,
    attempt_id: ExecutionAttemptId,
    reproducibility: ExecutionReproducibilitySnapshot,
) -> NotebookExecutionRequest:
    """Prepare executable cells without mutating authored notebook intent."""
    _require_text(adapter.adapter_id, "kernel adapter id")
    analysis = analyze_notebook_dependencies(document.notebook)
    if not analysis.is_valid:
        raise ValueError("cannot prepare notebook execution with invalid dependencies")

    by_id = {cell.id: cell for cell in document.notebook.cells}
    requests: list[CellExecutionRequest] = []
    for cell_id in analysis.execution_order:
        cell = by_id[cell_id]
        prepared = adapter.prepare(cell)
        if prepared.cell_id != cell.id:
            raise ValueError("kernel adapter must preserve cell identity")
        if prepared.directive.adapter_id != adapter.adapter_id:
            raise ValueError("prepared directive adapter id must match the preparing adapter")
        requests.append(
            CellExecutionRequest(
                cell_id=cell.id,
                authored_source=cell.source,
                executable_source=prepared.executable_source,
                language=cell.language or "",
                dependencies=cell.dependencies,
                directive=prepared.directive,
            )
        )

    return NotebookExecutionRequest(
        document,
        runtime,
        repository,
        attempt_id,
        reproducibility,
        tuple(requests),
    )
