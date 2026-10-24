from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier

import pytest
from studio_semantic import (
    DashboardDefinition,
    DashboardTile,
    MetricQuery,
    SemanticMeasure,
    SemanticModel,
    SemanticModelConflict,
    SqliteSemanticStore,
    commit_semantic_bundle_import,
    export_semantic_bundle,
    plan_semantic_bundle_import,
)


def _model(name: str = "Sales") -> SemanticModel:
    return SemanticModel("sales", name, "orders", measures=(SemanticMeasure("orders", "count"),))


def _dashboard(title: str = "Sales") -> DashboardDefinition:
    return DashboardDefinition(
        "sales_dashboard",
        title,
        (DashboardTile("orders", "Orders", "number", MetricQuery("sales", ("orders",))),),
    )


def test_semantic_models_are_durable_and_project_scoped(tmp_path: Path) -> None:
    store = SqliteSemanticStore(tmp_path / "semantic.sqlite")
    model = _model()
    assert store.put_model("project-a", model) == model
    assert store.get_model("project-a", "sales") == model
    assert store.list_models("project-b") == ()
    assert store.list_models("project-a") == (model,)
    with pytest.raises(SemanticModelConflict):
        store.put_model("project-a", _model("Changed"))
    dashboard = _dashboard()
    assert store.put_dashboard("project-a", dashboard) == dashboard
    assert store.get_dashboard("project-a", "sales_dashboard") == dashboard
    assert store.list_dashboards("project-a") == (dashboard,)


def test_semantic_store_rejects_invalid_project_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="project_id"):
        SqliteSemanticStore(tmp_path / "semantic.sqlite").list_models(" ")


def test_semantic_bundle_round_trip_is_deterministic(tmp_path: Path) -> None:
    source = SqliteSemanticStore(tmp_path / "source.sqlite")
    model = _model()
    source.put_model("project-a", model)
    dashboard = DashboardDefinition(
        "sales_dashboard",
        "Sales",
        (DashboardTile("orders", "Orders", "number", MetricQuery("sales", ("orders",))),),
    )
    source.put_dashboard("project-a", dashboard)
    first = tmp_path / "first.roninbundle"
    second = tmp_path / "second.roninbundle"
    export_semantic_bundle("project-a", source, first)
    export_semantic_bundle("project-a", source, second)
    assert first.read_bytes() == second.read_bytes()
    target = SqliteSemanticStore(tmp_path / "target.sqlite")
    plan = plan_semantic_bundle_import(first)
    assert plan.models == (model,)
    commit_semantic_bundle_import(first, "project-a", target)
    commit_semantic_bundle_import(first, "project-a", target)
    assert target.get_model("project-a", "sales") == model
    assert target.get_dashboard("project-a", "sales_dashboard") == dashboard


def test_semantic_bundle_import_rolls_back_models_when_dashboard_write_fails(
    tmp_path: Path,
) -> None:
    source = SqliteSemanticStore(tmp_path / "source.sqlite")
    source.put_model("project-a", _model())
    source.put_dashboard("project-a", _dashboard())
    bundle = tmp_path / "semantic.roninbundle"
    export_semantic_bundle("project-a", source, bundle)

    target_path = tmp_path / "target.sqlite"
    target = SqliteSemanticStore(target_path)
    with closing(sqlite3.connect(target_path)) as connection, connection:
        connection.execute(
            "CREATE TRIGGER reject_semantic_dashboard BEFORE INSERT ON semantic_dashboards "
            "BEGIN SELECT RAISE(ABORT, 'injected dashboard write failure'); END"
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected dashboard write failure"):
        commit_semantic_bundle_import(bundle, "project-a", target)

    assert target.list_models("project-a") == ()
    assert target.list_dashboards("project-a") == ()


def test_semantic_bundle_conflict_does_not_commit_earlier_model(
    tmp_path: Path,
) -> None:
    source = SqliteSemanticStore(tmp_path / "source.sqlite")
    source.put_model("project-a", _model())
    source.put_dashboard("project-a", _dashboard())
    bundle = tmp_path / "semantic.roninbundle"
    export_semantic_bundle("project-a", source, bundle)

    target = SqliteSemanticStore(tmp_path / "target.sqlite")
    target.put_dashboard("project-a", _dashboard("Different title"))
    with pytest.raises(SemanticModelConflict, match="dashboard already exists"):
        commit_semantic_bundle_import(bundle, "project-a", target)

    assert target.list_models("project-a") == ()
    assert target.list_dashboards("project-a") == (_dashboard("Different title"),)


def test_concurrent_conflicting_semantic_bundle_imports_have_one_winner(
    tmp_path: Path,
) -> None:
    target = SqliteSemanticStore(tmp_path / "target.sqlite")
    bundles: list[Path] = []
    for index, title in enumerate(("First definition", "Second definition")):
        source = SqliteSemanticStore(tmp_path / f"source-{index}.sqlite")
        source.put_model("project-a", _model(title))
        bundle = tmp_path / f"semantic-{index}.roninbundle"
        export_semantic_bundle("project-a", source, bundle)
        bundles.append(bundle)

    barrier = Barrier(2)

    def import_bundle(bundle: Path) -> str:
        barrier.wait(timeout=10)
        try:
            commit_semantic_bundle_import(bundle, "project-a", target)
        except SemanticModelConflict:
            return "conflict"
        return "committed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(import_bundle, bundles))

    assert sorted(outcomes) == ["committed", "conflict"]
    assert len(target.list_models("project-a")) == 1
    assert target.get_model("project-a", "sales") in {
        _model("First definition"),
        _model("Second definition"),
    }
