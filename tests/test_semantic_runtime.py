from studio_semantic import (
    DashboardDefinition,
    DashboardTile,
    MetricQuery,
    SemanticDimension,
    SemanticFilter,
    SemanticMeasure,
    SemanticModel,
    SemanticQueryError,
    SemanticRuntime,
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
    assert 'SUM("amount") AS "revenue"' in compiled.sql
    assert 'GROUP BY "country"' in compiled.sql


def test_unknown_semantic_field_fails_closed() -> None:
    query = MetricQuery("sales", ("missing",))
    try:
        compile_metric_query(_model(), query)
    except SemanticQueryError as exc:
        assert "unknown measures" in str(exc)
    else:
        raise AssertionError("unknown semantic measure must fail")


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
