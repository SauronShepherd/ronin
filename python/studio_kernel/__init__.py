"""Kernel request preparation and immutable execution-evidence contracts."""

from .contracts import (
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionEvidenceReference,
    KernelDirective,
    KernelDirectiveField,
    KernelRequestAdapter,
    NotebookExecutionEvidence,
    NotebookExecutionRequest,
    PreparedCell,
    RepositoryRevision,
    prepare_notebook_execution,
)
from .reproducibility import (
    EffectiveRuntimeSetting,
    ExecutionAttemptId,
    ExecutionEventId,
    ExecutionReproducibilitySnapshot,
    ReproducibilityDigest,
)

__all__ = (
    "CellExecutionRequest",
    "CellExecutionResult",
    "EffectiveRuntimeSetting",
    "ExecutionAttemptId",
    "ExecutionEventId",
    "ExecutionEvidenceReference",
    "ExecutionReproducibilitySnapshot",
    "KernelDirective",
    "KernelDirectiveField",
    "KernelRequestAdapter",
    "NotebookExecutionEvidence",
    "NotebookExecutionRequest",
    "PreparedCell",
    "RepositoryRevision",
    "ReproducibilityDigest",
    "prepare_notebook_execution",
)
