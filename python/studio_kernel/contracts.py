"""Typed kernel preparation and execution-evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias
from urllib.parse import urlsplit

from studio_core import Requirement, ResolvedRuntimeSnapshot
from studio_notebook import CellId, NotebookCell, NotebookDocument, analyze_notebook_dependencies

from .redaction import redact_sensitive_text
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
    """Exact local Git revision plus its optional declared project binding."""

    commit: str
    dirty_patch_sha256: str | None = None
    source_uri: str | None = None
    source_default_ref: str | None = None
    source_subdirectory: str | None = None
    source_sync_policy: Literal["manual", "fetch", "fast-forward"] | None = None

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
        if (self.source_uri is None) != (self.source_default_ref is None):
            raise ValueError("source URI and default ref must be provided together")
        if self.source_uri is not None:
            _require_text(self.source_uri, "source URI")
            if any(
                ord(character) < 0x20 or ord(character) == 0x7F for character in self.source_uri
            ):
                raise ValueError("source URI must not contain control characters")
            try:
                parsed = urlsplit(self.source_uri)
                _ = parsed.port
            except ValueError as exc:
                raise ValueError("source URI must be valid") from exc
            if (
                parsed.scheme not in {"https", "ssh", "git", "file"}
                or parsed.password is not None
                or (parsed.username is not None and parsed.scheme != "ssh")
                or parsed.query
                or parsed.fragment
                or (parsed.scheme == "file" and parsed.netloc)
                or (parsed.scheme == "file" and not parsed.path)
                or (parsed.scheme != "file" and not parsed.hostname)
            ):
                raise ValueError("source URI must be supported and credential-free")
            default_ref = self.source_default_ref or ""
            _require_text(default_ref, "source default ref")
            if default_ref.startswith("-") or any(
                character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
                for character in default_ref
            ):
                raise ValueError("source default ref must be a stable ref")
        if self.source_subdirectory is not None:
            if self.source_uri is None:
                raise ValueError("source subdirectory requires a source binding")
            _require_text(self.source_subdirectory, "source subdirectory")
            if any(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in self.source_subdirectory
            ):
                raise ValueError("source subdirectory must not contain control characters")
            normalized = self.source_subdirectory.replace("\\", "/")
            if normalized.startswith("/") or ".." in normalized.split("/"):
                raise ValueError("source subdirectory must stay inside its repository")
        if self.source_sync_policy is not None:
            if self.source_uri is None:
                raise ValueError("source sync policy requires a source binding")
            if self.source_sync_policy not in {"manual", "fetch", "fast-forward"}:
                raise ValueError("source sync policy is unsupported")


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
    """Adapter-owned normalized instruction separate from authored notebook intent.

    ``required_permissions`` remains as the alpha compatibility path. New adapters should
    emit typed ``required_grants`` requirements. A directive may use only one representation
    so execution cannot silently disagree about which authorization contract is authoritative.
    """

    adapter_id: str
    kind: str
    fields: tuple[KernelDirectiveField, ...] = ()
    required_permissions: tuple[str, ...] = ()
    required_grants: tuple[Requirement, ...] = ()

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
        requirements = tuple(sorted(self.required_grants, key=lambda item: item.canonical_key))
        if len(set(requirements)) != len(requirements):
            raise ValueError("kernel directive grant requirements must be unique")
        if permissions and requirements:
            raise ValueError(
                "kernel directive must not mix legacy permissions with typed grant requirements"
            )
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "required_permissions", permissions)
        object.__setattr__(self, "required_grants", requirements)


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
    """Execution evidence locator with optional portable content identity.

    ``ref`` is a physical locator and is deliberately excluded from ``portable_identity``.
    Durable execution paths require the portable fields so moving identical content does
    not change its logical identity. Legacy opaque references remain constructible while
    non-durable integrations migrate, but partial portable metadata is rejected.
    """

    kind: EvidenceKind
    ref: str
    digest_algorithm: str | None = None
    digest: str | None = None
    media_type: str | None = None
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"log", "metric", "trace", "lineage", "output", "resource", "cost"}:
            raise ValueError("unsupported execution evidence kind")
        _require_text(self.ref, "execution evidence reference")
        object.__setattr__(self, "ref", redact_sensitive_text(self.ref))

        portable_values = (self.digest_algorithm, self.digest, self.size_bytes)
        has_portable = any(value is not None for value in portable_values)
        if has_portable and any(value is None for value in portable_values):
            raise ValueError("portable evidence identity requires algorithm, digest, and size")
        if has_portable:
            digest_algorithm = self.digest_algorithm
            digest = self.digest
            size_bytes = self.size_bytes
            if digest_algorithm is None or digest is None or size_bytes is None:
                raise ValueError("portable evidence identity requires algorithm, digest, and size")
            if digest_algorithm != "sha256":
                raise ValueError("unsupported evidence digest algorithm")
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("evidence digest must be lowercase SHA-256 hex")
            if size_bytes < 0:
                raise ValueError("evidence size must be non-negative")
        if self.media_type is not None:
            _require_text(self.media_type, "evidence media type")

    @property
    def portable_identity(self) -> tuple[str, str, str, str | None, int] | None:
        """Return location-independent content identity when the reference is portable."""

        if self.digest_algorithm is None or self.digest is None or self.size_bytes is None:
            return None
        return (self.kind, self.digest_algorithm, self.digest, self.media_type, self.size_bytes)

    def portable_payload(self) -> dict[str, object]:
        """Return the fail-closed v1 portable representation used by durable boundaries."""

        identity = self.portable_identity
        if identity is None:
            raise ValueError("evidence reference does not have portable content identity")
        return {
            "version": 1,
            "role": self.kind,
            "digest_algorithm": self.digest_algorithm,
            "digest": self.digest,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "locator": self.ref,
            "availability": "available",
        }


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
            object.__setattr__(self, "failure_code", redact_sensitive_text(self.failure_code))
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
