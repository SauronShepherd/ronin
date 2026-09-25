"""Third-party tutorial plugin using only Ronin's public SDK."""

from studio_plugin_sdk import PluginContext, PluginManifest, SurfaceContribution


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
        surface_ids=("tutorial.get.v1",),
    )

    def register(self, context: PluginContext) -> None:
        context.contributions.add_route(
            "GET",
            "/v1/tutorial",
            context.plugin_id,
            self.get_tutorial,
            permission="tutorial:read",
        )
        context.contributions.add_surface(
            SurfaceContribution(
                id="tutorial.get.v1",
                plugin_id=context.plugin_id,
                namespace="tutorial",
                command="get",
                operation_id="tutorial.get.v1",
                capability="tutorial.example",
                permission="tutorial:read",
                path="/v1/tutorial",
                method="GET",
                output_schema={"type": "object"},
            )
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
