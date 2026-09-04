"""Runtime adapter boundaries for provider-neutral execution discovery and execution."""

from .container import (
    AsyncioCommandRunner,
    CancellableCommandRunner,
    CommandOutcome,
    ContainerExecutionLimits,
    ContainerExecutorConfig,
    DockerContainerKernelExecutor,
    ExecutionEvidenceStore,
    LocalExecutionEvidenceStore,
)
from .discovery import (
    RuntimeDiscoveryAdapter,
    RuntimeDiscoveryIssue,
    RuntimeDiscoveryReport,
    RuntimeDiscoveryResult,
    discover_runtime_profiles,
)

__all__ = (
    "AsyncioCommandRunner",
    "CancellableCommandRunner",
    "CommandOutcome",
    "ContainerExecutionLimits",
    "ContainerExecutorConfig",
    "DockerContainerKernelExecutor",
    "ExecutionEvidenceStore",
    "LocalExecutionEvidenceStore",
    "RuntimeDiscoveryAdapter",
    "RuntimeDiscoveryIssue",
    "RuntimeDiscoveryReport",
    "RuntimeDiscoveryResult",
    "discover_runtime_profiles",
)
