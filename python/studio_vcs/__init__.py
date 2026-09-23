"""Read-only local Git revision capture at the adapter boundary."""

from __future__ import annotations

from studio_vcs.git import (
    GitCaptureError,
    GitRevision,
    capture_revision,
    checkout_detached,
    create_branch,
    delete_branch,
    fetch_updates,
)
from studio_vcs.source import (
    SourcePolicyError,
    SourceRevisionEvidence,
    capture_source_revision,
    validate_repository_uri,
)

__all__ = (
    "GitCaptureError",
    "GitRevision",
    "capture_revision",
    "checkout_detached",
    "create_branch",
    "delete_branch",
    "fetch_updates",
    "SourcePolicyError",
    "SourceRevisionEvidence",
    "capture_source_revision",
    "validate_repository_uri",
)
