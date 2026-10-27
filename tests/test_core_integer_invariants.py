from __future__ import annotations

import pytest
from studio_core.ir import NodeId, Pipeline
from studio_core.ml import MetricValue
from studio_core.plugin_workers import WorkerLimits, WorkerProtocolError
from studio_core.portability import BundleEntry
from studio_core.scheduler import (
    RetryPolicy,
    TaskPolicy,
    TaskRun,
    TaskRunId,
    WorkflowDefinition,
    WorkflowId,
    WorkflowRunId,
)
from studio_core.scheduler_resources import ResourcePoolDefinition


def test_numeric_domain_fields_reject_booleans_as_integers() -> None:
    with pytest.raises(ValueError, match="metric step must be an integer"):
        MetricValue("accuracy", 0.9, True)
    with pytest.raises(ValueError, match="metric value must be numeric"):
        MetricValue("accuracy", True)
    with pytest.raises(ValueError, match="metric value must be numeric"):
        MetricValue("accuracy", "0.9")
    with pytest.raises(ValueError, match="metric value must be finite"):
        MetricValue("accuracy", 10**10_000)
    with pytest.raises(ValueError, match="size_bytes must be an integer"):
        BundleEntry("data.json", "application/json", "sha256", "a" * 64, True)
    with pytest.raises(ValueError, match="capacity must be an integer"):
        ResourcePoolDefinition("workers", True)
    with pytest.raises(ValueError, match="max_attempts must be an integer"):
        RetryPolicy(max_attempts=True)
    with pytest.raises(ValueError, match="delay_seconds must be an integer"):
        RetryPolicy(delay_seconds=True)
    with pytest.raises(ValueError, match="timeout_seconds must be an integer"):
        TaskPolicy(NodeId("node"), timeout_seconds=True)
    with pytest.raises(ValueError, match="max_concurrency must be an integer"):
        WorkflowDefinition(WorkflowId("workflow"), "Workflow", Pipeline(()), max_concurrency=True)
    with pytest.raises(ValueError, match="attempt_count must be an integer"):
        TaskRun(TaskRunId("task"), WorkflowRunId("run"), NodeId("node"), attempt_count=True)


@pytest.mark.parametrize(
    "limits",
    [
        WorkerLimits(max_payload_bytes=True),
        WorkerLimits(heartbeat_seconds=True),
        WorkerLimits(execution_timeout_seconds=True),
    ],
)
def test_worker_limits_reject_boolean_integer_fields(limits: WorkerLimits) -> None:
    with pytest.raises(WorkerProtocolError, match="limits must be integers"):
        limits.validate()
