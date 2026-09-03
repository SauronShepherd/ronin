"""Runtime adapter boundaries for provider-neutral execution discovery."""

from .discovery import (
    RuntimeDiscoveryAdapter,
    RuntimeDiscoveryIssue,
    RuntimeDiscoveryReport,
    RuntimeDiscoveryResult,
    discover_runtime_profiles,
)

__all__ = (
    "RuntimeDiscoveryAdapter",
    "RuntimeDiscoveryIssue",
    "RuntimeDiscoveryReport",
    "RuntimeDiscoveryResult",
    "discover_runtime_profiles",
)
