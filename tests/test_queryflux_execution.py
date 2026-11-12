from studio_data_engineering import plan_queryflux_execution


def test_queryflux_execution_plan_is_idempotent_for_same_scope_and_attempt() -> None:
    kwargs = {
        "workspace_id": "workspace-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "attempt_id": "attempt-1",
        "sql": "SELECT 1",
        "engine": "trino",
        "translation_policy": "strict",
        "max_rows": 100,
        "page_size": 50,
        "max_result_bytes": 4096,
        "parameters": [],
        "now": "2026-11-12T00:00:00.000000Z",
    }
    first = plan_queryflux_execution(**kwargs)
    second = plan_queryflux_execution(**kwargs)
    assert first.job.id == second.job.id
    assert first.run.id == second.run.id
    assert first.job.idempotency_key == (
        "queryflux:workspace-1:project-1:run-1:attempt-1"
    )
    assert first.job.target == "data-engineering.queryflux-execution.v1"


def test_queryflux_execution_plan_rejects_unbounded_limits() -> None:
    try:
        plan_queryflux_execution(
            workspace_id="workspace-1",
            project_id="project-1",
            run_id="run-1",
            attempt_id="attempt-1",
            sql="SELECT 1",
            engine="trino",
            translation_policy="strict",
            max_rows=0,
            page_size=50,
            max_result_bytes=4096,
            now="2026-11-12T00:00:00.000000Z",
        )
    except ValueError as error:
        assert "limits" in str(error)
    else:
        raise AssertionError("invalid QueryFlux limits must be rejected")
