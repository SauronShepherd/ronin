"""Third-party tutorial plugin using only Ronin's public SDK."""

from studio_plugin_sdk import PluginContext, PluginManifest


class TutorialPlugin:
    manifest = PluginManifest(
        id="com.example.ronin.tutorial",
        name="Ronin Tutorial",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        edition="third-party",
        capabilities=("tutorial.example",),
        permissions=("tutorial:read",),
    )

    def register(self, context: PluginContext) -> None:
        context.contributions.add_route(
            "GET",
            "/v1/tutorial",
            context.plugin_id,
            self.get_tutorial,
            permission="tutorial:read",
        )

    def startup(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def get_tutorial(self, **_kwargs: object) -> dict[str, str]:
        return {"status": "ok", "source": "third-party"}


def factory() -> TutorialPlugin:
    return TutorialPlugin()


__all__ = ("TutorialPlugin", "factory")
