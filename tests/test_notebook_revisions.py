from __future__ import annotations

import pytest

from studio_notebook import (
    CellIdentityAnchor,
    Notebook,
    NotebookCell,
    NotebookDocument,
    NotebookHTTPAdapter,
    NotebookRevisionConflict,
    NotebookRevisionStore,
    ProjectNotebookHTTPAdapter,
    allocate_cell_ids,
)


def _document(source: str) -> NotebookDocument:
    anchor = CellIdentityAnchor("authoring", "demo", "cell-1")
    cell = NotebookCell(allocate_cell_ids((anchor,))[0], "code", source, language="python")
    return NotebookDocument(
        Notebook((cell,)),
        (anchor,),
    )


def test_notebook_revision_crud_and_optimistic_conflict() -> None:
    store = NotebookRevisionStore()
    first = store.create(
        "nb-1",
        _document("x = 1"),
        source_revision="abc",
        parameter_schema=(("limit", "integer"),),
    )
    assert first.revision == 1
    assert len(first.content_digest) == 64
    assert first.parameter_schema == (("limit", "integer"),)
    second = store.save(
        "nb-1",
        _document("x = 2"),
        expected_revision=1,
        parameter_schema=(("limit", "integer"),),
    )
    assert second.revision == 2
    with pytest.raises(NotebookRevisionConflict, match="stale"):
        store.save("nb-1", _document("x = 3"), expected_revision=1)
    archived = store.archive("nb-1", expected_revision=2)
    assert archived.archived is True
    assert store.list() == ()
    assert len(store.list(include_archived=True)) == 1
    with pytest.raises(NotebookRevisionConflict, match="archived"):
        store.save("nb-1", _document("x = 4"), expected_revision=3)
    store.delete("nb-1", expected_revision=3)
    assert store.list(include_archived=True) == ()


def test_notebook_revision_metadata_is_single_line_and_trimmed() -> None:
    store = NotebookRevisionStore()
    document = _document("x = 1")
    with pytest.raises(ValueError, match="source_revision"):
        store.create("metadata-source", document, source_revision=" rev")
    with pytest.raises(ValueError, match="execution_binding"):
        store.create("metadata-binding", document, execution_binding="x\ny")
    created = store.create("metadata-ok", document, source_revision="commit:abc")
    with pytest.raises(ValueError, match="evidence_digest"):
        store.save("metadata-ok", document, expected_revision=created.revision, evidence_digest=" ")


def test_notebook_http_adapter_preserves_revision_contract() -> None:
    store = NotebookRevisionStore()
    adapter = NotebookHTTPAdapter(store)
    document = _document("x = 1").to_data()
    created = adapter.create({"id": "nb-http", "document": document})
    assert created["revision"] == 1
    updated = adapter.save(
        "nb-http", {"expected_revision": 1, "document": _document("x = 2").to_data()}
    )
    assert updated["revision"] == 2
    with pytest.raises(NotebookRevisionConflict):
        adapter.save("nb-http", {"expected_revision": 1, "document": document})
    assert adapter.list()["items"][0]["id"] == "nb-http"


def test_project_notebook_adapter_isolates_revision_namespaces() -> None:
    projects = ProjectNotebookHTTPAdapter()
    first = projects.for_project("project-a")
    second = projects.for_project("project-b")
    first.create({"id": "same-id", "document": _document("a").to_data()})
    assert second.list()["items"] == []
    assert first.list()["items"][0]["id"] == "same-id"
