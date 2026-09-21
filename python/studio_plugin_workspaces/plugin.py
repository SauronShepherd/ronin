"""Reference community plugin used to validate the Ronin plugin boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from studio_core import ProjectId, ProjectManifest, WorkspaceId
from studio_core.plugin_events import new_event
from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution

from .ports import WorkspacePort
from .services import ProjectApplication, WorkspaceApplication, parse_page_query


class WorkspacesPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.workspaces",
        name="Ronin Workspaces",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        edition="community",
        capabilities=("workspaces.read", "workspaces.write"),
        permissions=(
            "workspaces:read",
            "workspaces:write",
            "projects:read",
            "projects:write",
        ),
        ui_entry="studio_plugin_workspaces:ui_manifest",
        event_types=(
            "projects.project-created.v1",
            "projects.project-updated.v1",
            "projects.project-deleted.v1",
        ),
        surface_ids=(
            "workspaces.list.v1",
            "projects.list.v1",
            "projects.create.v1",
            "projects.get.v1",
        ),
    )

    def __init__(self) -> None:
        self.started = False
        self.context: PluginContext | None = None
        self._application: WorkspaceApplication | None = None
        self._projects: ProjectApplication | None = None
        self._event_dispatcher: object | None = None

    def register(self, context: PluginContext) -> None:
        self.context = context
        self._application = WorkspaceApplication(
            cast(WorkspacePort | None, context.services.get("workspace_service"))
        )
        self._projects = ProjectApplication(
            cast(object, context.services.get("project_service"))
            if context.services.get("project_service") is not None
            else None
        )
        self._event_dispatcher = context.services.get("event_dispatcher")
        context.contributions.add_ui(
            context.plugin_id,
            {
                "plugin_id": context.plugin_id,
                "ui_api": "1.0",
                "navigation": [
                    {
                        "id": "workspaces",
                        "route": "/workspaces",
                        "permission": "workspaces:read",
                    },
                    {
                        "id": "projects",
                        "route": "/projects",
                        "permission": "projects:read",
                    },
                ],
                "widgets": [],
            },
        )
        context.contributions.add_route(
            "GET",
            "/v1/workspaces",
            context.plugin_id,
            self.list_workspaces,
            permission="workspaces:read",
        )
        for contribution in (
            SurfaceContribution(
                id="workspaces.list.v1", plugin_id=context.plugin_id,
                namespace="workspaces", command="list",
                operation_id="workspaces.list.v1", capability="workspaces.read",
                permission="workspaces:read", path="/v1/workspaces", method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="projects.list.v1", plugin_id=context.plugin_id,
                namespace="projects", command="list",
                operation_id="projects.list.v1", capability="workspaces.read",
                permission="workspaces:read", path="/v1/workspaces/{workspace_id}/projects", method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="projects.create.v1", plugin_id=context.plugin_id,
                namespace="projects", command="create",
                operation_id="projects.create.v1", capability="workspaces.write",
                permission="projects:write", path="/v1/workspaces/{workspace_id}/projects", method="POST",
                input_schema={"type": "object"}, output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="projects.get.v1", plugin_id=context.plugin_id,
                namespace="projects", command="get",
                operation_id="projects.get.v1", capability="workspaces.read",
                permission="projects:read", path="/v1/workspaces/{workspace_id}/projects/{project_id}", method="GET",
                output_schema={"type": "object"},
            ),
        ):
            context.contributions.add_surface(contribution)
        context.contributions.add_route(
            "POST",
            "/v1/workspaces/{workspace_id}/projects",
            context.plugin_id,
            self.create_project,
            permission="projects:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/workspaces/{workspace_id}/projects/{project_id}",
            context.plugin_id,
            self.get_project,
            permission="projects:read",
        )
        context.contributions.add_route(
            "PUT",
            "/v1/workspaces/{workspace_id}/projects/{project_id}",
            context.plugin_id,
            self.replace_project,
            permission="projects:write",
        )
        context.contributions.add_route(
            "DELETE",
            "/v1/workspaces/{workspace_id}/projects/{project_id}",
            context.plugin_id,
            self.delete_project,
            permission="projects:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/workspaces/{workspace_id}/projects",
            context.plugin_id,
            self.list_projects,
            permission="workspaces:read",
        )

    def startup(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.started = False

    def list_workspaces(self, *_args: Any, **_kwargs: Any) -> list[dict[str, object]]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        application = self._application
        if application is None:
            return []
        return application.list_payloads()

    def list_projects(
        self, workspace_id: str, *, query: str | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        projects = self._projects
        if projects is None:
            return []
        limit, offset = parse_page_query(query)
        items, next_cursor = projects.list_payloads(
            WorkspaceId(workspace_id), limit=limit, offset=offset
        )
        return {"items": items, "next_cursor": next_cursor}

    def create_project(
        self,
        workspace_id: str,
        *,
        body: object | None = None,
        idempotency_key: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("Idempotency-Key is required")
        if not isinstance(body, dict):
            raise ValueError("project body must be an object")
        projects = self._projects
        if projects is None:
            raise RuntimeError("project service is unavailable")
        manifest = ProjectManifest.from_data(body)
        stored = projects.register(WorkspaceId(workspace_id), manifest, now="plugin")
        self._publish(
            "projects.project-created.v1",
            WorkspaceId(workspace_id),
            {"project_id": str(stored.project.id), "name": stored.project.name},
            idempotency_key,
        )
        return stored.to_data()

    def get_project(
        self,
        workspace_id: str,
        project_id: str,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if not self.started or self._projects is None:
            raise RuntimeError("project service is unavailable")
        return self._projects.get(WorkspaceId(workspace_id), ProjectId(project_id)).to_data()

    def replace_project(
        self,
        workspace_id: str,
        project_id: str,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if not self.started or self._projects is None:
            raise RuntimeError("project service is unavailable")
        if not isinstance(body, dict):
            raise ValueError("project body must be an object")
        manifest = ProjectManifest.from_data(body)
        if str(manifest.project.id) != project_id:
            raise ValueError("project body id does not match path")
        stored = self._projects.replace(WorkspaceId(workspace_id), manifest, now="plugin")
        self._publish(
            "projects.project-updated.v1",
            WorkspaceId(workspace_id),
            {"project_id": project_id, "name": stored.project.name},
            project_id,
        )
        return stored.to_data()

    def delete_project(
        self,
        workspace_id: str,
        project_id: str,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if not self.started or self._projects is None:
            raise RuntimeError("project service is unavailable")
        self._projects.unregister(WorkspaceId(workspace_id), ProjectId(project_id))
        self._publish(
            "projects.project-deleted.v1",
            WorkspaceId(workspace_id),
            {"project_id": project_id},
            project_id,
        )
        return {"unregistered": True, "project_id": project_id}

    def _publish(
        self,
        event_type: str,
        workspace_id: WorkspaceId,
        payload: dict[str, object],
        correlation_id: str,
    ) -> None:
        dispatcher = self._event_dispatcher
        publish = getattr(dispatcher, "publish", None)
        if publish is None:
            return
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        event = new_event(
            event_id=f"{event_type}-{digest}",
            event_type=event_type,
            producer=self.manifest.id,
            tenant_id=str(workspace_id),
            correlation_id=correlation_id,
            occurred_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            payload=payload,
        )
        publish(event)


def factory() -> WorkspacesPlugin:
    return WorkspacesPlugin()


def ui_manifest() -> dict[str, object]:
    """Return the declarative UI contribution for tooling and shell builds."""
    return {
        "plugin_id": WorkspacesPlugin.manifest.id,
        "ui_api": "1.0",
        "navigation": [
            {"id": "workspaces", "route": "/workspaces", "permission": "workspaces:read"},
            {"id": "projects", "route": "/projects", "permission": "projects:read"},
        ],
        "widgets": [],
    }


__all__ = ("WorkspacesPlugin", "factory", "ui_manifest")
