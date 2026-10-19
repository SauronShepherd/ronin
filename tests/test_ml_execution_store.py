"""The ML adapter maps requests onto the host's canonical JobStore lifecycle."""

from __future__ import annotations

import asyncio

import pytest
from studio_execution import DurableExecutionService
from studio_ml import ExecutionConflict, ExecutionSnapshot, JobStoreExecutionStore
from studio_orchestrator import JobState
from studio_storage import InMemoryJobStore


def _snapshot(workspace_id: str, digest: str = "a" * 64) -> ExecutionSnapshot:
    return ExecutionSnapshot(
        run_id="shared-run",
        state="queued",
        workspace_id=workspace_id,
        lab_id="lab-1",
        lab_digest="b" * 64,
        request_digest=digest,
        lab_json="{}",
        rows_json="[]",
    )


def test_job_store_adapter_scopes_and_idempotently_replays_requests() -> None:
    service = DurableExecutionService(InMemoryJobStore())
    adapter = JobStoreExecutionStore(service)
    try:
        first = adapter.create(_snapshot("workspace-a"))
        replay = adapter.create(_snapshot("workspace-a"))
        other_workspace = adapter.create(_snapshot("workspace-b", "c" * 64))

        assert first.state == "queued"
        assert replay.state == "queued"
        assert other_workspace.workspace_id == "workspace-b"
        assert (
            JobStoreExecutionStore._ids("workspace-a", "shared-run")[0]
            != (JobStoreExecutionStore._ids("workspace-b", "shared-run")[0])
        )
        with pytest.raises(ExecutionConflict, match="already exists"):
            adapter.create(_snapshot("workspace-a", "d" * 64))

        page = asyncio.run(
            service.list_jobs(
                project_id=None,
                project_ids=None,
                state=JobState.QUEUED,
                limit=10,
                cursor=None,
            )
        )
        assert len(page.items) == 2
    finally:
        asyncio.run(service.aclose())
