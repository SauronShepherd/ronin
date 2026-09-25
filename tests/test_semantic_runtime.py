import pytest

from studio_semantic import (
    DashboardDefinition,
    DashboardTile,
    MetricQuery,
    ProjectScopedSemanticRuntime,
    SemanticDimension,
    SemanticFilter,
    SemanticHTTPAdapter,
    SemanticJoin,
    SemanticMeasure,
    SemanticModel,
    SemanticQueryError,
    SemanticRuntime,
    SqliteSemanticStore,
    compile_metric_query,
)
from studio_sql import SqlColumn, SqlQueryResult


def _model() -> SemanticModel:
    return SemanticModel(
        "sales",
        "Sales",
        "orders",
        (
            SemanticDimension("country", "country"),
            SemanticDimension("status", "status"),
        ),
        (
            SemanticMeasure("revenue", "sum", "amount"),
            SemanticMeasure("orders", "count"),
        ),
    )


def test_metric_query_compiles_filters_as_parameters() -> None:
    query = MetricQuery(
        "sales",
        ("revenue",),
        ("country",),
        (SemanticFilter("status", "eq", ("done' OR 1=1 --",)),),
        100,
    )
    compiled = compile_metric_query(_model(), query)
    assert "done' OR 1=1 --" not in compiled.sql
    assert compiled.parameters == ("done' OR 1=1 --",)


def test_calculated_measure_compiles_only_from_declared_base_measures() -> None:
    model = SemanticModel(
        "sales",
        "Sales",
        "orders",
        measures=(
            SemanticMeasure("revenue", "sum", "amount"),
            SemanticMeasure("orders", "count"),
            SemanticMeasure("revenue_per_order", "sum", "amount", "revenue / orders"),
        ),
    )
    compiled = compile_metric_query(model, MetricQuery("sales", ("revenue_per_order",)))
    assert '"revenue_per_order"' in compiled.sql
    assert 'SUM("amount")' in compiled.sql
    assert "COUNT(*)" in compiled.sql


def test_unknown_semantic_field_fails_closed() -> None:
    query = MetricQuery("sales", ("missing",))
    with pytest.raises(SemanticQueryError, match="unknown measures"):
        compile_metric_query(_model(), query)


class _FakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], int]] = []

    def register_parquet(self, name: str, path: str) -> None:
        del name, path

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        self.calls.append((sql, parameters, max_rows))
        return SqlQueryResult((SqlColumn("orders", "BIGINT"),), ((3,),))

    def close(self) -> None:
        return None


def test_dashboard_executes_tiles_through_sql_engine() -> None:
    engine = _FakeEngine()
    runtime = SemanticRuntime(engine)
    dashboard = DashboardDefinition(
        "exec",
        "Executive",
        (DashboardTile("orders", "Orders", "number", MetricQuery("sales", ("orders",))),),
    )
    results = runtime.execute_dashboard({"sales": _model()}, dashboard)
    assert results[0].tile_id == "orders"
    assert results[0].result.rows == ((3,),)
    assert len(engine.calls) == 1


def test_runtime_executes_bounded_join_chain() -> None:
    engine = _FakeEngine()
    runtime = SemanticRuntime(engine)
    base = SemanticModel("orders", "Orders", "orders", (SemanticDimension("id", "id"),))
    customer = SemanticModel(
        "customers", "Customers", "customers", (SemanticDimension("id", "id"),)
    )
    result = runtime.execute_join_chain(
        base, ((customer, SemanticJoin("customer_id", "id")),), max_rows=42
    )
    assert result.rows == ((3,),)
    assert engine.calls[-1][2] == 42


class _ProjectScopedFakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def execute(
        self,
        project_id: str,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
    ) -> SqlQueryResult:
        del parameters
        self.calls.append((project_id, sql, max_rows))
        return SqlQueryResult((SqlColumn("orders_id", "BIGINT"),), ((7,),))


def test_project_scoped_runtime_executes_bounded_join_chain() -> None:
    engine = _ProjectScopedFakeEngine()
    runtime = ProjectScopedSemanticRuntime(engine)
    base = SemanticModel("orders", "Orders", "orders", (SemanticDimension("id", "id"),))
    customer = SemanticModel(
        "customers", "Customers", "customers", (SemanticDimension("id", "id"),)
    )
    result = runtime.execute_join_chain_for_project(
        "project",
        base,
        ((customer, SemanticJoin("customer_id", "id")),),
        max_rows=42,
    )
    assert result.rows == ((7,),)
    assert engine.calls[-1][0] == "project"
    assert engine.calls[-1][2] == 42


def test_project_scoped_runtime_executes_dashboard_tiles() -> None:
    engine = _ProjectScopedFakeEngine()
    runtime = ProjectScopedSemanticRuntime(engine)
    dashboard = DashboardDefinition(
        "exec",
        "Executive",
        (DashboardTile("orders", "Orders", "number", MetricQuery("sales", ("orders",))),),
    )
    results = runtime.execute_dashboard_for_project("project", {"sales": _model()}, dashboard)
    assert results[0].result.rows == ((7,),)
    assert engine.calls[-1][0] == "project"


def test_semantic_http_adapter_persists_and_queries_bounded_contract(tmp_path) -> None:
    engine = _FakeEngine()
    adapter = SemanticHTTPAdapter(
        SqliteSemanticStore(tmp_path / "semantic.sqlite"), SemanticRuntime(engine)
    )
    model = _model().to_payload()
    assert adapter.put_model("project", model)["id"] == "sales"
    query = MetricQuery("sales", ("orders",)).to_payload()
    result = adapter.query("project", query)
    assert result["rows"] == [[3]]
    with pytest.raises(ValueError, match="object"):
        adapter.query("project", [])


def test_semantic_http_adapter_executes_join_chain(tmp_path) -> None:
    engine = _FakeEngine()
    adapter = SemanticHTTPAdapter(
        SqliteSemanticStore(tmp_path / "semantic.sqlite"), SemanticRuntime(engine)
    )
    left = _model()
    right = SemanticModel("customers", "Customers", "customers", (SemanticDimension("id", "id"),))
    adapter.put_model("project", left.to_payload())
    adapter.put_model("project", right.to_payload())
    result = adapter.join_query(
        "project",
        {
            "base_model_id": "sales",
            "steps": [
                {
                    "model_id": "customers",
                    "left_column": "customer_id",
                    "right_column": "id",
                    "join_type": "left",
                }
            ],
            "limit": 25,
        },
    )
    assert result["rows"] == [[3]]
    assert engine.calls[-1][2] == 25


def test_semantic_http_adapter_executes_project_scoped_join_chain(tmp_path) -> None:
    engine = _ProjectScopedFakeEngine()
    adapter = SemanticHTTPAdapter(
        SqliteSemanticStore(tmp_path / "semantic.sqlite"), ProjectScopedSemanticRuntime(engine)
    )
    left = _model()
    right = SemanticModel("customers", "Customers", "customers", (SemanticDimension("id", "id"),))
    adapter.put_model("project", left.to_payload())
    adapter.put_model("project", right.to_payload())
    result = adapter.join_query(
        "project",
        {
            "base_model_id": "sales",
            "steps": [
                {
                    "model_id": "customers",
                    "left_column": "customer_id",
                    "right_column": "id",
                    "join_type": "left",
                }
            ],
            "limit": 25,
        },
    )
    assert result["rows"] == [[7]]
    assert engine.calls[-1][0] == "project"


def test_semantic_http_adapter_executes_project_scoped_dashboard(tmp_path) -> None:
    engine = _ProjectScopedFakeEngine()
    store = SqliteSemanticStore(tmp_path / "semantic.sqlite")
    adapter = SemanticHTTPAdapter(store, ProjectScopedSemanticRuntime(engine))
    model = _model()
    dashboard = DashboardDefinition(
        "exec",
        "Executive",
        (DashboardTile("orders", "Orders", "number", MetricQuery("sales", ("orders",))),),
    )
    adapter.put_model("project", model.to_payload())
    adapter.put_dashboard("project", dashboard.to_payload())
    result = adapter.execute_dashboard("project", "exec")
    assert result["tiles"][0]["rows"] == [[7]]
