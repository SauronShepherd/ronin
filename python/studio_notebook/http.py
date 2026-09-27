"""Transport-neutral notebook CRUD adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, cast

from .revisions import NotebookRevision, NotebookRevisionStore
from .serialization import NotebookDocument


class NotebookRevisionReader(Protocol):
    def list(self, *, include_archived: bool = False) -> tuple[NotebookRevision, ...]: ...
    def get(self, notebook_id: str) -> NotebookRevision: ...


def _document(payload: object) -> NotebookDocument:
    if not isinstance(payload, Mapping):
        raise ValueError("document must be an object")
    return NotebookDocument.from_data(payload)


def _parameters(payload: object) -> tuple[tuple[str, str], ...]:
    if payload is None:
        return ()
    if not isinstance(payload, list):
        raise ValueError("parameter_schema must be an array")
    result: list[tuple[str, str]] = []
    for item in payload:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("type"), str)
        ):
            raise ValueError("parameter_schema entries require name and type")
        result.append((item["name"], item["type"]))
    return tuple(result)


def _output(item: NotebookRevision) -> dict[str, object]:
    return {
        "id": item.notebook_id,
        "revision": item.revision,
        "content_digest": item.content_digest,
        "document": item.document.to_data(),
        "source_revision": item.source_revision,
        "archived": item.archived,
        "execution_binding": item.execution_binding,
        "evidence_digest": item.evidence_digest,
        "parameter_schema": [{"name": n, "type": t} for n, t in item.parameter_schema],
    }


class NotebookHTTPAdapter:
    """Strict CRUD port; authorization and HTTP status mapping stay outside."""

    def __init__(self, store: NotebookRevisionStore) -> None:
        self._store = store

    def list(self, *, include_archived: bool = False) -> dict[str, object]:
        return {
            "items": [_output(item) for item in self._store.list(include_archived=include_archived)]
        }

    def get(self, notebook_id: str) -> dict[str, object]:
        return _output(self._store.get(notebook_id))

    def create(self, payload: Mapping[str, object]) -> dict[str, object]:
        notebook_id = payload.get("id")
        if not isinstance(notebook_id, str):
            raise ValueError("id must be a string")
        return _output(
            self._store.create(
                notebook_id,
                _document(payload.get("document")),
                source_revision=cast(str | None, payload.get("source_revision")),
                execution_binding=cast(str | None, payload.get("execution_binding")),
                parameter_schema=_parameters(payload.get("parameter_schema")),
            )
        )

    def save(self, notebook_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        expected = payload.get("expected_revision")
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
            raise ValueError("expected_revision must be a positive integer")
        return _output(
            self._store.save(
                notebook_id,
                _document(payload.get("document")),
                expected_revision=expected,
                source_revision=cast(str | None, payload.get("source_revision")),
                execution_binding=cast(str | None, payload.get("execution_binding")),
                evidence_digest=cast(str | None, payload.get("evidence_digest")),
                parameter_schema=_parameters(payload.get("parameter_schema")),
            )
        )

    def archive(self, notebook_id: str, *, expected_revision: int) -> dict[str, object]:
        return _output(self._store.archive(notebook_id, expected_revision=expected_revision))

    def delete(self, notebook_id: str, *, expected_revision: int) -> None:
        self._store.delete(notebook_id, expected_revision=expected_revision)


class ProjectNotebookHTTPAdapter:
    """Project-scoped notebook port backed by isolated revision stores."""

    def __init__(self) -> None:
        self._projects: dict[str, NotebookHTTPAdapter] = {}

    def for_project(self, project_id: str) -> NotebookHTTPAdapter:
        if not isinstance(project_id, str) or not project_id or project_id != project_id.strip():
            raise ValueError("project_id must be non-empty and trimmed")
        adapter = self._projects.get(project_id)
        if adapter is None:
            adapter = NotebookHTTPAdapter(NotebookRevisionStore())
            self._projects[project_id] = adapter
        return adapter

    def list(self, *, project_id: str, include_archived: bool = False) -> dict[str, object]:
        return self.for_project(project_id).list(include_archived=include_archived)

    def get(self, *, project_id: str, notebook_id: str) -> dict[str, object]:
        return self.for_project(project_id).get(notebook_id)

    def create(self, *, project_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        return self.for_project(project_id).create(payload)

    def save(
        self, *, project_id: str, notebook_id: str, payload: Mapping[str, object]
    ) -> dict[str, object]:
        return self.for_project(project_id).save(notebook_id, payload)

    def archive(
        self, *, project_id: str, notebook_id: str, expected_revision: int
    ) -> dict[str, object]:
        return self.for_project(project_id).archive(
            notebook_id, expected_revision=expected_revision
        )

    def delete(self, *, project_id: str, notebook_id: str, expected_revision: int) -> None:
        self.for_project(project_id).delete(notebook_id, expected_revision=expected_revision)


__all__ = ("NotebookHTTPAdapter", "NotebookRevisionReader", "ProjectNotebookHTTPAdapter")
