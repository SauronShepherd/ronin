"""Application service connecting persisted DataContracts to executable quality runs."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from studio_core import AssetRef, DataContract, QualityRule, QualityRun, QualityRunId, WorkspaceId
from studio_orchestrator import Instant

from .evaluator import blocking_failures, evaluate_contract


class QualityContractNotFound(KeyError):
    """Raised when quality execution is requested without a persisted contract."""


@runtime_checkable
class QualityExecutionStore(Protocol):
    def get_contract(self, workspace_id: WorkspaceId, ref: AssetRef) -> DataContract | None: ...

    def record_run(
        self,
        workspace_id: WorkspaceId,
        run: QualityRun,
        *,
        now: Instant | str,
    ) -> QualityRun: ...

    def list_runs(
        self, workspace_id: WorkspaceId, ref: AssetRef
    ) -> tuple[QualityRun, ...]: ...


class QualityExecutionBlocked(RuntimeError):
    """Raised when requested gating fails because a blocking rule did not pass."""

    def __init__(self, run: QualityRun) -> None:
        super().__init__(f"quality run {run.id} contains blocking failures")
        self.run = run


def quality_gate(contract: DataContract, run: QualityRun) -> bool:
    """Return whether a recorded quality run may release dependent work."""
    if run.asset != contract.asset:
        raise ValueError("quality run asset does not match contract asset")
    if run.status == "error":
        return False
    return not blocking_failures(contract, run)


def list_quality_runs(
    store: QualityExecutionStore, workspace_id: WorkspaceId, asset: AssetRef
) -> tuple[QualityRun, ...]:
    """Return durable quality evidence for one governed asset revision."""

    return store.list_runs(workspace_id, asset)


def execute_quality(
    store: QualityExecutionStore,
    workspace_id: WorkspaceId,
    asset: AssetRef,
    rows: Sequence[Mapping[str, object]],
    *,
    run_id: QualityRunId,
    execution_ref: str | None = None,
    now: Instant | str,
    evaluation_time: datetime | None = None,
    reference_values: Callable[[QualityRule], Sequence[object]] | None = None,
    custom_sql: Callable[[QualityRule, Sequence[Mapping[str, object]]], bool] | None = None,
    custom_python: Callable[[QualityRule, Sequence[Mapping[str, object]]], bool] | None = None,
    enforce_blocking: bool = False,
) -> QualityRun:
    """Evaluate persisted contract, record immutable evidence, then optionally gate."""

    contract = store.get_contract(workspace_id, asset)
    if contract is None:
        raise QualityContractNotFound(f"{asset.asset_id}@{asset.version}")
    run = evaluate_contract(
        contract,
        rows,
        run_id=run_id,
        execution_ref=execution_ref,
        now=evaluation_time,
        reference_values=reference_values,
        custom_sql=custom_sql,
        custom_python=custom_python,
    )
    recorded = store.record_run(workspace_id, run, now=now)
    if enforce_blocking and not quality_gate(contract, recorded):
        raise QualityExecutionBlocked(recorded)
    return recorded


__all__ = (
    "QualityContractNotFound",
    "QualityExecutionBlocked",
    "QualityExecutionStore",
    "execute_quality",
    "quality_gate",
    "list_quality_runs",
)
