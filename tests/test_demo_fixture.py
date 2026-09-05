from __future__ import annotations

import json
from pathlib import Path

from studio_core import ProjectManifest
from studio_notebook import NotebookDocument, analyze_notebook_dependencies

from examples.demo.build_fixture import build


def test_demo_fixture_is_regenerable() -> None:
    committed = Path("examples/demo/notebooks/etl.ronin.json").read_text(encoding="utf-8")
    assert committed == build()


def test_demo_manifest_round_trips() -> None:
    raw = Path("examples/demo/.ronin/project.json").read_text(encoding="utf-8")
    manifest = ProjectManifest.from_json(raw)
    assert json.loads(manifest.to_json()) == json.loads(raw)
    assert manifest.project.primary_repository.alias == "demo"


def test_demo_dag_shape_is_stable() -> None:
    document = NotebookDocument.from_json(
        Path("examples/demo/notebooks/etl.ronin.json").read_text(encoding="utf-8")
    )
    analysis = analyze_notebook_dependencies(document.notebook)
    assert analysis.is_valid
    assert [len(level) for level in analysis.levels] == [2, 1, 1, 1]
    assert len(analysis.execution_order) == 5


def test_demo_cell_identity_vectors_are_stable() -> None:
    document = NotebookDocument.from_json(
        Path("examples/demo/notebooks/etl.ronin.json").read_text(encoding="utf-8")
    )
    by_reference = {
        identity.reference: cell.id.value
        for cell, identity in zip(document.notebook.cells, document.cell_identities, strict=True)
    }
    assert by_reference["intro"] == "aacc1d52a1fbc20634d366de68a7ad855931e5d39762f05f6697121c6baf66fd"
    assert by_reference["extract-customers"] == "5712e1391ca1bd28b844a6df1a125f71a09910870bb668e7c58fc6eddbbe1fd4"
    assert by_reference["extract-orders"] == "d5b4f0a27829cea13e582da482bfeb869c70dc515995bd10a9a9eb02abad7c9b"
