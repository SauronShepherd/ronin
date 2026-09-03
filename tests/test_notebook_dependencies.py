from __future__ import annotations

import pytest

from studio_notebook import CellId, Notebook, NotebookCell, analyze_notebook_dependencies


def code(cell_id: str, *, dependencies: tuple[str, ...] = ()) -> NotebookCell:
    return NotebookCell(
        id=CellId(cell_id),
        kind="code",
        language="python",
        source=f"# {cell_id}",
        dependencies=tuple(CellId(value) for value in dependencies),
    )


def test_cell_id_rejects_unstable_text() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        CellId(" x ")
    with pytest.raises(ValueError, match="single-line"):
        CellId("x\ny")


def test_cell_contract_rejects_invalid_execution_metadata() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        NotebookCell(CellId("x"), "shell", "echo x")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="execution language"):
        NotebookCell(CellId("x"), "markdown", "hello", language="markdown")
    with pytest.raises(ValueError, match="execution dependencies"):
        NotebookCell(
            CellId("x"),
            "markdown",
            "hello",
            dependencies=(CellId("code"),),
        )
    with pytest.raises(ValueError, match="require"):
        NotebookCell(CellId("x"), "code", "pass")
    with pytest.raises(ValueError, match="trimmed"):
        NotebookCell(CellId("x"), "sql", "select 1", language=" sql ")


def test_cell_dependencies_are_canonical_and_reject_ambiguity() -> None:
    cell = code("c", dependencies=("b", "a"))
    assert cell.dependencies == (CellId("a"), CellId("b"))
    with pytest.raises(ValueError, match="unique"):
        code("c", dependencies=("a", "a"))
    with pytest.raises(ValueError, match="itself"):
        code("c", dependencies=("c",))


def test_notebook_rejects_duplicate_cell_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        Notebook((code("a"), code("a")))


def test_dependency_analysis_is_stable_and_preserves_authored_ties() -> None:
    notebook = Notebook(
        (
            code("extract"),
            code("lookup"),
            code("join", dependencies=("lookup", "extract")),
            code("publish", dependencies=("join",)),
        )
    )

    analysis = analyze_notebook_dependencies(notebook)

    assert analysis.is_valid
    assert analysis.execution_order == tuple(
        CellId(value) for value in ("extract", "lookup", "join", "publish")
    )
    assert analysis.levels == (
        (CellId("extract"), CellId("lookup")),
        (CellId("join"),),
        (CellId("publish"),),
    )


def test_dependency_analysis_reorders_forward_dependencies() -> None:
    notebook = Notebook(
        (code("consumer", dependencies=("producer",)), code("producer"))
    )
    analysis = analyze_notebook_dependencies(notebook)
    assert analysis.is_valid
    assert analysis.execution_order == (CellId("producer"), CellId("consumer"))


def test_markdown_is_document_content_not_an_execution_step() -> None:
    notebook = Notebook(
        (
            NotebookCell(CellId("intro"), "markdown", "# Intro"),
            code("run"),
        )
    )
    analysis = analyze_notebook_dependencies(notebook)
    assert analysis.is_valid
    assert analysis.execution_order == (CellId("run"),)
    assert analysis.levels == ((CellId("run"),),)


def test_non_executable_dependency_returns_actionable_evidence() -> None:
    notebook = Notebook(
        (
            NotebookCell(CellId("intro"), "markdown", "# Intro"),
            code("consumer", dependencies=("intro",)),
        )
    )
    analysis = analyze_notebook_dependencies(notebook)
    assert not analysis.is_valid
    assert analysis.execution_order == ()
    assert analysis.levels == ()
    assert len(analysis.violations) == 1
    violation = analysis.violations[0]
    assert violation.code == "non_executable_dependency"
    assert violation.cell_id == CellId("consumer")
    assert violation.dependency_id == CellId("intro")
    assert "non-executable cell intro" in violation.message


def test_unknown_dependency_returns_actionable_evidence() -> None:
    analysis = analyze_notebook_dependencies(
        Notebook((code("consumer", dependencies=("missing",)),))
    )
    assert not analysis.is_valid
    assert analysis.execution_order == ()
    assert analysis.levels == ()
    assert len(analysis.violations) == 1
    violation = analysis.violations[0]
    assert violation.code == "unknown_dependency"
    assert violation.cell_id == CellId("consumer")
    assert violation.dependency_id == CellId("missing")
    assert "unknown cell missing" in violation.message


def test_invalid_dependencies_are_sorted_deterministically() -> None:
    analysis = analyze_notebook_dependencies(
        Notebook(
            (
                code("z", dependencies=("missing-z",)),
                code("a", dependencies=("missing-a",)),
            )
        )
    )
    assert tuple(item.cell_id for item in analysis.violations) == (
        CellId("a"),
        CellId("z"),
    )


def test_cycle_returns_all_involved_cells_without_partial_plan() -> None:
    analysis = analyze_notebook_dependencies(
        Notebook(
            (
                code("a", dependencies=("b",)),
                code("b", dependencies=("a",)),
                code("free"),
            )
        )
    )
    assert not analysis.is_valid
    assert analysis.execution_order == ()
    assert analysis.levels == ()
    assert tuple(item.cell_id for item in analysis.violations) == (
        CellId("a"),
        CellId("b"),
    )
    assert all(item.code == "dependency_cycle" for item in analysis.violations)


def test_empty_notebook_has_empty_valid_plan() -> None:
    analysis = analyze_notebook_dependencies(Notebook())
    assert analysis.is_valid
    assert analysis.execution_order == ()
    assert analysis.levels == ()
