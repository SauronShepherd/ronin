"""Provider-neutral notebook CRUD and optimistic revision lifecycle."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from .serialization import NotebookDocument


class NotebookRevisionConflict(RuntimeError):
    """Raised when a save/delete uses a stale notebook revision."""


class NotebookRevisionNotFound(KeyError):
    """Raised when a notebook identity is not present."""


@dataclass(frozen=True, slots=True)
class NotebookRevision:
    notebook_id: str
    revision: int
    content_digest: str
    document: NotebookDocument
    source_revision: str | None = None
    archived: bool = False
    execution_binding: str | None = None
    evidence_digest: str | None = None
    parameter_schema: tuple[tuple[str, str], ...] = ()


def _digest(document: NotebookDocument) -> str:
    return hashlib.sha256(document.to_json().encode("utf-8")).hexdigest()


def _parameters(value: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    if any(
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(type_name, str)
        or not type_name.strip()
        for name, type_name in value
    ):
        raise ValueError("notebook parameter schema entries must be non-empty text")
    if len({name for name, _ in value}) != len(value):
        raise ValueError("notebook parameter schema names must be unique")
    return tuple(sorted(value))


def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty trimmed text when provided")
    if any(char in value for char in "\r\n\x00"):
        raise ValueError(f"{name} must be single-line text")
    return value


class NotebookRevisionStore:
    """Small deterministic store boundary suitable for SQLite/API adapters."""

    def __init__(self) -> None:
        self._items: dict[str, NotebookRevision] = {}

    def create(
        self,
        notebook_id: str,
        document: NotebookDocument,
        *,
        source_revision: str | None = None,
        execution_binding: str | None = None,
        parameter_schema: tuple[tuple[str, str], ...] = (),
    ) -> NotebookRevision:
        self._validate_id(notebook_id)
        source_revision = _optional_text(source_revision, "source_revision")
        execution_binding = _optional_text(execution_binding, "execution_binding")
        if notebook_id in self._items:
            raise NotebookRevisionConflict(f"notebook already exists: {notebook_id}")
        result = NotebookRevision(
            notebook_id,
            1,
            _digest(document),
            document,
            source_revision,
            False,
            execution_binding,
            None,
            _parameters(parameter_schema),
        )
        self._items[notebook_id] = result
        return result

    def get(self, notebook_id: str) -> NotebookRevision:
        try:
            return self._items[notebook_id]
        except KeyError as exc:
            raise NotebookRevisionNotFound(notebook_id) from exc

    def save(
        self,
        notebook_id: str,
        document: NotebookDocument,
        *,
        expected_revision: int,
        source_revision: str | None = None,
        execution_binding: str | None = None,
        evidence_digest: str | None = None,
        parameter_schema: tuple[tuple[str, str], ...] = (),
    ) -> NotebookRevision:
        current = self.get(notebook_id)
        source_revision = _optional_text(source_revision, "source_revision")
        execution_binding = _optional_text(execution_binding, "execution_binding")
        evidence_digest = _optional_text(evidence_digest, "evidence_digest")
        if current.archived:
            raise NotebookRevisionConflict("cannot save an archived notebook")
        if current.revision != expected_revision:
            raise NotebookRevisionConflict(
                f"stale notebook revision: expected {expected_revision}, current {current.revision}"
            )
        result = replace(
            current,
            revision=current.revision + 1,
            content_digest=_digest(document),
            document=document,
            source_revision=source_revision,
            execution_binding=execution_binding,
            evidence_digest=evidence_digest,
            parameter_schema=_parameters(parameter_schema),
        )
        self._items[notebook_id] = result
        return result

    def archive(self, notebook_id: str, *, expected_revision: int) -> NotebookRevision:
        current = self.get(notebook_id)
        if current.revision != expected_revision:
            raise NotebookRevisionConflict("stale notebook revision")
        result = replace(current, revision=current.revision + 1, archived=True)
        self._items[notebook_id] = result
        return result

    def delete(self, notebook_id: str, *, expected_revision: int) -> None:
        current = self.get(notebook_id)
        if current.revision != expected_revision:
            raise NotebookRevisionConflict("stale notebook revision")
        del self._items[notebook_id]

    def list(self, *, include_archived: bool = False) -> tuple[NotebookRevision, ...]:
        return tuple(
            self._items[key]
            for key in sorted(self._items)
            if include_archived or not self._items[key].archived
        )

    @staticmethod
    def _validate_id(notebook_id: str) -> None:
        if (
            not isinstance(notebook_id, str)
            or not notebook_id
            or notebook_id != notebook_id.strip()
        ):
            raise ValueError("notebook_id must be non-empty and trimmed")


__all__ = (
    "NotebookRevision",
    "NotebookRevisionConflict",
    "NotebookRevisionNotFound",
    "NotebookRevisionStore",
)
