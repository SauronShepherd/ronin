"""Application services and reference in-memory adapter for ML Studio."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field

from studio_core import WorkspaceId

from .domain import FeatureDefinition, Lab, NodeKind, PipelineIR, PipelineNode
from .ports import FeatureDefinitionStore, MLLabStore


class MLLabConflict(RuntimeError):
    """Raised when an immutable lab identity is reused with different content."""


class FeatureDefinitionConflict(RuntimeError):
    """Raised when a feature identity/version is reused with different content."""


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


@dataclass(frozen=True, slots=True)
class FeatureDefinitionService:
    store: FeatureDefinitionStore

    def publish(
        self, workspace_id: WorkspaceId, definition: FeatureDefinition
    ) -> FeatureDefinition:
        current = self.store.get_feature_definition(workspace_id, definition.id, definition.version)
        if current is not None:
            if current != definition:
                raise FeatureDefinitionConflict(
                    f"feature definition version already exists: {definition.id}/{definition.version}"
                )
            return current
        latest = self.store.get_feature_definition(workspace_id, definition.id)
        if latest is not None and definition.version <= latest.version:
            raise FeatureDefinitionConflict(
                f"feature definition version must advance: {definition.id}/{latest.version}"
            )
        return self.store.put_feature_definition(workspace_id, definition)

    def publish_payload(self, workspace_id: WorkspaceId, payload: object) -> FeatureDefinition:
        return self.publish(workspace_id, FeatureDefinition.from_payload(payload))

    def get(
        self, workspace_id: WorkspaceId, feature_id: str, version: int | None = None
    ) -> FeatureDefinition:
        result = self.store.get_feature_definition(workspace_id, feature_id, version)
        if result is None:
            raise KeyError(feature_id)
        return result

    def list(
        self, workspace_id: WorkspaceId, feature_id: str | None = None
    ) -> tuple[FeatureDefinition, ...]:
        return self.store.list_feature_definitions(workspace_id, feature_id)


def _node(kind: str, depends_on: tuple[str, ...] = ()) -> PipelineNode:
    from typing import cast

    return PipelineNode(kind, cast(NodeKind, kind), depends_on)


__all__ = [
    "FeatureDefinitionConflict",
    "FeatureDefinitionService",
    "InMemoryMLLabStore",
    "LabService",
    "MLLabConflict",
]
