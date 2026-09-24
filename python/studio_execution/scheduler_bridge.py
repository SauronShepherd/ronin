"""Deterministic scheduler-task execution planning over the existing Job/Run lifecycle.

This module intentionally plans but does not dispatch work. Dispatch/reconciliation
must preserve the scheduler lease across the linked Job lifecycle before Public v1
can claim an end-to-end scheduler execution bridge.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from studio_core import WorkflowRun
from studio_orchestrator import Instant, Job, JobId, JobState, Run, RunId, RunState
from studio_storage.scheduler_fencing import ClaimedTask


class UnsupportedTaskExecution(ValueError):
    """Raised when no durable execution adapter exists for a workflow node."""


@dataclass(frozen=True, slots=True)
class SchedulerExecutionPlan:
    """One deterministic Job/Run candidate for an already-claimed scheduler task."""

    claim: ClaimedTask
    project_id: str
    job: Job
    run: Run


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _node_payload_for_claim(
    claim: ClaimedTask,
    workflow_run: WorkflowRun,
) -> Mapping[str, object]:
    if workflow_run.id != claim.workflow_run_id:
        raise ValueError("claimed task does not belong to the supplied workflow run")
    pipeline = workflow_run.workflow_snapshot.pipeline.to_data()
    nodes = pipeline.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("workflow snapshot nodes are invalid")
    matches = tuple(
        cast(Mapping[str, object], node)
        for node in nodes
        if isinstance(node, Mapping) and node.get("id") == claim.node_id.value
    )
    if len(matches) != 1:
        raise ValueError("claimed task node must exist exactly once in the workflow snapshot")
    return matches[0]


def _operator_payload(node: Mapping[str, object]) -> tuple[str, dict[str, object]]:
    operator = node.get("operator")
    params = node.get("params")
    if not isinstance(operator, Mapping) or not isinstance(params, Mapping):
        raise ValueError("workflow node operator/params are invalid")
    name = operator.get("name")
    version = operator.get("version")
    if not isinstance(name, str) or version != 1:
        raise UnsupportedTaskExecution(f"no durable execution adapter for {name}@{version}")
    if name in {"notebook.run", "code.python"}:
        target = params.get("target")
        if name == "code.python":
            target = target or params.get("source")
        parameters = params.get("parameters")
        if name == "code.python":
            parameters = parameters or {"source": params.get("source")}
        if not isinstance(target, str) or not target or target != target.strip():
            raise ValueError(f"{name} target/source must be a non-empty trimmed string")
        if not isinstance(parameters, Mapping) or not all(
            isinstance(key, str) for key in parameters
        ):
            raise ValueError(f"{name} parameters must be a JSON object")
        return target, dict(cast(Mapping[str, object], parameters))
    if name == "sql.query":
        query = params.get("query") or params.get("source")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("sql.query query/source must be a non-empty string")
        parameters = params.get("parameters", {})
        if not isinstance(parameters, Mapping) or not all(
            isinstance(key, str) for key in parameters
        ):
            raise ValueError("sql.query parameters must be a JSON object")
        return "sql.query", {"query": query, "parameters": dict(parameters)}
    if name == "data-engineering.pipeline-run":
        revision_key = params.get("revision_key")
        ir_digest = params.get("ir_digest")
        runtime = params.get("runtime")
        parameters = params.get("parameters", {})
        if not isinstance(revision_key, str) or not revision_key.strip():
            raise ValueError("pipeline-run revision_key must be non-empty")
        if (
            not isinstance(ir_digest, str)
            or len(ir_digest) != 64
            or any(char not in "0123456789abcdef" for char in ir_digest)
        ):
            raise ValueError("pipeline-run ir_digest must be a lowercase SHA-256 digest")
        if not isinstance(runtime, str) or not runtime.strip():
            raise ValueError("pipeline-run runtime must be non-empty")
        if not isinstance(parameters, Mapping) or not all(
            isinstance(key, str) for key in parameters
        ):
            raise ValueError("pipeline-run parameters must be a JSON object")
        return "data-engineering.pipeline-run.v1", {
            "revision_key": revision_key,
            "ir_digest": ir_digest,
            "runtime": runtime,
            "parameters": dict(parameters),
        }
    if name == "quality.gate":
        asset_id = params.get("asset_id")
        version = params.get("version")
        contract_digest = params.get("contract_digest")
        rows_ref = params.get("rows_ref")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("quality.gate asset_id must be non-empty")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("quality.gate version must be non-empty")
        if (
            not isinstance(contract_digest, str)
            or len(contract_digest) != 64
            or any(char not in "0123456789abcdef" for char in contract_digest)
        ):
            raise ValueError("quality.gate contract_digest must be a lowercase SHA-256 digest")
        if not isinstance(rows_ref, str) or not rows_ref.strip():
            raise ValueError("quality.gate rows_ref must be non-empty")
        return "quality.gate.v1", {
            "asset_id": asset_id,
            "version": version,
            "contract_digest": contract_digest,
            "rows_ref": rows_ref,
        }
    if name == "connector.sync":
        connector_id = params.get("connector_id")
        source_ref = params.get("source_ref")
        destination_ref = params.get("destination_ref")
        checkpoint_ref = params.get("checkpoint_ref")
        mode = params.get("mode", "incremental")
        if not isinstance(connector_id, str) or not connector_id.strip():
            raise ValueError("connector.sync connector_id must be non-empty")
        if not isinstance(source_ref, str) or not source_ref.strip():
            raise ValueError("connector.sync source_ref must be non-empty")
        if not isinstance(destination_ref, str) or not destination_ref.strip():
            raise ValueError("connector.sync destination_ref must be non-empty")
        if not isinstance(checkpoint_ref, str) or not checkpoint_ref.strip():
            raise ValueError("connector.sync checkpoint_ref must be non-empty")
        if mode not in {"snapshot", "incremental"}:
            raise ValueError("connector.sync mode must be snapshot or incremental")
        return "connector.sync.v1", {
            "connector_id": connector_id,
            "source_ref": source_ref,
            "destination_ref": destination_ref,
            "checkpoint_ref": checkpoint_ref,
            "mode": mode,
        }
    if name == "graph.query":
        graph_id = params.get("graph_id")
        query = params.get("query")
        limit = params.get("limit", 100)
        if not isinstance(graph_id, str) or not graph_id.strip():
            raise ValueError("graph.query graph_id must be non-empty")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("graph.query query must be non-empty")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10000:
            raise ValueError("graph.query limit must be between 1 and 10000")
        return "graph.query.v1", {"graph_id": graph_id, "query": query, "limit": limit}
    if name == "notification.send":
        notification_id = params.get("notification_id")
        channel = params.get("channel")
        destination_ref = params.get("destination_ref")
        payload_ref = params.get("payload_ref")
        if not isinstance(notification_id, str) or not notification_id.strip():
            raise ValueError("notification.send notification_id must be non-empty")
        if channel not in {"smtp", "webhook"}:
            raise ValueError("notification.send channel must be smtp or webhook")
        if not isinstance(destination_ref, str) or not destination_ref.startswith("secret://"):
            raise ValueError("notification.send destination_ref must be a secret:// reference")
        if not isinstance(payload_ref, str) or not payload_ref.strip():
            raise ValueError("notification.send payload_ref must be non-empty")
        return "notification.send.v1", {
            "notification_id": notification_id,
            "channel": channel,
            "destination_ref": destination_ref,
            "payload_ref": payload_ref,
        }
    if name == "semantic.refresh":
        model_id = params.get("model_id")
        definition_digest = params.get("definition_digest")
        tile_limit = params.get("tile_limit", 100)
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("semantic.refresh model_id must be non-empty")
        if (
            not isinstance(definition_digest, str)
            or len(definition_digest) != 64
            or any(char not in "0123456789abcdef" for char in definition_digest)
        ):
            raise ValueError(
                "semantic.refresh definition_digest must be a lowercase SHA-256 digest"
            )
        if (
            not isinstance(tile_limit, int)
            or isinstance(tile_limit, bool)
            or not 1 <= tile_limit <= 10000
        ):
            raise ValueError("semantic.refresh tile_limit must be between 1 and 10000")
        return "semantic.refresh.v1", {
            "model_id": model_id,
            "definition_digest": definition_digest,
            "tile_limit": tile_limit,
        }
    if name == "ml.run":
        lab_id = params.get("lab_id")
        pipeline_digest = params.get("pipeline_digest")
        dataset_ref = params.get("dataset_ref")
        if not isinstance(lab_id, str) or not lab_id.strip():
            raise ValueError("ml.run lab_id must be non-empty")
        if (
            not isinstance(pipeline_digest, str)
            or len(pipeline_digest) != 64
            or any(char not in "0123456789abcdef" for char in pipeline_digest)
        ):
            raise ValueError("ml.run pipeline_digest must be a lowercase SHA-256 digest")
        if not isinstance(dataset_ref, str) or not dataset_ref.strip():
            raise ValueError("ml.run dataset_ref must be non-empty")
        return "ml.run.v1", {
            "lab_id": lab_id,
            "pipeline_digest": pipeline_digest,
            "dataset_ref": dataset_ref,
        }
    if name == "genai.run":
        provider_id = params.get("provider_id")
        model_id = params.get("model_id")
        prompt_ref = params.get("prompt_ref")
        max_tokens = params.get("max_tokens", 1024)
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("genai.run provider_id must be non-empty")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("genai.run model_id must be non-empty")
        if not isinstance(prompt_ref, str) or not prompt_ref.strip():
            raise ValueError("genai.run prompt_ref must be non-empty")
        if (
            not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or not 1 <= max_tokens <= 100000
        ):
            raise ValueError("genai.run max_tokens must be between 1 and 100000")
        return "genai.run.v1", {
            "provider_id": provider_id,
            "model_id": model_id,
            "prompt_ref": prompt_ref,
            "max_tokens": max_tokens,
        }
    raise UnsupportedTaskExecution(f"no durable execution adapter for {name}@{version}")


def _digest(payload: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _execution_controls(params: Mapping[str, object]) -> dict[str, object]:
    """Validate the common evidence/resource controls carried by every adapter."""

    controls: dict[str, object] = {}
    resource_policy = params.get("resource_policy")
    if resource_policy is not None:
        if not isinstance(resource_policy, Mapping) or not all(
            isinstance(key, str) and key.strip() for key in resource_policy
        ):
            raise ValueError("resource_policy must be a JSON object with string keys")
        controls["resource_policy"] = dict(resource_policy)
    evidence_ref = params.get("evidence_ref")
    if evidence_ref is not None:
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise ValueError("evidence_ref must be a non-empty string")
        controls["evidence_ref"] = evidence_ref
    timeout_seconds = params.get("timeout_seconds")
    if timeout_seconds is not None:
        if (
            not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or not 1 <= timeout_seconds <= 7 * 24 * 60 * 60
        ):
            raise ValueError("timeout_seconds must be an integer between 1 and 604800")
        controls["timeout_seconds"] = timeout_seconds
    return controls


def plan_scheduler_execution(
    claim: ClaimedTask,
    workflow_run: WorkflowRun,
    project_id: str,
    *,
    now: Instant | str,
) -> SchedulerExecutionPlan:
    """Translate one supported task attempt into deterministic Job/Run identity.

    Scheduler retry attempts intentionally receive separate Jobs. The existing
    Job lifecycle remains responsible only for crash-replacement Attempts inside
    that one scheduler attempt, avoiding two independent ordinary-retry loops.
    """

    if (
        not project_id
        or project_id != project_id.strip()
        or "\n" in project_id
        or "\r" in project_id
    ):
        raise ValueError("project_id must be non-empty, trimmed, and single-line")
    current = Instant(now)
    node = _node_payload_for_claim(claim, workflow_run)
    target, parameters = _operator_payload(node)
    controls = _execution_controls(cast(Mapping[str, object], node["params"]))
    if controls:
        parameters = {**parameters, **controls}
    operator = cast(Mapping[str, object], node["operator"])
    identity = {
        "workspace_id": str(claim.workspace_id),
        "workflow_run_id": str(claim.workflow_run_id),
        "task_run_id": str(claim.task_run_id),
        "task_attempt_id": str(claim.attempt_id),
        "attempt_ordinal": claim.attempt_ordinal,
        "node_id": claim.node_id.value,
        "project_id": project_id,
    }
    identity_digest = _digest(identity)
    request_digest = _digest(
        {
            "identity": identity,
            "operator": {"name": operator["name"], "version": operator["version"]},
            "target": target,
            "parameters": parameters,
        }
    )
    job_id = JobId(f"job-scheduler-{identity_digest[:32]}")
    run_id = RunId(f"run-scheduler-{identity_digest[:32]}")
    job = Job(
        id=job_id,
        project_id=project_id,
        idempotency_key=f"scheduler:{claim.attempt_id}",
        request_digest=request_digest,
        state=JobState.QUEUED,
        created_at=current,
        updated_at=current,
        target=target,
        parameters_json=_canonical_json_bytes(parameters).decode("utf-8"),
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
