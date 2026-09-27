"""Provider-neutral HTTP-facing quality application adapter."""

from __future__ import annotations

from collections.abc import Mapping

from studio_core import AssetRef, DataContract, QualityRunId, WorkspaceId
from studio_orchestrator import Instant

from .service import (
    QualityExecutionStore,
    execute_quality,
    list_quality_runs,
    quality_state_summary,
)


class QualityHTTPAdapter:
    """Translate bounded public quality payloads into the quality service."""

    def __init__(self, store: QualityExecutionStore) -> None:
        self._store = store

    def get_contract(
        self, workspace_id: WorkspaceId, payload: Mapping[str, object]
    ) -> DataContract:
        asset = AssetRef.from_payload(payload)
        contract = self._store.get_contract(workspace_id, asset)
        if contract is None:
            raise KeyError(f"quality contract not found: {asset}")
        return contract

    def run(
        self, workspace_id: WorkspaceId, payload: Mapping[str, object], *, now: Instant | str
    ) -> dict[str, object]:
        required = {"asset", "rows", "run_id"}
        if set(payload) - required - {"execution_ref", "enforce_blocking"} or not required.issubset(
            payload
        ):
            raise ValueError("quality run body must contain asset, rows, and run_id")
        rows = payload["rows"]
        if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
            raise ValueError("quality rows must be an array of objects")
        run_id = payload["run_id"]
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("quality run_id must be a non-empty string")
        enforce_blocking = payload.get("enforce_blocking", False)
        if not isinstance(enforce_blocking, bool):
            raise ValueError("quality enforce_blocking must be boolean")
        execution_ref = payload.get("execution_ref")
        if execution_ref is not None and (
            not isinstance(execution_ref, str) or not execution_ref.strip()
        ):
            raise ValueError("quality execution_ref must be a non-empty string or null")
        asset = AssetRef.from_payload(payload["asset"])
        run = execute_quality(
            self._store,
            workspace_id,
            asset,
            rows,
            run_id=QualityRunId(run_id),
            execution_ref=execution_ref,
            now=now,
            enforce_blocking=enforce_blocking,
        )
        return {"run": run.to_payload(), "gate_passed": run.status == "passed"}

    def history(
        self, workspace_id: WorkspaceId, payload: Mapping[str, object]
    ) -> tuple[dict[str, object], ...]:
        asset = AssetRef.from_payload(payload)
        return tuple(
            run.to_payload() for run in list_quality_runs(self._store, workspace_id, asset)
        )

    def state(self, workspace_id: WorkspaceId, payload: Mapping[str, object]) -> dict[str, object]:
        asset = AssetRef.from_payload(payload)
        return quality_state_summary(list_quality_runs(self._store, workspace_id, asset))


__all__ = ("QualityHTTPAdapter",)
