"""Persistence ports for Machine Learning Studio application services."""
# ruff: noqa: E501

from __future__ import annotations

from typing import Protocol, runtime_checkable

from studio_core import WorkspaceId

from .domain import FeatureDefinition, Lab, PipelineIR
from .drift import DriftPolicy
from .quality import QualitySuite


@runtime_checkable
class MLLabStore(Protocol):
    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab: ...
    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None: ...
    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]: ...
    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR: ...
    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None: ...
    def put_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite: QualitySuite
    ) -> QualitySuite: ...
    def get_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite_id: str, version: int | None = None
    ) -> QualitySuite | None: ...
    def list_quality_suites(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[QualitySuite, ...]: ...
    def put_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy: DriftPolicy
    ) -> DriftPolicy: ...
    def get_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy_id: str, version: int | None = None
    ) -> DriftPolicy | None: ...
    def list_drift_policies(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[DriftPolicy, ...]: ...


@runtime_checkable
class FeatureDefinitionStore(Protocol):
    def put_feature_definition(
        self, workspace_id: WorkspaceId, definition: FeatureDefinition
    ) -> FeatureDefinition: ...
    def get_feature_definition(
        self, workspace_id: WorkspaceId, feature_id: str, version: int | None = None
    ) -> FeatureDefinition | None: ...
    def list_feature_definitions(
        self, workspace_id: WorkspaceId, feature_id: str | None = None
    ) -> tuple[FeatureDefinition, ...]: ...


__all__ = ["FeatureDefinitionStore", "MLLabStore"]
