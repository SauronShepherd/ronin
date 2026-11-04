"""Canonical workspace/project persistence keys for semantic assets."""

from __future__ import annotations


def semantic_project_scope(workspace_id: str, project_id: str) -> str:
    """Return a collision-free key for a workspace and project identifier pair."""
    for value, label in ((workspace_id, "workspace_id"), (project_id, "project_id")):
        if not value or value != value.strip() or "\x00" in value:
            raise ValueError(f"semantic {label} must be non-empty and trimmed")
    return f"{len(workspace_id)}:{workspace_id}{project_id}"


__all__ = ("semantic_project_scope",)
