from __future__ import annotations

from pathlib import Path

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


def test_semantic_models_are_durable_and_project_scoped(tmp_path: Path) -> None:
    store = SqliteSemanticStore(tmp_path / "semantic.sqlite")
    model = _model()
    assert store.put_model("project-a", model) == model
    assert store.get_model("project-a", "sales") == model
    assert store.list_models("project-b") == ()
    assert store.list_models("project-a") == (model,)
    with pytest.raises(SemanticModelConflict):
        store.put_model("project-a", _model("Changed"))
    dashboard = DashboardDefinition(
        "sales_dashboard",
        "Sales",
        (DashboardTile("orders", "Orders", "number", MetricQuery("sales", ("orders",))),),
    )
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
    assert target.get_model("project-a", "sales") == model
    assert target.get_dashboard("project-a", "sales_dashboard") == dashboard
