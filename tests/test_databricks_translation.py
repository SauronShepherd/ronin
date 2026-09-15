from __future__ import annotations

from studio_migration import translate_notebook_job


def test_databricks_notebook_job_translates_to_executable_workflow() -> None:
    result = translate_notebook_job(
        '{"job_id":"42","name":"Daily","tasks":[{"task_key":"extract","notebook_task":{"notebook_path":"/Shared/extract","base_parameters":{"limit":"5"}}},{"task_key":"sql","sql_task":{"query_id":"q-1"}}]}',
        source_version="15.4",
    )
    assert result.workflow.name == "Daily"
    assert len(result.workflow.pipeline.nodes) == 1
    assert result.workflow.pipeline.nodes[0].operator.name == "notebook.run"
    assert {item.status for item in result.report.objects} == {"translated", "unsupported"}


def test_databricks_dependencies_become_canonical_dag_edges() -> None:
    result = translate_notebook_job(
        '{"job_id":"7","tasks":[{"task_key":"a","notebook_task":{"notebook_path":"/a"}},{"task_key":"b","depends_on":[{"task_key":"a"}],"notebook_task":{"notebook_path":"/b"}}]}',
    )
    assert len(result.workflow.pipeline.edges) == 1
    assert next(item for item in result.report.objects if item.source_id == "b").status == "translated"


def test_databricks_schedule_is_preserved_as_canonical_schedule() -> None:
    result = translate_notebook_job(
        '{"job_id":"8","schedule":{"cron":"0 5 * * *"},"tasks":[{"task_key":"a","notebook_task":{"notebook_path":"/a"}}]}',
    )
    assert result.schedule is not None
    assert result.schedule.workflow_id == result.workflow.id
