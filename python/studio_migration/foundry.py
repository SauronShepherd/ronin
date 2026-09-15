"""Executable translation subset for Palantir Foundry/AIP Python functions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from studio_core import Node, OperatorRef, Pipeline, WorkflowDefinition, WorkflowId
from studio_core.portability import MigrationObjectReport, MigrationReport


@dataclass(frozen=True, slots=True)
class FoundryTranslation:
    workflow: WorkflowDefinition
    report: MigrationReport


def translate_python_functions(document: str | bytes, *, source_version: str = "unknown") -> FoundryTranslation:
    try:
        payload: Any = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise ValueError("Foundry export is not valid JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("functions"), Sequence) or isinstance(payload["functions"], (str, bytes)):
        raise ValueError("Foundry export requires a functions array")
    project_id = payload.get("project_id", payload.get("id"))
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("Foundry export requires an explicit project_id or id")
    nodes: list[Node] = []
    reports: list[MigrationObjectReport] = []
    for function in payload["functions"]:
        if not isinstance(function, Mapping) or not isinstance(function.get("id"), str):
            raise ValueError("every Foundry function requires an explicit id")
        function_id = function["id"]
        source = function.get("source")
        if isinstance(source, str):
            nodes.append(Node.create(operator=OperatorRef("code.python"), instance_key=function_id, params={"source": source}))
            reports.append(MigrationObjectReport("function", function_id, "translated", (f"workflow-node:{function_id}",), ("Foundry Python function translated to Ronin code.python",)))
        else:
            reports.append(MigrationObjectReport("function", function_id, "unsupported", (), ("Function has no portable Python source",)))
    if not nodes:
        raise ValueError("Foundry export contains no executable Python functions")
    workflow = WorkflowDefinition(WorkflowId(f"foundry-project-{project_id}"), str(payload.get("name", project_id)), Pipeline(tuple(nodes)))
    return FoundryTranslation(workflow, MigrationReport("palantir-foundry-aip", source_version, "ronin-foundry-0.1", tuple(reports)))


__all__ = ("FoundryTranslation", "translate_python_functions")
