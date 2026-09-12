"""Provider-neutral workflow and scheduler contracts for Ronin Public v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.ir import NodeId, Pipeline

TriggerKind: TypeAlias = Literal["manual", "api", "schedule", "event", "backfill"]
WorkflowRunState: TypeAlias = Literal[
    "pending", "running", "succeeded", "failed", "cancelling", "cancelled"
]
TaskRunState: TypeAlias = Literal[
    "pending", "running", "retry_wait", "succeeded", "failed", "cancelled", "blocked"
]


def _require_text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


@dataclass(frozen=True, order=True, slots=True)
class WorkflowId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "workflow id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class ScheduleId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "schedule id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class WorkflowRunId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "workflow run id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True, slots=True)
class TaskRunId:
    value: str

    def __post_init__(self) -> None:
        _require_text(self.value, "task run id")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    delay_seconds: int = 0
    exponential_backoff: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")

    def to_payload(self) -> dict[str, object]:
        return {
            "max_attempts": self.max_attempts,
            "delay_seconds": self.delay_seconds,
            "exponential_backoff": self.exponential_backoff,
        }

    @classmethod
    def from_payload(cls, payload: object) -> RetryPolicy:
        if not isinstance(payload, Mapping) or set(payload) != {
            "max_attempts",
            "delay_seconds",
            "exponential_backoff",
        }:
            raise ValueError("retry policy has invalid shape")
        max_attempts = payload["max_attempts"]
        delay_seconds = payload["delay_seconds"]
        exponential_backoff = payload["exponential_backoff"]
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or not isinstance(delay_seconds, int)
            or isinstance(delay_seconds, bool)
            or not isinstance(exponential_backoff, bool)
        ):
            raise ValueError("retry policy has invalid field types")
        return cls(max_attempts, delay_seconds, exponential_backoff)


@dataclass(frozen=True, order=True, slots=True)
class TaskPolicy:
    node_id: NodeId
    retry: RetryPolicy = RetryPolicy()
    timeout_seconds: int | None = None
    pool: str | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds is not None and self.timeout_seconds < 1:
            raise ValueError("task timeout_seconds must be positive")
        if self.pool is not None:
            _require_text(self.pool, "task pool")

    def to_payload(self) -> dict[str, object]:
        return {
            "node_id": self.node_id.value,
            "retry": self.retry.to_payload(),
            "timeout_seconds": self.timeout_seconds,
            "pool": self.pool,
        }

    @classmethod
    def from_payload(cls, payload: object) -> TaskPolicy:
        if not isinstance(payload, Mapping) or set(payload) != {
            "node_id",
            "retry",
            "timeout_seconds",
            "pool",
        }:
            raise ValueError("task policy has invalid shape")
        node_id = payload["node_id"]
        timeout = payload["timeout_seconds"]
        pool = payload["pool"]
        if not isinstance(node_id, str):
            raise ValueError("task policy node_id must be string")
        if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool)):
            raise ValueError("task policy timeout_seconds must be integer or null")
        if pool is not None and not isinstance(pool, str):
            raise ValueError("task policy pool must be string or null")
        return cls(
            NodeId(node_id),
            RetryPolicy.from_payload(payload["retry"]),
            cast(int | None, timeout),
            cast(str | None, pool),
        )


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    id: WorkflowId
    name: str
    pipeline: Pipeline
    task_policies: tuple[TaskPolicy, ...] = ()
    max_concurrency: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.name, "workflow name")
        if self.max_concurrency is not None and self.max_concurrency < 1:
            raise ValueError("workflow max_concurrency must be positive")
        node_ids = {node.id for node in self.pipeline.nodes}
        policies = tuple(sorted(self.task_policies, key=lambda policy: policy.node_id.value))
        policy_ids = [policy.node_id for policy in policies]
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("workflow task policies must be unique by node")
        unknown = set(policy_ids) - node_ids
        if unknown:
            raise ValueError("workflow task policy references unknown pipeline node")
        object.__setattr__(self, "task_policies", policies)

    def policy_for(self, node_id: NodeId) -> TaskPolicy:
        for policy in self.task_policies:
            if policy.node_id == node_id:
                return policy
        return TaskPolicy(node_id)

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "name": self.name,
            "pipeline": self.pipeline.to_data(),
            "task_policies": [policy.to_payload() for policy in self.task_policies],
            "max_concurrency": self.max_concurrency,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> WorkflowDefinition:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "name",
            "pipeline",
            "task_policies",
            "max_concurrency",
        }:
            raise ValueError("workflow definition has invalid shape")
        identifier = payload["id"]
        name = payload["name"]
        policies = payload["task_policies"]
        concurrency = payload["max_concurrency"]
        if not isinstance(identifier, str) or not isinstance(name, str):
            raise ValueError("workflow id and name must be strings")
        if not isinstance(payload["pipeline"], Mapping):
            raise ValueError("workflow pipeline must be an object")
        if not isinstance(policies, list):
            raise ValueError("workflow task_policies must be an array")
        if concurrency is not None and (
            not isinstance(concurrency, int) or isinstance(concurrency, bool)
        ):
            raise ValueError("workflow max_concurrency must be integer or null")
        return cls(
            WorkflowId(identifier),
            name,
            Pipeline.from_data(cast(Mapping[str, object], payload["pipeline"])),
            tuple(TaskPolicy.from_payload(item) for item in policies),
            cast(int | None, concurrency),
        )

    @classmethod
    def from_json(cls, payload: str) -> WorkflowDefinition:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class Schedule:
    id: ScheduleId
    workflow_id: WorkflowId
    cron: str
    timezone: str = "UTC"
    enabled: bool = True

    def __post_init__(self) -> None:
        _require_text(self.cron, "schedule cron")
        _require_text(self.timezone, "schedule timezone")

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "workflow_id": self.workflow_id.value,
            "cron": self.cron,
            "timezone": self.timezone,
            "enabled": self.enabled,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> Schedule:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "workflow_id",
            "cron",
            "timezone",
            "enabled",
        }:
            raise ValueError("schedule has invalid shape")
        identifier = payload["id"]
        workflow_id = payload["workflow_id"]
        cron = payload["cron"]
        timezone = payload["timezone"]
        enabled = payload["enabled"]
        if not all(isinstance(value, str) for value in (identifier, workflow_id, cron, timezone)):
            raise ValueError("schedule identity/cron/timezone fields must be strings")
        if not isinstance(enabled, bool):
            raise ValueError("schedule enabled must be boolean")
        return cls(
            ScheduleId(cast(str, identifier)),
            WorkflowId(cast(str, workflow_id)),
            cast(str, cron),
            cast(str, timezone),
            enabled,
        )

    @classmethod
    def from_json(cls, payload: str) -> Schedule:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class Trigger:
    kind: TriggerKind
    key: str
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"manual", "api", "schedule", "event", "backfill"}:
            raise ValueError("unsupported trigger kind")
        _require_text(self.key, "trigger key")
        if self.source_ref is not None:
            _require_text(self.source_ref, "trigger source_ref")

    def to_payload(self) -> dict[str, object]:
        return {"kind": self.kind, "key": self.key, "source_ref": self.source_ref}

    @classmethod
    def from_payload(cls, payload: object) -> Trigger:
        if not isinstance(payload, Mapping) or set(payload) != {"kind", "key", "source_ref"}:
            raise ValueError("trigger has invalid shape")
        kind = payload["kind"]
        key = payload["key"]
        source_ref = payload["source_ref"]
        if not isinstance(kind, str) or kind not in {"manual", "api", "schedule", "event", "backfill"}:
            raise ValueError("unsupported trigger kind")
        if not isinstance(key, str) or (source_ref is not None and not isinstance(source_ref, str)):
            raise ValueError("trigger key/source_ref have invalid types")
        return cls(cast(TriggerKind, kind), key, cast(str | None, source_ref))


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    id: WorkflowRunId
    workflow_id: WorkflowId
    workflow_snapshot: WorkflowDefinition
    trigger: Trigger
    state: WorkflowRunState = "pending"

    def __post_init__(self) -> None:
        if self.workflow_snapshot.id != self.workflow_id:
            raise ValueError("workflow run snapshot id must match workflow_id")
        if self.state not in {"pending", "running", "succeeded", "failed", "cancelling", "cancelled"}:
            raise ValueError("unsupported workflow run state")

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "workflow_id": self.workflow_id.value,
            "workflow_snapshot": self.workflow_snapshot.to_payload(),
            "trigger": self.trigger.to_payload(),
            "state": self.state,
        }

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> WorkflowRun:
        if not isinstance(payload, Mapping) or set(payload) != {
            "id",
            "workflow_id",
            "workflow_snapshot",
            "trigger",
            "state",
        }:
            raise ValueError("workflow run has invalid shape")
        identifier = payload["id"]
        workflow_id = payload["workflow_id"]
        state = payload["state"]
        if not isinstance(identifier, str) or not isinstance(workflow_id, str) or not isinstance(state, str):
            raise ValueError("workflow run identity/state fields must be strings")
        if state not in {"pending", "running", "succeeded", "failed", "cancelling", "cancelled"}:
            raise ValueError("unsupported workflow run state")
        return cls(
            WorkflowRunId(identifier),
            WorkflowId(workflow_id),
            WorkflowDefinition.from_payload(payload["workflow_snapshot"]),
            Trigger.from_payload(payload["trigger"]),
            cast(WorkflowRunState, state),
        )

    @classmethod
    def from_json(cls, payload: str) -> WorkflowRun:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class TaskRun:
    id: TaskRunId
    workflow_run_id: WorkflowRunId
    node_id: NodeId
    state: TaskRunState = "pending"
    attempt_count: int = 0

    def __post_init__(self) -> None:
        if self.state not in {
            "pending",
            "running",
            "retry_wait",
            "succeeded",
            "failed",
            "cancelled",
            "blocked",
        }:
            raise ValueError("unsupported task run state")
        if self.attempt_count < 0:
            raise ValueError("task attempt_count must be non-negative")
