"""Open-source local workspace plugin."""

from .plugin import WorkspacesPlugin, factory
from .ports import ProjectPort, WorkspacePort
from .services import WorkspaceApplication

__all__ = (
    "ProjectPort",
    "WorkspaceApplication",
    "WorkspacePort",
    "WorkspacesPlugin",
    "factory",
)
