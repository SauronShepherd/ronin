"""Executable translation subset for Databricks notebook Jobs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from studio_core import Edge, Node, OperatorRef, Pipeline, Port, Schedule, ScheduleId, WorkflowDefinition, WorkflowId
from studio_core.portability import MigrationObjectReport, MigrationReport


@dataclass(frozen=True, slots=True)
class DatabricksTranslation:
    workflow: WorkflowDefinition
    report: MigrationReport
    schedule: Schedule | None = None


def translate_notebook_job(document: str | bytes, *, source_version: str = "unknown") -> DatabricksTranslation:
    try:
        payload: Any = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise ValueError("Databricks Job is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("Databricks Job must be an object")
    job_id = payload.get("job_id", payload.get("id"))
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("Databricks Job requires an explicit string job_id or id")
    tasks = payload.get("tasks")
    if not isinstance(tasks, Sequence) or isinstance(tasks, (str, bytes)) or not tasks:
        raise ValueError("Databricks Job requires a non-empty tasks array")
    nodes: list[Node] = []
    node_by_task: dict[str, Node] = {}
    dependency_keys: dict[str, tuple[str, ...]] = {}
    reports: list[MigrationObjectReport] = []
    for task in tasks:
        if not isinstance(task, Mapping) or not isinstance(task.get("task_key"), str):
            raise ValueError("every Databricks task requires task_key")
        task_key = cast(str, task["task_key"])
        dependencies = task.get("depends_on", ())
        if not isinstance(dependencies, Sequence) or isinstance(dependencies, (str, bytes)):
            raise ValueError("Databricks task depends_on must be an array")
        dependency_names: list[str] = []
        for dependency in dependencies:
            if not isinstance(dependency, Mapping) or not isinstance(dependency.get("task_key"), str):
                raise ValueError("Databricks dependency requires task_key")
            dependency_names.append(dependency["task_key"])
        notebook = task.get("notebook_task")
        if isinstance(notebook, Mapping) and isinstance(notebook.get("notebook_path"), str):
            node = Node.create(operator=OperatorRef("notebook.run"), instance_key=task_key, params={"target": notebook["notebook_path"], "parameters": notebook.get("base_parameters", {})}, inputs=(Port("in"),) if dependency_names else (), outputs=(Port("out"),))
            nodes.append(node)
            node_by_task[task_key] = node
            dependency_keys[task_key] = tuple(dependency_names)
            reports.append(MigrationObjectReport("notebook_task", task_key, "translated", (f"workflow-node:{task_key}",), ("Databricks notebook task translated to Ronin notebook.run",)))
        else:
            reports.append(MigrationObjectReport("task", task_key, "unsupported", (), ("Only notebook_task is executable in this translation subset",)))
    if not nodes:
        raise ValueError("Databricks Job contains no executable notebook tasks")
    edges: list[Edge] = []
    for task_key, dependencies_for_task in dependency_keys.items():
        target = node_by_task[task_key]
        for dependency_key in dependencies_for_task:
            source = node_by_task.get(dependency_key)
            if source is None:
                raise ValueError("Databricks dependency references a non-executable task")
            edges.append(Edge(source.id, "out", target.id, "in"))
    workflow = WorkflowDefinition(WorkflowId(f"databricks-job-{job_id}"), str(payload.get("name", job_id)), Pipeline(tuple(nodes), tuple(edges)))
    reports.append(MigrationObjectReport("job", job_id, "translated", (str(workflow.id),), ("Job translated with notebook-task subset; schedules and unsupported tasks require review",)))
    schedule_value = payload.get("schedule")
    schedule: Schedule | None = None
    if schedule_value is not None:
        if not isinstance(schedule_value, Mapping) or not isinstance(schedule_value.get("cron"), str):
            raise ValueError("Databricks schedule requires a cron string")
        schedule = Schedule(ScheduleId(f"databricks-schedule-{job_id}"), workflow.id, schedule_value["cron"])
    return DatabricksTranslation(workflow, MigrationReport("databricks", source_version, "ronin-databricks-0.1", tuple(reports)), schedule)


__all__ = ("DatabricksTranslation", "translate_notebook_job")
