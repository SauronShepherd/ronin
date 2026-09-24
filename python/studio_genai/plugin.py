"""Plugin boundary for provider-neutral GenAI discovery."""

from __future__ import annotations

from typing import Protocol, cast

from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution


class _GenAIService(Protocol):
    def providers(self, workspace_id: str) -> object: ...
    def health(self, workspace_id: str) -> object: ...


class GenAIPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.genai",
        name="Ronin GenAI",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        capabilities=("genai.discovery",),
        permissions=("genai:read",),
        isolation="worker",
        surface_ids=("genai.providers.v1", "genai.health.v1"),
    )

    def __init__(self) -> None:
        self._service: _GenAIService | None = None

    def register(self, context: PluginContext) -> None:
        self._service = cast(_GenAIService | None, context.services.get("genai"))
        context.contributions.add_permission("genai:read", context.plugin_id)
        for method, path, operation, handler in (
            ("GET", "/v1/workspaces/{workspace_id}/genai/providers", "providers", self.providers),
            ("GET", "/v1/workspaces/{workspace_id}/genai/health", "health", self.health),
        ):
            surface_id = f"genai.{operation}.v1"
            context.contributions.add_route(
                method, path, context.plugin_id, handler, permission="genai:read"
            )
            context.contributions.add_surface(SurfaceContribution(
                id=surface_id, plugin_id=context.plugin_id, namespace="genai",
                command=operation, operation_id=surface_id, capability="genai.discovery",
                permission="genai:read", path=path, method=method,
                output_schema={"type": "object"},
            ))

    def startup(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def providers(self, *, workspace_id: str = "", **_kwargs: object) -> object:
        if self._service is None:
            return {"status": "not_configured", "items": []}
        try:
            return self._service.providers(workspace_id)
        except Exception:
            return {"status": "unavailable", "items": []}

    def health(self, *, workspace_id: str = "", **_kwargs: object) -> object:
        if self._service is None:
            return {"status": "not_configured", "provider": "unavailable"}
        try:
            return self._service.health(workspace_id)
        except Exception:
            return {"status": "unhealthy", "provider": "unavailable"}


def factory() -> GenAIPlugin:
    return GenAIPlugin()
