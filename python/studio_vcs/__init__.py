"""Read-only local Git revision capture at the adapter boundary."""

from __future__ import annotations

from studio_vcs.git import GitCaptureError, GitRevision, capture_revision

__all__ = ("GitCaptureError", "GitRevision", "capture_revision")
