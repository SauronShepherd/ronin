"""Reference community plugin used to validate the Ronin plugin boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from studio_core import (
    EnvironmentDefinition,
    EnvironmentId,
    ProjectId,
    ProjectManifest,
    Workspace,
    WorkspaceId,
)
from studio_core.plugin_events import new_event
from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution

from .ports import ProjectPort, WorkspacePort
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
            "workspaces.get.v1",
            "workspaces.create.v1",
            "workspaces.update.v1",
            "workspaces.archive.v1",
            "environments.list.v1",
            "environments.get.v1",
            "environments.create.v1",
            "environments.replace.v1",
            "environments.disable.v1",
            "environments.enable.v1",
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
        self._environment_service: object | None = None
        self._event_dispatcher: object | None = None

    def register(self, context: PluginContext) -> None:
        self.context = context
        self._application = WorkspaceApplication(
            cast(WorkspacePort | None, context.services.get("workspace_service"))
        )
        self._projects = ProjectApplication(
            cast(ProjectPort, context.services.get("project_service"))
            if context.services.get("project_service") is not None
            else None
        )
        self._environment_service = context.services.get("environment_service")
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
        context.contributions.add_route(
            "GET",
            "/v1/workspaces/{workspace_id}",
            context.plugin_id,
            self.get_workspace,
            permission="workspaces:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/workspaces",
            context.plugin_id,
            self.create_workspace,
            permission="workspaces:write",
        )
        context.contributions.add_route(
            "PUT",
            "/v1/workspaces/{workspace_id}",
            context.plugin_id,
            self.update_workspace,
            permission="workspaces:write",
        )
        context.contributions.add_route(
            "POST",
            "/v1/workspaces/{workspace_id}/archive",
            context.plugin_id,
            self.archive_workspace,
            permission="workspaces:write",
        )
        for method, path, handler, permission in (
            (
                "GET",
                "/v1/workspaces/{workspace_id}/environments",
                self.list_environments,
                "workspaces:read",
            ),
            (
                "POST",
                "/v1/workspaces/{workspace_id}/environments",
                self.create_environment,
                "workspaces:write",
            ),
            (
                "GET",
                "/v1/workspaces/{workspace_id}/environments/{environment_id}",
                self.get_environment,
                "workspaces:read",
            ),
            (
                "PUT",
                "/v1/workspaces/{workspace_id}/environments/{environment_id}",
                self.replace_environment,
                "workspaces:write",
            ),
            (
                "POST",
                "/v1/workspaces/{workspace_id}/environments/{environment_id}/disable",
                self.disable_environment,
                "workspaces:write",
            ),
            (
                "POST",
                "/v1/workspaces/{workspace_id}/environments/{environment_id}/enable",
                self.enable_environment,
                "workspaces:write",
            ),
        ):
            context.contributions.add_route(
                method, path, context.plugin_id, handler, permission=permission
            )
        for contribution in (
            SurfaceContribution(
                id="workspaces.list.v1",
                plugin_id=context.plugin_id,
                namespace="workspaces",
                command="list",
                operation_id="workspaces.list.v1",
                capability="workspaces.read",
                permission="workspaces:read",
                path="/v1/workspaces",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="workspaces.get.v1",
                plugin_id=context.plugin_id,
                namespace="workspaces",
                command="get",
                operation_id="workspaces.get.v1",
                capability="workspaces.read",
                permission="workspaces:read",
                path="/v1/workspaces/{workspace_id}",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="workspaces.create.v1",
                plugin_id=context.plugin_id,
                namespace="workspaces",
                command="create",
                operation_id="workspaces.create.v1",
                capability="workspaces.write",
                permission="workspaces:write",
                path="/v1/workspaces",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="workspaces.update.v1",
                plugin_id=context.plugin_id,
                namespace="workspaces",
                command="update",
                operation_id="workspaces.update.v1",
                capability="workspaces.write",
                permission="workspaces:write",
                path="/v1/workspaces/{workspace_id}",
                method="PUT",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="workspaces.archive.v1",
                plugin_id=context.plugin_id,
                namespace="workspaces",
                command="archive",
                operation_id="workspaces.archive.v1",
                capability="workspaces.write",
                permission="workspaces:write",
                path="/v1/workspaces/{workspace_id}/archive",
                method="POST",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="environments.list.v1",
                plugin_id=context.plugin_id,
                namespace="environments",
                command="list",
                operation_id="environments.list.v1",
                capability="workspaces.read",
                permission="workspaces:read",
                path="/v1/workspaces/{workspace_id}/environments",
                method="GET",
                output_schema={"type": "array"},
            ),
            SurfaceContribution(
                id="environments.get.v1",
                plugin_id=context.plugin_id,
                namespace="environments",
                command="get",
                operation_id="environments.get.v1",
                capability="workspaces.read",
                permission="workspaces:read",
                path="/v1/workspaces/{workspace_id}/environments/{environment_id}",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="environments.create.v1",
                plugin_id=context.plugin_id,
                namespace="environments",
                command="create",
                operation_id="environments.create.v1",
                capability="workspaces.write",
                permission="workspaces:write",
                path="/v1/workspaces/{workspace_id}/environments",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="environments.replace.v1",
                plugin_id=context.plugin_id,
                namespace="environments",
                command="replace",
                operation_id="environments.replace.v1",
                capability="workspaces.write",
                permission="workspaces:write",
                path="/v1/workspaces/{workspace_id}/environments/{environment_id}",
                method="PUT",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="environments.disable.v1",
                plugin_id=context.plugin_id,
                namespace="environments",
                command="disable",
                operation_id="environments.disable.v1",
                capability="workspaces.write",
                permission="workspaces:write",
                path="/v1/workspaces/{workspace_id}/environments/{environment_id}/disable",
                method="POST",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="environments.enable.v1",
                plugin_id=context.plugin_id,
                namespace="environments",
                command="enable",
                operation_id="environments.enable.v1",
                capability="workspaces.write",
                permission="workspaces:write",
                path="/v1/workspaces/{workspace_id}/environments/{environment_id}/enable",
                method="POST",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="projects.list.v1",
                plugin_id=context.plugin_id,
                namespace="projects",
                command="list",
                operation_id="projects.list.v1",
                capability="workspaces.read",
                permission="workspaces:read",
                path="/v1/workspaces/{workspace_id}/projects",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="projects.create.v1",
                plugin_id=context.plugin_id,
                namespace="projects",
                command="create",
                operation_id="projects.create.v1",
                capability="workspaces.write",
                permission="projects:write",
                path="/v1/workspaces/{workspace_id}/projects",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="projects.get.v1",
                plugin_id=context.plugin_id,
                namespace="projects",
                command="get",
                operation_id="projects.get.v1",
                capability="workspaces.read",
                permission="projects:read",
                path="/v1/workspaces/{workspace_id}/projects/{project_id}",
                method="GET",
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

    def get_workspace(self, workspace_id: str, **_kwargs: Any) -> dict[str, object]:
        if not self.started or self._application is None:
            raise RuntimeError("workspace service is unavailable")
        workspace = self._application.get(WorkspaceId(workspace_id))
        return {
            "id": str(workspace.id),
            "name": workspace.name,
            "description": workspace.description,
            "state": workspace.state,
        }

    def create_workspace(
        self,
        *,
        body: object | None = None,
        idempotency_key: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if not self.started or self._application is None:
            raise RuntimeError("workspace service is unavailable")
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("Idempotency-Key is required")
        if not isinstance(body, dict):
            raise ValueError("workspace body must be an object")
        raw_id, raw_name = body.get("id"), body.get("name")
        if not isinstance(raw_id, str) or not isinstance(raw_name, str):
            raise ValueError("workspace body requires string id and name")
        description = body.get("description")
        if description is not None and not isinstance(description, str):
            raise ValueError("workspace description must be a string or null")
        workspace = self._application.create(
            Workspace(WorkspaceId(raw_id), raw_name, description), now="plugin"
        )
        return {
            "id": str(workspace.id),
            "name": workspace.name,
            "description": workspace.description,
            "state": workspace.state,
        }

    def update_workspace(
        self,
        workspace_id: str,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if not self.started or self._application is None:
            raise RuntimeError("workspace service is unavailable")
        if not isinstance(body, dict):
            raise ValueError("workspace body must be an object")
        name, description = body.get("name"), body.get("description")
        if not isinstance(name, str) or (
            description is not None and not isinstance(description, str)
        ):
            raise ValueError("workspace body requires string name and description")
        workspace = self._application.update(
            WorkspaceId(workspace_id), name=name, description=description, now="plugin"
        )
        return {
            "id": str(workspace.id),
            "name": workspace.name,
            "description": workspace.description,
            "state": workspace.state,
        }

    def archive_workspace(self, workspace_id: str, **_kwargs: Any) -> dict[str, object]:
        if not self.started or self._application is None:
            raise RuntimeError("workspace service is unavailable")
        workspace = self._application.archive(WorkspaceId(workspace_id), now="plugin")
        return {
            "id": str(workspace.id),
            "name": workspace.name,
            "description": workspace.description,
            "state": workspace.state,
        }

    def _environment_service_or_raise(self) -> Any:
        if self._environment_service is None:
            raise RuntimeError("environment service is unavailable")
        return self._environment_service

    @staticmethod
    def _environment_payload(item: EnvironmentDefinition) -> dict[str, object]:
        return item.to_payload()

    def list_environments(self, workspace_id: str, **_kwargs: Any) -> list[dict[str, object]]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        return [
            self._environment_payload(item)
            for item in self._environment_service_or_raise().list(WorkspaceId(workspace_id))
        ]

    def get_environment(
        self, workspace_id: str, environment_id: str, **_kwargs: Any
    ) -> dict[str, object]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        item = self._environment_service_or_raise().get(
            WorkspaceId(workspace_id), EnvironmentId(environment_id)
        )
        return self._environment_payload(item)

    @staticmethod
    def _parse_environment(
        body: object, environment_id: str | None = None
    ) -> EnvironmentDefinition:
        if not isinstance(body, dict):
            raise ValueError("environment body must be an object")
        item = EnvironmentDefinition.from_payload(body)
        if environment_id is not None and str(item.id) != environment_id:
            raise ValueError("environment body id does not match path")
        return item

    def create_environment(
        self, workspace_id: str, *, body: object | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        item = self._environment_service_or_raise().create(
            WorkspaceId(workspace_id), self._parse_environment(body), now="plugin"
        )
        return self._environment_payload(item)

    def replace_environment(
        self,
        workspace_id: str,
        environment_id: str,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        item = self._environment_service_or_raise().replace(
            WorkspaceId(workspace_id), self._parse_environment(body, environment_id), now="plugin"
        )
        return self._environment_payload(item)

    def disable_environment(
        self, workspace_id: str, environment_id: str, **_kwargs: Any
    ) -> dict[str, object]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        item = self._environment_service_or_raise().disable(
            WorkspaceId(workspace_id), EnvironmentId(environment_id), now="plugin"
        )
        return self._environment_payload(item)

    def enable_environment(
        self, workspace_id: str, environment_id: str, **_kwargs: Any
    ) -> dict[str, object]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        item = self._environment_service_or_raise().enable(
            WorkspaceId(workspace_id), EnvironmentId(environment_id), now="plugin"
        )
        return self._environment_payload(item)

    def list_projects(
        self, workspace_id: str, *, query: str | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        if not self.started:
            raise RuntimeError("workspaces plugin is not ready")
        projects = self._projects
        if projects is None:
            return {"items": [], "next_cursor": None}
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
