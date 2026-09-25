"""Execution orchestration boundary, replaceable by Ronin's worker broker."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Literal, Protocol

from .domain import Lab
from .runner import ClusteringResult, ExperimentResult, LocalExperimentRunner

RunState = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    run_id: str
    state: RunState
    result: ExperimentResult | ClusteringResult | None = None
    error: str | None = None
    result_payload: dict[str, object] | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"run_id": self.run_id, "state": self.state}
        if self.result is not None:
            payload["result"] = self.result.to_payload()
        elif self.result_payload is not None:
            payload["result"] = self.result_payload
        if self.error is not None:
            payload["error"] = self.error
        return payload


class ExecutionStore(Protocol):
    def put(self, snapshot: ExecutionSnapshot) -> None: ...
    def get(self, run_id: str) -> ExecutionSnapshot | None: ...


class InMemoryExecutionStore:
    def __init__(self) -> None:
        self._items: dict[str, ExecutionSnapshot] = {}

    def put(self, snapshot: ExecutionSnapshot) -> None:
        self._items[snapshot.run_id] = snapshot

    def get(self, run_id: str) -> ExecutionSnapshot | None:
        return self._items.get(run_id)


class LocalExecutionCoordinator:
    """Bounded local coordinator with the same lifecycle a remote adapter must expose."""

    def __init__(
        self,
        runner: LocalExperimentRunner | None = None,
        max_workers: int = 2,
        store: ExecutionStore | None = None,
    ) -> None:
        if max_workers < 1 or max_workers > 32:
            raise ValueError("max_workers must be between 1 and 32")
        self._runner = runner or LocalExperimentRunner()
        self._store = store or InMemoryExecutionStore()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ronin-ml")
        self._lock = Lock()
        self._snapshots: dict[str, ExecutionSnapshot] = {}
        self._futures: dict[str, Future[object]] = {}

    def submit(self, run_id: str, lab: Lab, rows: list[dict[str, object]]) -> ExecutionSnapshot:
        with self._lock:
            if run_id in self._snapshots:
                return self._snapshots[run_id]
            persisted = self._store.get(run_id)
            if persisted is not None and persisted.state in {"succeeded", "failed", "cancelled"}:
                self._snapshots[run_id] = persisted
                return persisted
            self._snapshots[run_id] = ExecutionSnapshot(run_id, "queued")
            self._store.put(self._snapshots[run_id])
            future = self._executor.submit(self._execute, run_id, lab, rows)
            self._futures[run_id] = future
            return self._snapshots[run_id]

    def _execute(self, run_id: str, lab: Lab, rows: list[dict[str, object]]) -> object:
        with self._lock:
            if self._snapshots[run_id].state == "cancelled":
                raise RuntimeError("execution cancelled before start")
            self._snapshots[run_id] = ExecutionSnapshot(run_id, "running")
            self._store.put(self._snapshots[run_id])
        try:
            result: ExperimentResult | ClusteringResult
            if lab.task == "clustering":
                result = self._runner.run_clustering_result(lab, rows)
            else:
                result = self._runner.run(lab, rows)
        except Exception as exc:
            with self._lock:
                self._snapshots[run_id] = ExecutionSnapshot(run_id, "failed", error=str(exc))
                self._store.put(self._snapshots[run_id])
            raise
        with self._lock:
            if self._snapshots[run_id].state == "cancelled":
                return result
            self._snapshots[run_id] = ExecutionSnapshot(
                run_id, "succeeded", result=result, result_payload=result.to_payload()
            )
            self._store.put(self._snapshots[run_id])
        return result

    def status(self, run_id: str) -> ExecutionSnapshot:
        with self._lock:
            snapshot = self._snapshots.get(run_id)
            if snapshot is None:
                snapshot = self._store.get(run_id)
                if snapshot is None:
                    raise KeyError(run_id)
                self._snapshots[run_id] = snapshot
            return snapshot

    def cancel(self, run_id: str) -> ExecutionSnapshot:
        with self._lock:
            snapshot = self.status(run_id)
            if snapshot.state in {"queued", "running"}:
                future = self._futures[run_id]
                future.cancel()
                self._snapshots[run_id] = ExecutionSnapshot(run_id, "cancelled")
                self._store.put(self._snapshots[run_id])
            return self._snapshots[run_id]

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)


__all__ = [
    "ExecutionSnapshot",
    "ExecutionStore",
    "InMemoryExecutionStore",
    "LocalExecutionCoordinator",
    "RunState",
]
