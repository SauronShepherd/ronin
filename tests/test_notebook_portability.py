from __future__ import annotations

import json

import pytest

from studio_notebook import (
    NOTEBOOK_DOCUMENT_SCHEMA,
    CellId,
    CellIdentityAnchor,
    Notebook,
    NotebookCell,
    NotebookDocument,
    NotebookImportCell,
    allocate_cell_ids,
    import_notebook,
)


def test_cell_identity_anchor_has_stable_golden_ids() -> None:
    authoring = CellIdentityAnchor("authoring", "project/notebooks/demo", "cell-1")
    imported = CellIdentityAnchor("import", "project/notebooks/demo", "cell-1")

    assert authoring.cell_id() == CellId(
        "e617c45761af4c7f02cda8854e94580903e7850d34e86eead93fa4feccdc94e8"
    )
    assert imported.cell_id() == CellId(
        "1ff1e8d95ccfaf40aa1458ad576f81cb35052586902897d495c79765add12f79"
    )
    assert allocate_cell_ids((authoring, imported)) == (
        authoring.cell_id(),
        imported.cell_id(),
    )


def test_cell_identity_anchor_rejects_ambiguous_provenance() -> None:
    with pytest.raises(ValueError, match="boundary"):
        CellIdentityAnchor("runtime", "notebook", "cell")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="namespace"):
        CellIdentityAnchor("import", " notebook ", "cell")
    with pytest.raises(ValueError, match="namespace"):
        CellIdentityAnchor("import", "", "cell")
    with pytest.raises(ValueError, match="namespace"):
        CellIdentityAnchor("import", "note\nbook", "cell")
    with pytest.raises(ValueError, match="reference"):
        CellIdentityAnchor("import", "notebook", " cell ")
    with pytest.raises(ValueError, match="reference"):
        CellIdentityAnchor("import", "notebook", "cell\rnext")


def test_cell_identity_allocation_rejects_duplicates() -> None:
    anchor = CellIdentityAnchor("import", "notebook", "cell")
    with pytest.raises(ValueError, match="unique"):
        allocate_cell_ids((anchor, anchor))


def _portable_document() -> NotebookDocument:
    intro_identity = CellIdentityAnchor("authoring", "demo", "intro")
    code_identity = CellIdentityAnchor("authoring", "demo", "code")
    sql_identity = CellIdentityAnchor("authoring", "demo", "sql")
    intro_id, code_id, sql_id = allocate_cell_ids(
        (intro_identity, code_identity, sql_identity)
    )
    notebook = Notebook(
        (
            NotebookCell(intro_id, "markdown", "# Café"),
            NotebookCell(code_id, "code", "value = 1", language="python"),
            NotebookCell(
                sql_id,
                "sql",
                "select * from values",
                dependencies=(code_id,),
                language="ansi-sql",
            ),
        )
    )
    return NotebookDocument(
        notebook,
        (intro_identity, code_identity, sql_identity),
    )


def test_notebook_document_round_trip_is_deterministic_and_portable() -> None:
    document = _portable_document()

    payload = document.to_json()
    decoded = json.loads(payload)

    assert decoded["schema"] == NOTEBOOK_DOCUMENT_SCHEMA
    assert [cell["kind"] for cell in decoded["cells"]] == ["markdown", "code", "sql"]
    assert "Café" in payload
    assert "outputs" not in payload
    assert "execution_count" not in payload
    assert "metadata" not in payload
    assert NotebookDocument.from_json(payload) == document
    reordered = {"cells": decoded["cells"], "schema": decoded["schema"]}
    assert NotebookDocument.from_data(reordered) == document
    assert NotebookDocument.from_json(payload).to_json() == payload


def test_notebook_document_rejects_schema_and_identity_mismatch() -> None:
    document = _portable_document()
    with pytest.raises(ValueError, match="unsupported"):
        NotebookDocument(
            document.notebook,
            document.cell_identities,
            schema="ronin.notebook/v2",
        )
    with pytest.raises(ValueError, match="exactly one"):
        NotebookDocument(document.notebook, document.cell_identities[:-1])
    with pytest.raises(ValueError, match="unique"):
        NotebookDocument(
            document.notebook,
            (document.cell_identities[0],) * len(document.notebook.cells),
        )

    wrong_identity = CellIdentityAnchor("authoring", "demo", "different")
    with pytest.raises(ValueError, match="do not match"):
        NotebookDocument(
            document.notebook,
            (document.cell_identities[0], document.cell_identities[1], wrong_identity),
        )


def test_notebook_document_rejects_tampered_serialized_id() -> None:
    data = _portable_document().to_data()
    cells = data["cells"]
    assert isinstance(cells, list)
    cell = cells[1]
    assert isinstance(cell, dict)
    cell["id"] = "tampered"

    with pytest.raises(ValueError, match="do not match"):
        NotebookDocument.from_data(data)


def test_notebook_document_strictly_rejects_shape_drift() -> None:
    document = _portable_document()
    data = document.to_data()

    with pytest.raises(ValueError, match="keys mismatch"):
        NotebookDocument.from_data(
            {"schema": NOTEBOOK_DOCUMENT_SCHEMA, "cells": [], "extra": 1}
        )
    with pytest.raises(ValueError, match="keys mismatch"):
        NotebookDocument.from_data({"schema": NOTEBOOK_DOCUMENT_SCHEMA})
    with pytest.raises(TypeError, match="cells must be an array"):
        NotebookDocument.from_data(
            {"schema": NOTEBOOK_DOCUMENT_SCHEMA, "cells": "not-array"}
        )
    with pytest.raises(TypeError, match="cell must be an object"):
        NotebookDocument.from_data({"schema": NOTEBOOK_DOCUMENT_SCHEMA, "cells": [1]})
    with pytest.raises(TypeError, match="string keys"):
        NotebookDocument.from_data({1: "bad"})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="object"):
        NotebookDocument.from_json("[]")

    cells = data["cells"]
    assert isinstance(cells, list)
    first = cells[0]
    assert isinstance(first, dict)
    first["extra"] = True
    with pytest.raises(ValueError, match="cell keys mismatch"):
        NotebookDocument.from_data(data)


def _single_cell_data() -> dict[str, object]:
    identity = CellIdentityAnchor("authoring", "demo", "cell")
    cell_id = identity.cell_id()
    return {
        "schema": NOTEBOOK_DOCUMENT_SCHEMA,
        "cells": [
            {
                "dependencies": [],
                "id": cell_id.value,
                "identity": {
                    "boundary": identity.boundary,
                    "namespace": identity.namespace,
                    "reference": identity.reference,
                },
                "kind": "code",
                "language": "python",
                "source": "pass",
            }
        ],
    }


def test_notebook_document_rejects_invalid_cell_values() -> None:
    cases: tuple[tuple[str, object, type[Exception], str], ...] = (
        ("kind", "raw", ValueError, "cell.kind"),
        ("language", 1, TypeError, "cell.language"),
        ("dependencies", "none", TypeError, "cell.dependencies"),
        ("id", 1, TypeError, "cell.id"),
        ("source", 1, TypeError, "cell.source"),
    )
    for key, value, error_type, match in cases:
        data = _single_cell_data()
        cells = data["cells"]
        assert isinstance(cells, list)
        cell = cells[0]
        assert isinstance(cell, dict)
        cell[key] = value
        with pytest.raises(error_type, match=match):
            NotebookDocument.from_data(data)

    data = _single_cell_data()
    cells = data["cells"]
    assert isinstance(cells, list)
    cell = cells[0]
    assert isinstance(cell, dict)
    cell["dependencies"] = [1]
    with pytest.raises(TypeError, match="cell dependency"):
        NotebookDocument.from_data(data)


def test_notebook_document_rejects_invalid_identity_values() -> None:
    data = _single_cell_data()
    cells = data["cells"]
    assert isinstance(cells, list)
    cell = cells[0]
    assert isinstance(cell, dict)
    cell["identity"] = 1
    with pytest.raises(TypeError, match="cell.identity"):
        NotebookDocument.from_data(data)

    for key, value, error_type, match in (
        ("boundary", "runtime", ValueError, "boundary"),
        ("boundary", 1, TypeError, "boundary"),
        ("namespace", 1, TypeError, "namespace"),
        ("reference", 1, TypeError, "reference"),
    ):
        data = _single_cell_data()
        cells = data["cells"]
        assert isinstance(cells, list)
        cell = cells[0]
        assert isinstance(cell, dict)
        identity = cell["identity"]
        assert isinstance(identity, dict)
        identity[key] = value
        with pytest.raises(error_type, match=match):
            NotebookDocument.from_data(data)

    data = _single_cell_data()
    cells = data["cells"]
    assert isinstance(cells, list)
    cell = cells[0]
    assert isinstance(cell, dict)
    identity = cell["identity"]
    assert isinstance(identity, dict)
    identity["extra"] = True
    with pytest.raises(ValueError, match="cell.identity keys mismatch"):
        NotebookDocument.from_data(data)


def test_notebook_import_preserves_source_identity_across_edits_and_order_changes() -> None:
    original_cells = (
        NotebookImportCell("intro", "markdown", "# Intro"),
        NotebookImportCell("extract", "code", "x = 1", language="python"),
        NotebookImportCell(
            "query",
            "sql",
            "select 1",
            dependency_references=("extract",),
            language="ansi-sql",
        ),
    )
    original = import_notebook("nbformat:/repo/demo.ipynb", original_cells)
    edited = import_notebook(
        "nbformat:/repo/demo.ipynb",
        (
            NotebookImportCell(
                "query",
                "sql",
                "select 2",
                dependency_references=("extract",),
                language="ansi-sql",
            ),
            NotebookImportCell("extract", "code", "x = 2", language="python"),
            NotebookImportCell("intro", "markdown", "# Renamed"),
        ),
    )

    original_ids = {
        identity.reference: cell.id
        for identity, cell in zip(
            original.cell_identities,
            original.notebook.cells,
            strict=True,
        )
    }
    edited_ids = {
        identity.reference: cell.id
        for identity, cell in zip(
            edited.cell_identities,
            edited.notebook.cells,
            strict=True,
        )
    }
    assert edited_ids == original_ids
    assert edited.notebook.cells[0].dependencies == (original_ids["extract"],)
    assert NotebookDocument.from_json(original.to_json()) == original

    another_document = import_notebook(
        "nbformat:/repo/other.ipynb",
        (NotebookImportCell("extract", "code", "x = 1", language="python"),),
    )
    assert another_document.notebook.cells[0].id != original_ids["extract"]


def test_notebook_import_rejects_ambiguous_or_invalid_references() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        NotebookImportCell(" cell ", "code", "pass", language="python")
    with pytest.raises(ValueError, match="single-line"):
        NotebookImportCell("cell\nnext", "code", "pass", language="python")
    with pytest.raises(ValueError, match="unique"):
        NotebookImportCell(
            "cell",
            "code",
            "pass",
            dependency_references=("other", "other"),
            language="python",
        )
    with pytest.raises(ValueError, match="itself"):
        NotebookImportCell(
            "cell",
            "code",
            "pass",
            dependency_references=("cell",),
            language="python",
        )
    with pytest.raises(ValueError, match="unique"):
        import_notebook(
            "demo",
            (
                NotebookImportCell("cell", "code", "pass", language="python"),
                NotebookImportCell("cell", "code", "pass", language="python"),
            ),
        )
    with pytest.raises(ValueError, match="unknown dependency"):
        import_notebook(
            "demo",
            (
                NotebookImportCell(
                    "cell",
                    "code",
                    "pass",
                    dependency_references=("missing",),
                    language="python",
                ),
            ),
        )
    with pytest.raises(ValueError, match="namespace"):
        import_notebook(
            " demo ",
            (NotebookImportCell("cell", "code", "pass", language="python"),),
        )


def test_notebook_import_delegates_semantic_cell_validation() -> None:
    with pytest.raises(ValueError, match="language"):
        import_notebook("demo", (NotebookImportCell("cell", "code", "pass"),))
    with pytest.raises(ValueError, match="execution dependencies"):
        import_notebook(
            "demo",
            (
                NotebookImportCell("code", "code", "pass", language="python"),
                NotebookImportCell(
                    "markdown",
                    "markdown",
                    "text",
                    dependency_references=("code",),
                ),
            ),
        )
