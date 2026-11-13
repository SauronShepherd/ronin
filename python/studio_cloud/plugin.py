"""Ronin plugin boundary for Cloud Studio."""

import os
from typing import Any

from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution

from .backends import EmulatorBackend, InMemoryBackend, create_backend, terraform_provider_config
from .engine import (
    CATALOG,
    CloudEmulator,
    CloudResource,
    CloudTopology,
    SnapshotStore,
    export_terraform,
    import_terraform,
)


class CloudStudioPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.cloud-studio",
        name="Cloud Studio",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        capabilities=(
            "cloud-studio.catalog",
            "cloud-studio.topology",
            "cloud-studio.emulator",
            "cloud-studio.terraform",
        ),
        permissions=("cloud-studio:read", "cloud-studio:write"),
        ui_entry="cloud-studio",
        surface_ids=(
            "cloud-studio.catalog.v1",
            "cloud-studio.validate.v1",
            "cloud-studio.plan.v1",
            "cloud-studio.terraform.v1",
        ),
    )

    def __init__(
        self,
        backend_kind: str = "in-memory",
        endpoint: str | None = None,
        snapshot_dir: str | None = None,
        terraform_root: str | None = None,
        iac_executable: str = "terraform",
    ) -> None:
        self.started = False
        self.backend = create_backend(
            backend_kind,
            endpoint,
            terraform_root or os.getenv("RONIN_CLOUD_STUDIO_TERRAFORM_ROOT") or None,
            os.getenv("RONIN_CLOUD_STUDIO_IAC", iac_executable),
        )
        self._workspace_backends: dict[str, EmulatorBackend] = {"default": self.backend}
        configured_snapshot_root = os.getenv("RONIN_CLOUD_STUDIO_SNAPSHOTS")
        snapshot_root: str = (
            snapshot_dir
            if snapshot_dir is not None
            else configured_snapshot_root or ".ronin/cloud-studio"
        )
        self.snapshots = SnapshotStore(snapshot_root)

    def register(self, context: PluginContext) -> None:
        context.contributions.add_ui(
            context.plugin_id,
            {
                "id": "cloud-studio",
                "label": "Cloud Studio",
                "entry": "cloud-studio.html",
                "navigation": {"group": "Build", "path": "/cloud-studio"},
                "capabilities": ["cloud-studio.topology", "cloud-studio.terraform"],
            },
        )
        context.contributions.add_route(
            "GET",
            "/v1/cloud-studio/catalog",
            context.plugin_id,
            self.catalog,
            permission="cloud-studio:read",
        )
        for contribution in (
            SurfaceContribution(
                id="cloud-studio.catalog.v1",
                plugin_id=context.plugin_id,
                namespace="cloud-studio",
                command="catalog",
                operation_id="cloud-studio.catalog.v1",
                capability="cloud-studio.catalog",
                permission="cloud-studio:read",
                path="/v1/cloud-studio/catalog",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="cloud-studio.validate.v1",
                plugin_id=context.plugin_id,
                namespace="cloud-studio",
                command="validate",
                operation_id="cloud-studio.validate.v1",
                capability="cloud-studio.topology",
                permission="cloud-studio:read",
                path="/v1/cloud-studio/validate",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="cloud-studio.plan.v1",
                plugin_id=context.plugin_id,
                namespace="cloud-studio",
                command="plan",
                operation_id="cloud-studio.plan.v1",
                capability="cloud-studio.emulator",
                permission="cloud-studio:read",
                path="/v1/cloud-studio/plan",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="cloud-studio.terraform.v1",
                plugin_id=context.plugin_id,
                namespace="cloud-studio",
                command="terraform",
                operation_id="cloud-studio.terraform.v1",
                capability="cloud-studio.terraform",
                permission="cloud-studio:read",
                path="/v1/cloud-studio/terraform",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
        ):
            context.contributions.add_surface(contribution)
        context.contributions.add_route(
            "POST",
            "/v1/cloud-studio/validate",
            context.plugin_id,
            self.validate,
            permission="cloud-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/cloud-studio/apply",
            context.plugin_id,
            self.apply,
            permission="cloud-studio:write",
        )
        context.contributions.add_route(
            "POST",
            "/v1/cloud-studio/plan",
            context.plugin_id,
            self.plan,
            permission="cloud-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/cloud-studio/destroy",
            context.plugin_id,
            self.destroy,
            permission="cloud-studio:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/cloud-studio/refresh",
            context.plugin_id,
            self.refresh,
            permission="cloud-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/cloud-studio/terraform",
            context.plugin_id,
            self.terraform,
            permission="cloud-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/cloud-studio/import",
            context.plugin_id,
            self.import_hcl,
            permission="cloud-studio:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/cloud-studio/backend",
            context.plugin_id,
            self.backend_info,
            permission="cloud-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/cloud-studio/snapshots",
            context.plugin_id,
            self.save_snapshot,
            permission="cloud-studio:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/cloud-studio/snapshots",
            context.plugin_id,
            self.load_snapshot,
            permission="cloud-studio:read",
        )

    def startup(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.started = False

    def catalog(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"version": "1", "components": CATALOG}

    @staticmethod
    def _topology(payload: dict[str, Any]) -> CloudTopology:
        resources = tuple(CloudResource(**item) for item in payload.get("resources", []))
        edges = tuple(tuple(edge) for edge in payload.get("edges", []))
        return CloudTopology(resources, edges)

    @staticmethod
    def _request_payload(payload: dict[str, Any] | None, body: object | None) -> dict[str, Any]:
        value = body if body is not None else payload
        if not isinstance(value, dict):
            raise ValueError("cloud request body must be a JSON object")
        return value

    def _backend_for_workspace(self, workspace: str) -> EmulatorBackend:
        if not isinstance(self.backend, InMemoryBackend):
            return self.backend
        if workspace not in self._workspace_backends:
            self._workspace_backends[workspace] = InMemoryBackend(CloudEmulator())
        return self._workspace_backends[workspace]

    def validate(
        self,
        payload: dict[str, Any] | None = None,
        *_args: Any,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        payload = self._request_payload(payload, body)
        topology = self._topology(payload)
        return {"valid": not topology.validate(), "errors": topology.validate()}

    def apply(
        self,
        payload: dict[str, Any] | None = None,
        *_args: Any,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        payload = self._request_payload(payload, body)
        workspace = str(payload.get("workspace", "default"))
        return self._backend_for_workspace(workspace).apply(self._topology(payload))

    def plan(
        self,
        payload: dict[str, Any] | None = None,
        *_args: Any,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        payload = self._request_payload(payload, body)
        workspace = str(payload.get("workspace", "default"))
        return self._backend_for_workspace(workspace).plan(self._topology(payload))

    def refresh(self, *_args: Any, **kwargs: Any) -> dict[str, Any]:
        workspace = str(kwargs.get("workspace", "default"))
        return self._backend_for_workspace(workspace).refresh()

    def destroy(self, *_args: Any, **kwargs: Any) -> dict[str, Any]:
        workspace = str(kwargs.get("workspace", "default"))
        return self._backend_for_workspace(workspace).destroy()

    def terraform(
        self,
        payload: dict[str, Any] | None = None,
        *_args: Any,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, str]:
        payload = self._request_payload(payload, body)
        return {
            "format": "hcl",
            "content": terraform_provider_config(self.backend)
            + "\n"
            + export_terraform(self._topology(payload)),
        }

    def import_hcl(
        self,
        payload: dict[str, Any] | None = None,
        *_args: Any,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        payload = self._request_payload(payload, body)
        topology = import_terraform(str(payload.get("hcl", "")))
        return {
            "resources": [
                {"id": item.id, "type": item.type, "name": item.name, "properties": item.properties}
                for item in topology.resources
            ],
            "edges": list(topology.edges),
        }

    def backend_info(self, *_args: Any, **_kwargs: Any) -> dict[str, object]:
        return self.backend.health()

    def save_snapshot(
        self,
        payload: dict[str, Any] | None = None,
        *_args: Any,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        payload = self._request_payload(payload, body)
        workspace = str(payload.get("workspace", "default"))
        topology = self._topology(payload)
        errors = topology.validate()
        if errors:
            raise ValueError("invalid snapshot: " + "; ".join(errors))
        snapshot = {
            "resources": [
                {
                    "id": item.id,
                    "type": item.type,
                    "name": item.name,
                    "properties": dict(item.properties),
                }
                for item in topology.resources
            ],
            "edges": [list(edge) for edge in topology.edges],
        }
        return {"workspace": workspace, "snapshot": self.snapshots.save(workspace, snapshot)}

    def load_snapshot(
        self, workspace: str = "default", *_args: Any, **kwargs: Any
    ) -> dict[str, Any]:
        workspace = str(kwargs.get("workspace", workspace))
        return {"workspace": workspace, "snapshot": self.snapshots.load(workspace)}


def factory() -> CloudStudioPlugin:
    return CloudStudioPlugin(
        backend_kind=os.getenv("RONIN_CLOUD_STUDIO_BACKEND", "in-memory"),
        endpoint=os.getenv("RONIN_CLOUD_STUDIO_ENDPOINT") or None,
        snapshot_dir=os.getenv("RONIN_CLOUD_STUDIO_SNAPSHOTS") or None,
        terraform_root=os.getenv("RONIN_CLOUD_STUDIO_TERRAFORM_ROOT") or None,
    )
