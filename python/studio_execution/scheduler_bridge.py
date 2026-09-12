"""Deterministic scheduler-task execution planning over the existing Job/Run lifecycle.

This module intentionally plans but does not dispatch work. Dispatch/reconciliation
must preserve the scheduler lease across the linked Job lifecycle before Public v1
can claim an end-to-end scheduler execution bridge.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from studio_core import Node, ProjectId, WorkflowRun, operator_parameter_value
from studio_core.canonical_json import encode as encode_canonical_json
from studio_orchestrator import Instant, Job, JobId, JobState, Run, RunId, RunState
from studio_storage.scheduler_fencing import ClaimedTask


class UnsupportedTaskExecution(ValueError):
    """Raised when no durable execution adapter exists for a workflow node."""


@dataclass(frozen=True, slots=True)
class SchedulerExecutionPlan:
    """One deterministic Job/Run candidate for an already-claimed scheduler task."""

    claim: ClaimedTask
    project_id: ProjectId
    job: Job
    run: Run


def _node_for_claim(claim: ClaimedTask, workflow_run: WorkflowRun) -> Node:
    if workflow_run.id != claim.workflow_run_id:
        raise ValueError("claimed task does not belong to the supplied workflow run")
    matches = tuple(
        node
        for node in workflow_run.workflow_snapshot.pipeline.nodes
        if node.id == claim.node_id
    )
    if len(matches) != 1:
        raise ValueError("claimed task node must exist exactly once in the workflow snapshot")
    return matches[0]


def _notebook_payload(node: Node) -> tuple[str, dict[str, object]]:
    if node.operator.name != "notebook.run" or node.operator.version != 1:
        raise UnsupportedTaskExecution(
            f"no durable execution adapter for {node.operator.name}@{node.operator.version}"
        )
    target = operator_parameter_value(node, "target")
    parameters = operator_parameter_value(node, "parameters")
    if not isinstance(target, str) or not target or target != target.strip():
        raise ValueError("notebook.run target must be a non-empty trimmed string")
    if parameters is None:
        parameter_map: dict[str, object] = {}
    elif isinstance(parameters, dict) and all(isinstance(key, str) for key in parameters):
        parameter_map = parameters
    else:
        raise ValueError("notebook.run parameters must be a JSON object")
    return target, parameter_map


def _digest(payload: object) -> str:
    return hashlib.sha256(encode_canonical_json(payload)).hexdigest()


def plan_scheduler_execution(
    claim: ClaimedTask,
    workflow_run: WorkflowRun,
    project_id: ProjectId,
    *,
    now: Instant | str,
) -> SchedulerExecutionPlan:
    """Translate one supported task attempt into deterministic Job/Run identity.

    Scheduler retry attempts intentionally receive separate Jobs. The existing
    Job lifecycle remains responsible only for crash-replacement Attempts inside
    that one scheduler attempt, avoiding two independent ordinary-retry loops.
    """

    current = Instant(now)
    node = _node_for_claim(claim, workflow_run)
    target, parameters = _notebook_payload(node)
    identity = {
        "workspace_id": str(claim.workspace_id),
        "workflow_run_id": str(claim.workflow_run_id),
        "task_run_id": str(claim.task_run_id),
        "task_attempt_id": str(claim.attempt_id),
        "attempt_ordinal": claim.attempt_ordinal,
        "node_id": claim.node_id.value,
        "project_id": str(project_id),
    }
    identity_digest = _digest(identity)
    request_digest = _digest(
        {
            "identity": identity,
            "operator": {"name": node.operator.name, "version": node.operator.version},
            "target": target,
            "parameters": parameters,
        }
    )
    job_id = JobId(f"job-scheduler-{identity_digest[:32]}")
    run_id = RunId(f"run-scheduler-{identity_digest[:32]}")
    job = Job(
        id=job_id,
        project_id=str(project_id),
        idempotency_key=f"scheduler:{claim.attempt_id}",
        request_digest=request_digest,
        state=JobState.QUEUED,
        created_at=current,
        updated_at=current,
        target=target,
        parameters_json=encode_canonical_json(parameters).decode("utf-8"),
    )
    run = Run(
        id=run_id,
        job_id=job_id,
        ordinal=1,
        state=RunState.PENDING,
        not_before=current,
        created_at=current,
        updated_at=current,
    )
    return SchedulerExecutionPlan(claim, project_id, job, run)


__all__ = (
    "SchedulerExecutionPlan",
    "UnsupportedTaskExecution",
    "plan_scheduler_execution",
)
