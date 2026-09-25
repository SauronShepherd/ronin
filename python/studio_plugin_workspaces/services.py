"""Plugin-owned application facade over stable workspace ports."""

from __future__ import annotations

import base64
import binascii
from urllib.parse import unquote

from studio_core import ProjectId, ProjectManifest, Workspace, WorkspaceId

from .ports import ProjectPort, WorkspacePort


class WorkspaceApplication:
    """Use-case boundary that prevents the plugin API from knowing adapters."""

    def __init__(self, workspace_port: WorkspacePort | None) -> None:
        self._workspace_port = workspace_port

    def list_payloads(self) -> list[dict[str, object]]:
        if self._workspace_port is None:
            return []
        return [
            {
                "id": str(workspace.id),
                "name": workspace.name,
                "description": workspace.description,
                "state": workspace.state,
            }
            for workspace in self._workspace_port.list()
        ]

    def get(self, workspace_id: WorkspaceId) -> Workspace:
        if self._workspace_port is None:
            raise LookupError(f"workspace service is unavailable: {workspace_id}")
        return self._workspace_port.get(workspace_id)

    def create(self, workspace: Workspace, *, now: object) -> Workspace:
        if self._workspace_port is None:
            raise LookupError("workspace service is unavailable")
        return self._workspace_port.create(workspace, now=now)

    def update(
        self, workspace_id: WorkspaceId, *, name: str, description: str | None, now: object
    ) -> Workspace:
        if self._workspace_port is None:
            raise LookupError("workspace service is unavailable")
        return self._workspace_port.update(
            workspace_id, name=name, description=description, now=now
        )

    def archive(self, workspace_id: WorkspaceId, *, now: object) -> Workspace:
        if self._workspace_port is None:
            raise LookupError("workspace service is unavailable")
        return self._workspace_port.archive(workspace_id, now=now)


class ProjectApplication:
    """Project use cases exposed without importing the legacy service."""

    def __init__(self, project_port: ProjectPort | None) -> None:
        self._project_port = project_port

    def list_payloads(
        self,
        workspace_id: WorkspaceId,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, object]], str | None]:
        if self._project_port is None:
            return [], None
        items = [manifest.to_data() for manifest in self._project_port.list(workspace_id)]
        selected = items[offset : offset + limit]
        next_offset = offset + len(selected)
        if next_offset >= len(items):
            return selected, None
        encoded = base64.urlsafe_b64encode(str(next_offset).encode("ascii")).decode("ascii")
        return selected, "pp1." + encoded.rstrip("=")

    def get(self, workspace_id: WorkspaceId, project_id: ProjectId) -> ProjectManifest:
        if self._project_port is None:
            raise LookupError(f"project service is unavailable: {workspace_id}/{project_id}")
        return self._project_port.get(workspace_id, project_id)

    def register(
        self,
        workspace_id: WorkspaceId,
        manifest: ProjectManifest,
        *,
        now: object,
    ) -> ProjectManifest:
        if self._project_port is None:
            raise LookupError("project service is unavailable")
        return self._project_port.register(workspace_id, manifest, now=now)

    def replace(
        self,
        workspace_id: WorkspaceId,
        manifest: ProjectManifest,
        *,
        now: object,
    ) -> ProjectManifest:
        if self._project_port is None:
            raise LookupError("project service is unavailable")
        return self._project_port.replace(workspace_id, manifest, now=now)

    def unregister(self, workspace_id: WorkspaceId, project_id: ProjectId) -> None:
        if self._project_port is None:
            raise LookupError("project service is unavailable")
        self._project_port.unregister(workspace_id, project_id)

    def archive(self, workspace_id: WorkspaceId, project_id: ProjectId, *, now: object) -> bool:
        if self._project_port is None:
            raise LookupError("project service is unavailable")
        return self._project_port.archive(workspace_id, project_id, now=now)


def parse_page_query(query: str | None) -> tuple[int, int]:
    """Parse a bounded plugin cursor without accepting duplicate parameters."""

    if not query:
        return 50, 0
    values: dict[str, str] = {}
    for pair in query.split("&"):
        if not pair or "=" not in pair:
            raise ValueError("query parameters must use key=value form")
        key, value = pair.split("=", 1)
        key, value = unquote(key), unquote(value)
        if key not in {"limit", "cursor"} or key in values:
            raise ValueError("plugin pagination query is invalid")
        values[key] = value
    try:
        limit = int(values.get("limit", "50"))
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    cursor = values.get("cursor")
    if cursor is None:
        return limit, 0
    if not cursor.startswith("pp1."):
        raise ValueError("plugin cursor is invalid")
    encoded = cursor[4:]
    try:
        offset = int(base64.urlsafe_b64decode((encoded + "===").encode("ascii")).decode("ascii"))
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError("plugin cursor is invalid") from exc
    if offset < 0:
        raise ValueError("plugin cursor is invalid")
    return limit, offset


__all__ = ("ProjectApplication", "WorkspaceApplication", "parse_page_query")
