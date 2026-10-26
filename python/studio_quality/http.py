"""Provider-neutral HTTP-facing quality application adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from studio_core import AssetRef, DataContract, QualityRun, QualityRunId, WorkspaceId
from studio_orchestrator import Instant

from .evaluator import DEFAULT_QUALITY_EVALUATION_BUDGET, QualityEvaluationBudget
from .service import (
    QualityExecutionBlocked,
    QualityExecutionStore,
    execute_quality_with_gate,
    list_quality_runs,
    quality_run_payload,
    quality_state_summary,
)


class QualityHTTPAdapter:
    """Translate bounded public quality payloads into the quality service."""

    def __init__(
        self,
        store: QualityExecutionStore,
        *,
        budget: QualityEvaluationBudget = DEFAULT_QUALITY_EVALUATION_BUDGET,
        on_run: Callable[[WorkspaceId, QualityRun, Instant], object] | None = None,
    ) -> None:
        self._store = store
        self._budget = budget
        self._on_run = on_run

    def get_contract(
        self, workspace_id: WorkspaceId, payload: Mapping[str, object]
    ) -> DataContract:
        asset = AssetRef.from_payload(payload)
        contract = self._store.get_contract(workspace_id, asset)
        if contract is None:
            raise KeyError(f"quality contract not found: {asset}")
        return contract

    def put_contract(
        self, workspace_id: WorkspaceId, payload: Mapping[str, object], *, now: Instant | str
    ) -> dict[str, object]:
        contract = DataContract.from_payload(payload)
        writer = getattr(self._store, "put_contract", None)
        if not callable(writer):
            raise RuntimeError("quality contract persistence is not configured")
        return cast(dict[str, object], writer(workspace_id, contract, now=now).to_payload())

    def run(
        self, workspace_id: WorkspaceId, payload: Mapping[str, object], *, now: Instant | str
    ) -> dict[str, object]:
        required = {"asset", "rows", "run_id"}
        optional = {"execution_ref", "enforce_blocking", "contract_digest"}
        if set(payload) - required - optional or not required.issubset(payload):
            raise ValueError("quality run body must contain asset, rows, and run_id")
        rows = payload["rows"]
        if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
            raise ValueError("quality rows must be an array of objects")
        self._budget.validate_rows(rows)
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
        expected_contract_digest = payload.get("contract_digest")
        if expected_contract_digest is not None and (
            not isinstance(expected_contract_digest, str)
            or len(expected_contract_digest) != 64
            or any(char not in "0123456789abcdef" for char in expected_contract_digest)
        ):
            raise ValueError("quality contract_digest must be a lowercase SHA-256 digest")
        asset = AssetRef.from_payload(payload["asset"])
        outcome = execute_quality_with_gate(
            self._store,
            workspace_id,
            asset,
            rows,
            run_id=QualityRunId(run_id),
            expected_contract_digest=expected_contract_digest,
            execution_ref=execution_ref,
            now=now,
            budget=self._budget,
        )
        if self._on_run is not None:
            get_run_created_at = getattr(self._store, "get_run_created_at", None)
            if not callable(get_run_created_at):
                raise TypeError("quality alert integration requires a durable run timestamp reader")
            observed_at = get_run_created_at(workspace_id, outcome.run.id)
            if observed_at is None:
                raise RuntimeError("recorded quality run is missing its durable timestamp")
            self._on_run(workspace_id, outcome.run, observed_at)
        if enforce_blocking and not outcome.gate_passed:
            raise QualityExecutionBlocked(outcome.run)
        return {"run": quality_run_payload(outcome.run), "gate_passed": outcome.gate_passed}

    def history(
        self, workspace_id: WorkspaceId, payload: Mapping[str, object]
    ) -> tuple[dict[str, object], ...]:
        asset = AssetRef.from_payload(payload)
        return tuple(
            quality_run_payload(run) for run in list_quality_runs(self._store, workspace_id, asset)
        )

    def state(self, workspace_id: WorkspaceId, payload: Mapping[str, object]) -> dict[str, object]:
        asset = AssetRef.from_payload(payload)
        return quality_state_summary(list_quality_runs(self._store, workspace_id, asset))


__all__ = ("QualityHTTPAdapter",)
