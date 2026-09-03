"""Strict deterministic serialization for portable Ronin notebook documents."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from .dependencies import CellId, CellKind, Notebook, NotebookCell
from .identity import CellIdentityAnchor, CellIdentityBoundary, allocate_cell_ids

NOTEBOOK_DOCUMENT_SCHEMA = "ronin.notebook/v1"


@dataclass(frozen=True, slots=True)
class NotebookDocument:
    """Versioned notebook intent with persisted, verifiable cell identity provenance."""

    notebook: Notebook
    cell_identities: tuple[CellIdentityAnchor, ...]
    schema: str = NOTEBOOK_DOCUMENT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != NOTEBOOK_DOCUMENT_SCHEMA:
            raise ValueError(f"unsupported notebook document schema: {self.schema}")
        if len(self.cell_identities) != len(self.notebook.cells):
            raise ValueError("notebook document requires exactly one identity anchor per cell")
        expected_ids = allocate_cell_ids(self.cell_identities)
        actual_ids = tuple(cell.id for cell in self.notebook.cells)
        if actual_ids != expected_ids:
            raise ValueError("notebook cell ids do not match persisted identity anchors")

    def to_data(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "cells": [
                _cell_to_data(cell, identity)
                for cell, identity in zip(
                    self.notebook.cells,
                    self.cell_identities,
                    strict=True,
                )
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_data(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_data(cls, value: Mapping[str, object]) -> NotebookDocument:
        document_data = _require_mapping(value, "notebook document")
        _require_exact_keys(document_data, {"schema", "cells"}, "notebook document")
        schema = _require_str(document_data.get("schema"), "schema")
        cells_data = _require_sequence(document_data.get("cells"), "cells")
        parsed = tuple(_cell_from_data(_require_mapping(item, "cell")) for item in cells_data)
        return cls(
            notebook=Notebook(tuple(cell for cell, _ in parsed)),
            cell_identities=tuple(identity for _, identity in parsed),
            schema=schema,
        )

    @classmethod
    def from_json(cls, payload: str) -> NotebookDocument:
        return cls.from_data(_require_mapping(json.loads(payload), "notebook document"))


def _cell_to_data(cell: NotebookCell, identity: CellIdentityAnchor) -> dict[str, object]:
    return {
        "dependencies": [dependency.value for dependency in cell.dependencies],
        "id": cell.id.value,
        "identity": {
            "boundary": identity.boundary,
            "namespace": identity.namespace,
            "reference": identity.reference,
        },
        "kind": cell.kind,
        "language": cell.language,
        "source": cell.source,
    }


def _cell_from_data(value: Mapping[str, object]) -> tuple[NotebookCell, CellIdentityAnchor]:
    _require_exact_keys(
        value,
        {"dependencies", "id", "identity", "kind", "language", "source"},
        "cell",
    )
    kind = _require_str(value.get("kind"), "cell.kind")
    if kind not in {"code", "markdown", "sql"}:
        raise ValueError("cell.kind must be code, markdown, or sql")
    language = value.get("language")
    if language is not None and not isinstance(language, str):
        raise TypeError("cell.language must be a string or null")
    identity = _identity_from_data(_require_mapping(value.get("identity"), "cell.identity"))
    dependencies_data = _require_sequence(value.get("dependencies"), "cell.dependencies")
    cell = NotebookCell(
        id=CellId(_require_str(value.get("id"), "cell.id")),
        kind=cast(CellKind, kind),
        source=_require_str(value.get("source"), "cell.source"),
        dependencies=tuple(
            CellId(_require_str(item, "cell dependency")) for item in dependencies_data
        ),
        language=language,
    )
    return cell, identity


def _identity_from_data(value: Mapping[str, object]) -> CellIdentityAnchor:
    _require_exact_keys(value, {"boundary", "namespace", "reference"}, "cell.identity")
    boundary = _require_str(value.get("boundary"), "cell.identity.boundary")
    if boundary not in {"authoring", "import"}:
        raise ValueError("cell.identity.boundary must be authoring or import")
    return CellIdentityAnchor(
        boundary=cast(CellIdentityBoundary, boundary),
        namespace=_require_str(value.get("namespace"), "cell.identity.namespace"),
        reference=_require_str(value.get("reference"), "cell.identity.reference"),
    )


def _require_exact_keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise ValueError(f"{name} keys mismatch; missing={missing}, extra={extra}")


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{name} must be an object with string keys")
    return cast(Mapping[str, object], value)


def _require_sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{name} must be an array")
    return cast(Sequence[object], value)


def _require_str(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value
