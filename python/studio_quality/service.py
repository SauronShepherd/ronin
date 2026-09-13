"""Application service connecting persisted DataContracts to executable quality runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from studio_core import AssetRef, DataContract, QualityRun, QualityRunId, WorkspaceId
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


class QualityExecutionBlocked(RuntimeError):
    """Raised when requested gating fails because a blocking rule did not pass."""

    def __init__(self, run: QualityRun) -> None:
        super().__init__(f"quality run {run.id} contains blocking failures")
        self.run = run


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
    )
    recorded = store.record_run(workspace_id, run, now=now)
    if enforce_blocking and blocking_failures(contract, recorded):
        raise QualityExecutionBlocked(recorded)
    return recorded


__all__ = (
    "QualityContractNotFound",
    "QualityExecutionBlocked",
    "QualityExecutionStore",
    "execute_quality",
)
