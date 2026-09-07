"""Runtime adapter boundaries for provider-neutral execution discovery and execution."""

from .container import (
    AsyncioCommandRunner,
    CancellableCommandRunner,
    CommandOutcome,
    ContainerExecutionLimits,
    ContainerExecutorConfig,
    DockerContainerKernelExecutor,
    ExecutionEvidenceStore,
)
from .discovery import (
    RuntimeDiscoveryAdapter,
    RuntimeDiscoveryIssue,
    RuntimeDiscoveryReport,
    RuntimeDiscoveryResult,
    discover_runtime_profiles,
)
from .evidence import PortableLocalExecutionEvidenceStore

LocalExecutionEvidenceStore = PortableLocalExecutionEvidenceStore

__all__ = (
    "AsyncioCommandRunner",
    "CancellableCommandRunner",
    "CommandOutcome",
    "ContainerExecutionLimits",
    "ContainerExecutorConfig",
    "DockerContainerKernelExecutor",
    "ExecutionEvidenceStore",
    "LocalExecutionEvidenceStore",
    "PortableLocalExecutionEvidenceStore",
    "RuntimeDiscoveryAdapter",
    "RuntimeDiscoveryIssue",
    "RuntimeDiscoveryReport",
    "RuntimeDiscoveryResult",
    "discover_runtime_profiles",
)
