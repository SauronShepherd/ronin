from __future__ import annotations

from dataclasses import dataclass

import pytest
from studio_core import ResolvedRuntimeSnapshot, RuntimeProfile, RuntimeProfileRef
from studio_kernel import (
    CellExecutionResult,
    ExecutionAttemptId,
    ExecutionEvidenceReference,
    ExecutionReproducibilitySnapshot,
    KernelDirective,
    KernelDirectiveField,
    NotebookExecutionEvidence,
    PreparedCell,
    RepositoryRevision,
    prepare_notebook_execution,
)
from studio_notebook import CellIdentityAnchor, Notebook, NotebookCell, NotebookDocument


def _runtime() -> ResolvedRuntimeSnapshot:
    profile = RuntimeProfile(RuntimeProfileRef("local", "python"))
    return ResolvedRuntimeSnapshot(None, profile, "compatible", False, (), 0)


def _document(*, invalid_dependency: bool = False) -> NotebookDocument:
    anchors = (
        CellIdentityAnchor("authoring", "nb", "intro"),
        CellIdentityAnchor("authoring", "nb", "load"),
        CellIdentityAnchor("authoring", "nb", "report"),
    )
    intro_id, load_id, report_id = (anchor.cell_id() for anchor in anchors)
    dependency = (
        CellIdentityAnchor("authoring", "other", "missing").cell_id()
        if invalid_dependency
        else load_id
    )
    notebook = Notebook(
        (
            NotebookCell(intro_id, "markdown", "# title"),
            NotebookCell(load_id, "code", "%pip install demo\nprint('load')", language="python"),
            NotebookCell(report_id, "sql", "%%sql\nselect 1", (dependency,), "sql"),
        )
    )
    return NotebookDocument(notebook, anchors)


@dataclass(frozen=True)
class _Adapter:
    adapter_id: str = "test-kernel"
    wrong_cell: bool = False
    wrong_adapter: bool = False

    def prepare(self, cell: NotebookCell) -> PreparedCell:
        directive_adapter = "other" if self.wrong_adapter else self.adapter_id
        directive = KernelDirective(
            directive_adapter,
            "source.execute",
            (KernelDirectiveField("language", cell.language or ""),),
            ("network.egress",) if cell.source.startswith("%pip") else (),
        )
        return PreparedCell(
            CellIdentityAnchor("authoring", "wrong", "cell").cell_id()
            if self.wrong_cell
            else cell.id,
            cell.source.split("\n", maxsplit=1)[-1],
            directive,
        )


def _prepare(
    document: NotebookDocument,
    adapter: _Adapter = _Adapter(),
    repository: RepositoryRevision = RepositoryRevision("a" * 40),
) -> object:
    return prepare_notebook_execution(
        document,
        _runtime(),
        repository,
        adapter,
        attempt_id=ExecutionAttemptId("attempt-001"),
        reproducibility=ExecutionReproducibilitySnapshot(),
    )


def test_repository_revision_validates_clean_and_dirty_git_identity() -> None:
    clean = RepositoryRevision("a" * 40)
    dirty = RepositoryRevision("b" * 64, "c" * 64)
    assert clean.dirty_patch_sha256 is None
    assert dirty.dirty_patch_sha256 == "c" * 64

    for commit in ("a" * 39, "A" * 40, "z" * 40):
        with pytest.raises(ValueError, match="repository commit"):
            RepositoryRevision(commit)
    for patch in ("d" * 63, "D" * 64, "z" * 64):
        with pytest.raises(ValueError, match="dirty patch"):
            RepositoryRevision("a" * 40, patch)


def test_directives_are_canonical_and_fail_closed_on_invalid_metadata() -> None:
    directive = KernelDirective(
        "adapter",
        "package.install",
        (KernelDirectiveField("z", "2"), KernelDirectiveField("a", "1")),
        ("secrets.read", "network.egress"),
    )
    assert [field.name for field in directive.fields] == ["a", "z"]
    assert directive.required_permissions == ("network.egress", "secrets.read")

    for value in ("", " padded ", "bad\nvalue"):
        with pytest.raises(ValueError, match="non-empty"):
            KernelDirective(value, "kind")
        with pytest.raises(ValueError, match="non-empty"):
            KernelDirective("adapter", value)
        with pytest.raises(ValueError, match="non-empty"):
            KernelDirectiveField(value, "value")

    with pytest.raises(ValueError, match="NUL"):
        KernelDirectiveField("name", "bad\x00value")
    with pytest.raises(ValueError, match="field names"):
        KernelDirective(
            "adapter",
            "kind",
            (KernelDirectiveField("same", "1"), KernelDirectiveField("same", "2")),
        )
    with pytest.raises(ValueError, match="permissions must be unique"):
        KernelDirective("adapter", "kind", required_permissions=("run", "run"))
    with pytest.raises(ValueError, match="permission"):
        KernelDirective("adapter", "kind", required_permissions=(" bad ",))


def test_prepare_notebook_execution_preserves_authored_intent_and_dependency_order() -> None:
    document = _document()
    reproducibility = ExecutionReproducibilitySnapshot()
    attempt_id = ExecutionAttemptId("attempt-001")
    request = prepare_notebook_execution(
        document,
        _runtime(),
        RepositoryRevision("a" * 40, "b" * 64),
        _Adapter(),
        attempt_id=attempt_id,
        reproducibility=reproducibility,
    )

    assert request.document is document
    assert request.runtime == _runtime()
    assert request.repository.dirty_patch_sha256 == "b" * 64
    assert request.attempt_id == attempt_id
    assert request.reproducibility is reproducibility
    assert [cell.cell_id for cell in request.cells] == [
        document.notebook.cells[1].id,
        document.notebook.cells[2].id,
    ]
    assert request.cells[0].authored_source.startswith("%pip")
    assert request.cells[0].executable_source == "print('load')"
    assert request.cells[0].directive.required_permissions == ("network.egress",)
    assert request.cells[1].dependencies == (document.notebook.cells[1].id,)
    assert document.notebook.cells[1].source == "%pip install demo\nprint('load')"


def test_prepare_notebook_execution_rejects_invalid_graph_and_adapter_identity_drift() -> None:
    with pytest.raises(ValueError, match="invalid dependencies"):
        _prepare(_document(invalid_dependency=True))
    with pytest.raises(ValueError, match="kernel adapter id"):
        _prepare(_document(), _Adapter(adapter_id=" bad "))
    with pytest.raises(ValueError, match="preserve cell identity"):
        _prepare(_document(), _Adapter(wrong_cell=True))
    with pytest.raises(ValueError, match="must match"):
        _prepare(_document(), _Adapter(wrong_adapter=True))


def test_results_normalize_failure_and_cross_cutting_evidence() -> None:
    request = _prepare(_document())
    assert hasattr(request, "cells")
    first, second = request.cells  # type: ignore[attr-defined]
    refs = (
        ExecutionEvidenceReference("trace", "otel://trace/123"),
        ExecutionEvidenceReference("cost", "cost://run/cell-1"),
        ExecutionEvidenceReference("lineage", "lineage://event/7"),
    )
    success = CellExecutionResult(first.cell_id, "succeeded", evidence=refs)
    failure = CellExecutionResult(second.cell_id, "failed", "kernel.sql.syntax")
    evidence = NotebookExecutionEvidence(request, (success, failure))  # type: ignore[arg-type]

    assert success.evidence == tuple(sorted(refs))
    assert evidence.is_complete is True
    assert NotebookExecutionEvidence(request, (success,)).is_complete is False  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="unsupported execution evidence kind"):
        ExecutionEvidenceReference("unknown", "ref")  # type: ignore[arg-type]
    for ref in ("", " bad ", "bad\nref"):
        with pytest.raises(ValueError, match="execution evidence reference"):
            ExecutionEvidenceReference("log", ref)
    with pytest.raises(ValueError, match="unsupported cell execution state"):
        CellExecutionResult(first.cell_id, "unknown")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="requires a normalized failure code"):
        CellExecutionResult(first.cell_id, "failed")
    for failure_code in ("", " bad ", "bad\ncode"):
        with pytest.raises(ValueError, match="failure code"):
            CellExecutionResult(first.cell_id, "failed", failure_code)
    with pytest.raises(ValueError, match="non-failed"):
        CellExecutionResult(first.cell_id, "cancelled", "should-not-exist")
    duplicate_ref = ExecutionEvidenceReference("log", "log://same")
    with pytest.raises(ValueError, match="evidence references must be unique"):
        CellExecutionResult(first.cell_id, "succeeded", evidence=(duplicate_ref, duplicate_ref))
    with pytest.raises(ValueError, match="unique cell ids"):
        NotebookExecutionEvidence(request, (success, success))  # type: ignore[arg-type]
    unknown = CellIdentityAnchor("authoring", "nb", "unknown").cell_id()
    with pytest.raises(ValueError, match="requested cells"):
        NotebookExecutionEvidence(  # type: ignore[arg-type]
            request,
            (CellExecutionResult(unknown, "succeeded"),),
        )
