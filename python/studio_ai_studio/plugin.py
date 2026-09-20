"""Ronin plugin registration for local inference and AI proxy capability."""

from typing import Protocol, cast

from studio_core.plugins import PluginContext, PluginManifest

from .ui_manifest import UI_MANIFEST


class _HTTPAPI(Protocol):
    def dispatch(self, method: str, path: str, body: object | None = None) -> "_HTTPResponse": ...


class _HTTPResponse(Protocol):
    body: dict[str, object]


class AIStudioPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.ai-studio",
        name="Ronin AI Studio",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        capabilities=("ai-studio.discovery", "ai-studio.proxy", "ai-studio.exposure"),
        permissions=("ai-studio:read", "ai-studio:write"),
        isolation="worker",
        ui_entry="studio_ai_studio.ui_manifest:UI_MANIFEST",
        config_schema="config/ai-studio.schema.json",
    )

    def __init__(self) -> None:
        self._api: _HTTPAPI | None = None

    def register(self, context: PluginContext) -> None:
        self._api = cast(_HTTPAPI | None, context.services.get("ai_studio_http"))
        context.contributions.add_permission("ai-studio:read", context.plugin_id)
        context.contributions.add_permission("ai-studio:invoke", context.plugin_id)
        context.contributions.add_permission("ai-studio:admin", context.plugin_id)
        context.contributions.add_ui(context.plugin_id, UI_MANIFEST)
        context.contributions.add_route(
            "GET",
            "/v1/workspaces/{workspace_id}/ai-studio/models",
            context.plugin_id,
            self.list_models,
            permission="ai-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/workspaces/{workspace_id}/ai-studio/invoke",
            context.plugin_id,
            self.invoke,
            permission="ai-studio:invoke",
        )

    def startup(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def list_models(self, *, body: object | None = None, **_kwargs: object) -> dict[str, object]:
        if self._api is None:
            return {"object": "list", "data": [], "status": "not_configured"}
        response = self._api.dispatch("GET", "/v1/models", body if isinstance(body, dict) else None)
        return dict(response.body)

    def invoke(self, *, body: object | None = None, **_kwargs: object) -> dict[str, object]:
        if not isinstance(body, dict):
            return {"error": {"code": "invalid_request"}}
        if self._api is None:
            return {"error": {"code": "ai_studio_unavailable"}}
        path = "/v1/chat/completions"
        response = self._api.dispatch("POST", path, body)
        return dict(response.body)


def factory() -> AIStudioPlugin:
    return AIStudioPlugin()
