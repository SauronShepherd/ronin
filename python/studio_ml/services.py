"""Application services and reference in-memory adapter for ML Studio."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field

from studio_core import WorkspaceId

from .domain import Lab, PipelineIR
from .ports import MLLabStore


class MLLabConflict(RuntimeError):
    """Raised when an immutable lab identity is reused with different content."""


@dataclass
class InMemoryMLLabStore:
    _labs: dict[tuple[str, str], Lab] = field(default_factory=dict)
    _pipelines: dict[tuple[str, str], PipelineIR] = field(default_factory=dict)

    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        key = (str(workspace_id), lab.id)
        current = self._labs.get(key)
        if current is not None and current != lab:
            raise MLLabConflict(f"lab id already exists: {lab.id}")
        self._labs[key] = lab
        return lab

    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None:
        return self._labs.get((str(workspace_id), lab_id))

    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
        prefix = str(workspace_id)
        return tuple(
            sorted(
                (lab for (workspace, _), lab in self._labs.items() if workspace == prefix),
                key=lambda item: item.id,
            )
        )

    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR:
        self._pipelines[(str(workspace_id), lab_id)] = pipeline
        return pipeline

    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None:
        return self._pipelines.get((str(workspace_id), lab_id))


@dataclass(frozen=True, slots=True)
class LabService:
    store: MLLabStore

    def create(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        if self.store.get_lab(workspace_id, lab.id) is not None:
            raise MLLabConflict(f"lab id already exists: {lab.id}")
        return self.store.put_lab(workspace_id, lab)

    def get(self, workspace_id: WorkspaceId, lab_id: str) -> Lab:
        lab = self.store.get_lab(workspace_id, lab_id)
        if lab is None:
            raise KeyError(lab_id)
        return lab

    def list(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
        return self.store.list_labs(workspace_id)

    def compile(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR:
        lab = self.get(workspace_id, lab_id)
        pipeline = PipelineIR(
            nodes=(
                _node("profile"),
                _node("quality_gate", ("profile",)),
                _node("prepare", ("quality_gate",)),
                _node("train", ("prepare",)),
                _node("evaluate", ("train",)),
                _node("select", ("evaluate",)),
            ),
            parameters=(
                ("backend_id", lab.backend_id),
                ("seed", str(lab.seed)),
                ("task", lab.task),
            ),
        )
        return self.store.put_pipeline(workspace_id, lab.id, pipeline)


def _node(kind: str, depends_on: tuple[str, ...] = ()):
    from .domain import PipelineNode

    return PipelineNode(kind, kind, depends_on)


__all__ = ["InMemoryMLLabStore", "LabService", "MLLabConflict"]
