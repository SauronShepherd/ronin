from __future__ import annotations

import pytest
from studio_plugin_sdk import PluginManifest
from studio_plugin_testkit import assert_plugin_ready, validate_plugin


class _Plugin:
    manifest = PluginManifest(
        id="com.example.test",
        name="Example",
        version="1.0.0",
        plugin_api="1.0",
        capabilities=("example.read",),
        permissions=("example:read",),
    )

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.started = False

    def register(self, context) -> None:
        context.contributions.add_route(
            "GET", "/v1/example", context.plugin_id, self.handle, permission="example:read"
        )

    def startup(self) -> None:
        if self.fail:
            raise RuntimeError("not ready")
        self.started = True

    def shutdown(self) -> None:
        self.started = False

    def handle(self, **_kwargs: object) -> dict[str, str]:
        return {"status": "ok"}


def test_external_plugin_testkit_validates_contract() -> None:
    report = assert_plugin_ready(_Plugin())

    assert report.plugin_id == "com.example.test"
    assert report.routes == (("GET", "/v1/example"),)
    assert report.states == ("ready",)


def test_testkit_reports_degraded_optional_plugin() -> None:
    report = validate_plugin(_Plugin(fail=True))

    assert report.states == ("degraded",)
    with pytest.raises(AssertionError, match="did not become ready"):
        assert_plugin_ready(_Plugin(fail=True))
