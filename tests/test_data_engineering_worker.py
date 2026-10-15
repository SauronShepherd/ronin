import pytest
from studio_data_engineering import (
    PipelineExecutionError,
    execute_pipeline_job,
    persist_pipeline_evidence,
)
from studio_data_engineering.spark_connect import SparkConnectResult
from studio_storage import LocalArtifactStore


def test_local_preview_worker_returns_evidence() -> None:
    result = execute_pipeline_job(
        {
            "runtime": "local-preview",
            "pipeline": {"config": {"name": "main"}, "nodes": [], "edges": []},
            "fixtures": {},
        }
    )
    assert result.state == "succeeded"
    assert result.evidence["kind"] == "data-engineering.preview"
    assert result.evidence["payload_digest"]


def test_worker_requires_endpoint_for_spark_connect() -> None:
    with pytest.raises(PipelineExecutionError, match="endpoint is required") as error:
        execute_pipeline_job(
            {
                "runtime": "spark-connect",
                "pipeline": {"config": {"name": "main"}, "nodes": [], "edges": []},
            }
        )
    assert error.value.code == "DE-EXEC-006"


def test_worker_requires_compiled_sql_for_spark_connect() -> None:
    with pytest.raises(PipelineExecutionError, match="compiled SQL is required") as error:
        execute_pipeline_job(
            {
                "runtime": "spark-connect",
                "endpoint": "sc://local",
                "pipeline": {"config": {"name": "main"}, "nodes": [], "edges": []},
            }
        )
    assert error.value.code == "DE-EXEC-007"


def test_worker_delegates_spark_connect_execution(monkeypatch) -> None:
    def execute(_self, _sql, *, limit):
        assert limit == 10
        return SparkConnectResult(({"value": 1},), 1, "sc://local")

    monkeypatch.setattr("studio_data_engineering.worker.SparkConnectProvider.execute_sql", execute)
    result = execute_pipeline_job(
        {
            "runtime": "spark-connect",
            "endpoint": "sc://local",
            "sql": "select 1",
            "pipeline": {},
            "row_limit": 10,
        }
    )
    assert result.state == "succeeded"
    assert result.output["row_count"] == 1


def test_worker_result_can_be_persisted_as_evidence(tmp_path) -> None:
    result = execute_pipeline_job(
        {
            "runtime": "local-preview",
            "pipeline": {"config": {"name": "main"}, "nodes": [], "edges": []},
            "fixtures": {},
        }
    )
    ref = persist_pipeline_evidence(
        LocalArtifactStore(tmp_path / "artifacts"),
        project_id="p",
        run_id="run-1",
        output=result.output,
        evidence=result.evidence,
    )
    assert ref.media_type == "application/json"
