import pytest
from studio_semantic import (
    MAX_DASHBOARD_EXECUTION_MS,
    MAX_DASHBOARD_QUERY_BYTES,
    MAX_DASHBOARD_ROWS,
    MAX_DASHBOARD_TILES,
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
from studio_sql import SqlColumn, SqlQueryResult, SqlResultLimitError, SqlTimeoutError


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
        self.execution_limits: list[tuple[int, int]] = []

    def register_parquet(self, name: str, path: str) -> None:
        del name, path

    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
        timeout_ms: int = 5_000,
        max_result_bytes: int = 1_048_576,
    ) -> SqlQueryResult:
        self.calls.append((sql, parameters, max_rows))
        self.execution_limits.append((timeout_ms, max_result_bytes))
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
        self.execution_limits: list[tuple[int, int]] = []

    def execute(
        self,
        project_id: str,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
        timeout_ms: int = 5_000,
        max_result_bytes: int = 1_048_576,
    ) -> SqlQueryResult:
        del parameters
        self.calls.append((project_id, sql, max_rows))
        self.execution_limits.append((timeout_ms, max_result_bytes))
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
    assert 0 < engine.execution_limits[-1][0] <= MAX_DASHBOARD_EXECUTION_MS
    assert engine.execution_limits[-1][1] <= MAX_DASHBOARD_QUERY_BYTES


def _execute_test_dashboard(engine, dashboard, models):
    if isinstance(engine, _ProjectScopedFakeEngine):
        return ProjectScopedSemanticRuntime(engine).execute_dashboard_for_project(
            "project", models, dashboard
        )
    return SemanticRuntime(engine).execute_dashboard(models, dashboard)


@pytest.mark.parametrize("project_scoped", [False, True])
def test_dashboard_rejects_fanout_and_aggregate_rows_before_any_query(project_scoped) -> None:
    engine = _ProjectScopedFakeEngine() if project_scoped else _FakeEngine()
    models = {"sales": _model()}
    tiles = tuple(
        DashboardTile(
            f"tile_{index}",
            f"Tile {index}",
            "number",
            MetricQuery("sales", ("orders",)),
        )
        for index in range(MAX_DASHBOARD_TILES + 1)
    )
    over_fanout = DashboardDefinition("too_many", "Too many", tiles)
    with pytest.raises(ValueError, match="exceeds 12 tiles"):
        _execute_test_dashboard(engine, over_fanout, models)
    assert engine.calls == []

    over_budget = DashboardDefinition(
        "too_many_rows",
        "Too many rows",
        (
            DashboardTile("tile_a", "A", "table", MetricQuery("sales", ("orders",), limit=60_000)),
            DashboardTile("tile_b", "B", "table", MetricQuery("sales", ("orders",), limit=60_000)),
        ),
    )
    with pytest.raises(ValueError, match=f"aggregate row budget of {MAX_DASHBOARD_ROWS}"):
        _execute_test_dashboard(engine, over_budget, models)
    assert engine.calls == []


@pytest.mark.parametrize("project_scoped", [False, True])
def test_dashboard_precompiles_all_tiles_before_executing(project_scoped) -> None:
    engine = _ProjectScopedFakeEngine() if project_scoped else _FakeEngine()
    dashboard = DashboardDefinition(
        "stale_reference",
        "Stale reference",
        (
            DashboardTile("tile_a", "A", "number", MetricQuery("sales", ("orders",))),
            DashboardTile("tile_b", "B", "number", MetricQuery("missing", ("orders",))),
        ),
    )
    with pytest.raises(KeyError, match="unknown semantic model: missing"):
        _execute_test_dashboard(engine, dashboard, {"sales": _model()})
    assert engine.calls == []


@pytest.mark.parametrize("project_scoped", [False, True])
def test_dashboard_global_timeout_stops_before_starting_another_tile(
    project_scoped, monkeypatch
) -> None:
    engine = _ProjectScopedFakeEngine() if project_scoped else _FakeEngine()
    dashboard = DashboardDefinition(
        "deadline",
        "Deadline",
        tuple(
            DashboardTile(
                f"tile_{index}",
                f"Tile {index}",
                "number",
                MetricQuery("sales", ("orders",)),
            )
            for index in range(2)
        ),
    )
    clock = iter((100.0, 100.001, 115.0))
    monkeypatch.setattr("studio_semantic.runtime.monotonic", lambda: next(clock))
    with pytest.raises(SqlTimeoutError, match="total execution time limit"):
        _execute_test_dashboard(engine, dashboard, {"sales": _model()})
    assert len(engine.calls) == 1
    assert 0 < engine.execution_limits[0][0] <= MAX_DASHBOARD_EXECUTION_MS - 1


class _OversizedDashboardEngine(_FakeEngine):
    def execute(
        self,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
        timeout_ms: int = 5_000,
        max_result_bytes: int = 1_048_576,
    ) -> SqlQueryResult:
        self.calls.append((sql, parameters, max_rows))
        self.execution_limits.append((timeout_ms, max_result_bytes))
        return SqlQueryResult((SqlColumn("orders", "VARCHAR"),), (("x" * (max_result_bytes + 1),),))


class _ProjectScopedOversizedDashboardEngine(_ProjectScopedFakeEngine):
    def execute(
        self,
        project_id: str,
        sql: str,
        parameters: tuple[object, ...] = (),
        *,
        max_rows: int = 10_000,
        timeout_ms: int = 5_000,
        max_result_bytes: int = 1_048_576,
    ) -> SqlQueryResult:
        del parameters
        self.calls.append((project_id, sql, max_rows))
        self.execution_limits.append((timeout_ms, max_result_bytes))
        return SqlQueryResult((SqlColumn("orders", "VARCHAR"),), (("x" * (max_result_bytes + 1),),))


@pytest.mark.parametrize("project_scoped", [False, True])
def test_dashboard_total_result_budget_fails_without_returning_partial_results(project_scoped):
    engine = (
        _ProjectScopedOversizedDashboardEngine() if project_scoped else _OversizedDashboardEngine()
    )
    dashboard = DashboardDefinition(
        "oversized",
        "Oversized",
        (
            DashboardTile("tile_a", "A", "table", MetricQuery("sales", ("orders",))),
            DashboardTile("tile_b", "B", "table", MetricQuery("sales", ("orders",))),
        ),
    )
    with pytest.raises(SqlResultLimitError, match="total response byte limit"):
        _execute_test_dashboard(engine, dashboard, {"sales": _model()})
    assert len(engine.calls) == 1


@pytest.mark.parametrize("project_scoped", [False, True])
def test_dashboard_budgets_execute_against_real_duckdb(project_scoped, tmp_path) -> None:
    pytest.importorskip("pyarrow")
    from studio_lakehouse import write_parquet_rows
    from studio_sql import DuckDbSqlEngine, ProjectScopedDuckDbSqlEngine

    parquet = tmp_path / "orders.parquet"
    write_parquet_rows(
        parquet,
        (
            {"country": "ES", "status": "done", "amount": 5},
            {"country": "US", "status": "done", "amount": 7},
        ),
    )
    dashboard = DashboardDefinition(
        "real_dashboard",
        "Real dashboard",
        (
            DashboardTile(
                "total_orders", "Total orders", "number", MetricQuery("sales", ("orders",))
            ),
            DashboardTile(
                "revenue_by_country",
                "Revenue by country",
                "bar",
                MetricQuery("sales", ("revenue",), ("country",), limit=10),
            ),
        ),
    )
    model = _model()
    if project_scoped:
        with ProjectScopedDuckDbSqlEngine() as engine:
            engine.register_parquet("project", "orders", str(parquet))
            results = ProjectScopedSemanticRuntime(engine).execute_dashboard_for_project(
                "project", {"sales": model}, dashboard
            )
    else:
        with DuckDbSqlEngine() as engine:
            engine.register_parquet("orders", str(parquet))
            results = SemanticRuntime(engine).execute_dashboard({"sales": model}, dashboard)

    assert [result.tile_id for result in results] == ["revenue_by_country", "total_orders"]
    by_country = results[0].result.rows
    assert {tuple(row) for row in by_country} == {("ES", 5), ("US", 7)}
    assert results[1].result.rows == ((2,),)


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
