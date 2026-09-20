"""Declarative UI contribution for Ronin AI Studio."""

UI_MANIFEST = {
    "pluginId": "com.sauronshepherd.ronin.ai-studio",
    "version": "1.0",
    "navigation": [
        {
            "id": "ai-studio-models", "labelKey": "aiStudio.models",
            "route": "/ai-studio/models", "permission": "ai-studio:read",
        },
        {
            "id": "ai-studio-endpoints", "labelKey": "aiStudio.endpoints",
            "route": "/ai-studio/endpoints", "permission": "ai-studio:admin",
        },
        {
            "id": "ai-studio-health", "labelKey": "aiStudio.health",
            "route": "/ai-studio/health", "permission": "ai-studio:read",
        },
    ],
}
