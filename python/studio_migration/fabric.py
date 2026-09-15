"""Executable translation subset for Microsoft Fabric notebook items."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from studio_core import Node, OperatorRef, Pipeline, WorkflowDefinition, WorkflowId
from studio_core.portability import MigrationObjectReport, MigrationReport


@dataclass(frozen=True, slots=True)
class FabricTranslation:
    workflow: WorkflowDefinition
    report: MigrationReport


def translate_notebook_items(
    document: str | bytes, *, source_version: str = "unknown"
) -> FabricTranslation:
    try:
        payload: Any = json.loads(document)
    except (TypeError, ValueError) as exc:
        raise ValueError("Fabric export is not valid JSON") from exc
    if (
        not isinstance(payload, Mapping)
        or not isinstance(payload.get("items"), Sequence)
        or isinstance(payload["items"], (str, bytes))
    ):
        raise ValueError("Fabric export requires an items array")
    project_id = payload.get("project_id", payload.get("id"))
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("Fabric export requires an explicit project_id or id")
    nodes: list[Node] = []
    reports: list[MigrationObjectReport] = []
    for item in payload["items"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
            raise ValueError("every Fabric item requires an explicit id")
        item_id = item["id"]
        kind = item.get("type", "unknown")
        if kind == "notebook" and isinstance(item.get("path"), str):
            nodes.append(
                Node.create(
                    operator=OperatorRef("notebook.run"),
                    instance_key=item_id,
                    params={"target": item["path"], "parameters": item.get("parameters", {})},
                )
            )
            reports.append(
                MigrationObjectReport(
                    "notebook",
                    item_id,
                    "translated",
                    (f"workflow-node:{item_id}",),
                    ("Fabric notebook item translated to Ronin notebook.run",),
                )
            )
        else:
            reports.append(
                MigrationObjectReport(
                    str(kind),
                    item_id,
                    "unsupported",
                    (),
                    ("Only Fabric notebook items with a path are executable in this subset",),
                )
            )
    if not nodes:
        raise ValueError("Fabric export contains no executable notebook items")
    workflow = WorkflowDefinition(
        WorkflowId(f"fabric-project-{project_id}"),
        str(payload.get("name", project_id)),
        Pipeline(tuple(nodes)),
    )
    return FabricTranslation(
        workflow,
        MigrationReport("microsoft-fabric", source_version, "ronin-fabric-0.1", tuple(reports)),
    )


__all__ = ("FabricTranslation", "translate_notebook_items")
