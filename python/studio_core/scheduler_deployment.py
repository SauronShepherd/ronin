"""Deployment-local workflow bindings kept outside canonical WorkflowDefinition identity."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json
from .environments import EnvironmentId
from .projects import ProjectId
from .scheduler import WorkflowId


@dataclass(frozen=True, order=True, slots=True)
class WorkflowDeploymentBinding:
    """Bind one portable workflow to a project and optional deployment environment.

    This value is intentionally stored outside ``WorkflowDefinition`` so moving
    the same workflow between environments does not change its canonical source
    identity or invalidate historical WorkflowRun snapshots.
    """

    workflow_id: WorkflowId
    project_id: ProjectId
    environment_id: EnvironmentId | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "workflow_id": str(self.workflow_id),
            "project_id": str(self.project_id),
            "environment_id": (
                None if self.environment_id is None else str(self.environment_id)
            ),
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> WorkflowDeploymentBinding:
        if not isinstance(payload, Mapping) or set(payload) != {
            "workflow_id",
            "project_id",
            "environment_id",
        }:
            raise ValueError("workflow deployment binding has invalid shape")
        workflow_id = payload["workflow_id"]
        project_id = payload["project_id"]
        environment_id = payload["environment_id"]
        if not isinstance(workflow_id, str) or not isinstance(project_id, str):
            raise ValueError("workflow/project ids must be strings")
        if environment_id is not None and not isinstance(environment_id, str):
            raise ValueError("environment id must be a string or null")
        return cls(
            WorkflowId(workflow_id),
            ProjectId(project_id),
            None if environment_id is None else EnvironmentId(environment_id),
        )

    @classmethod
    def from_json(cls, payload: str) -> WorkflowDeploymentBinding:
        return cls.from_payload(decode_canonical_json(payload))


__all__ = ("WorkflowDeploymentBinding",)
