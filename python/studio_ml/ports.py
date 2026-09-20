"""Persistence ports for Machine Learning Studio application services."""
# ruff: noqa: E501

from __future__ import annotations

from typing import Protocol, runtime_checkable

from studio_core import WorkspaceId

from .domain import Lab, PipelineIR


@runtime_checkable
class MLLabStore(Protocol):
    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab: ...
    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None: ...
    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]: ...
    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR: ...
    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None: ...


__all__ = ["MLLabStore"]
