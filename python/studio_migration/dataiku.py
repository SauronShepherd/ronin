"""Executable translation subset for Dataiku DSS code recipes."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from studio_core import Node, OperatorRef, Pipeline, WorkflowDefinition, WorkflowId
from studio_core.portability import MigrationObjectReport, MigrationReport


@dataclass(frozen=True, slots=True)
class DataikuTranslation:
    workflow: WorkflowDefinition
    report: MigrationReport


def translate_code_recipes(document: str | bytes, *, source_version: str = "unknown") -> DataikuTranslation:
    try:
        payload: Any = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dataiku export is not valid JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("recipes"), Sequence) or isinstance(payload["recipes"], (str, bytes)):
        raise ValueError("Dataiku export requires a recipes array")
    project_id = payload.get("project_id", payload.get("id"))
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("Dataiku export requires an explicit project_id or id")
    nodes: list[Node] = []
    reports: list[MigrationObjectReport] = []
    for recipe in payload["recipes"]:
        if not isinstance(recipe, Mapping) or not isinstance(recipe.get("id"), str):
            raise ValueError("every Dataiku recipe requires an explicit id")
        recipe_id = recipe["id"]
        kind = recipe.get("type")
        source = recipe.get("source")
        if kind == "python" and isinstance(source, str):
            operator = "code.python"
        elif kind == "sql" and isinstance(source, str):
            operator = "sql.query"
        else:
            reports.append(MigrationObjectReport(str(kind or "recipe"), recipe_id, "unsupported", (), ("Only explicit Python and SQL recipe sources are executable in this subset",)))
            continue
        nodes.append(Node.create(operator=OperatorRef(operator), instance_key=recipe_id, params={"source": source}))
        reports.append(MigrationObjectReport(str(kind), recipe_id, "translated", (f"workflow-node:{recipe_id}",), (f"Dataiku {kind} recipe translated to {operator}",)))
    if not nodes:
        raise ValueError("Dataiku export contains no executable code recipes")
    workflow = WorkflowDefinition(WorkflowId(f"dataiku-project-{project_id}"), str(payload.get("name", project_id)), Pipeline(tuple(nodes)))
    return DataikuTranslation(workflow, MigrationReport("dataiku-dss", source_version, "ronin-dataiku-0.1", tuple(reports)))


__all__ = ("DataikuTranslation", "translate_code_recipes")
