from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from threading import Thread

import pytest
from studio_core import Grant, GrantSet, ResourceScope
from studio_execution import DurableExecutionService
from studio_orchestrator import Instant
from studio_server import RoninHTTPServer
from studio_storage import SqliteJobStore

from tools.check_web_assets import referenced_assets

_GRANTS = GrantSet(
    (
        Grant(
            frozenset({"read", "list", "events", "submit", "execute", "cancel", "evidence:read"}),
            ResourceScope("*", None),
        ),
    )
)


def test_studio_assets_are_allowlisted_and_served(tmp_path) -> None:
    service = DurableExecutionService(
        SqliteJobStore(tmp_path / "ronin.db", migration_now=Instant("2026-09-06T20:00:00.000000Z"))
    )
    server = RoninHTTPServer(  # noqa: S106
        ("127.0.0.1", 0),
        service,
        token="test-token",  # noqa: S106 - deterministic fixture credential
        grants=_GRANTS,  # noqa: S106
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(  # noqa: S310
            f"{base_url}/studio/", timeout=2
        ) as response:
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/html")
            assert b"RONIN Studio" in response.read()
            assert response.headers["Cache-Control"] == "no-cache"
        for asset, content_type in (
            ("js/app.js", "text/javascript"),
            ("styles/base.css", "text/css"),
            ("assets/ronin-logo-full.png", "image/png"),
            ("data-enginerring-studio.html", "text/html"),
            ("data-enginerring-studio.js", "text/javascript"),
            ("data-enginerring-studio.css", "text/css"),
        ):
            with urllib.request.urlopen(f"{base_url}/studio/{asset}", timeout=2) as response:  # noqa: S310
                assert response.status == 200
                assert response.headers["Content-Type"].startswith(content_type)
        with pytest.raises(urllib.error.HTTPError) as error_info:
            urllib.request.urlopen(f"{base_url}/studio/../pyproject.toml", timeout=2)  # noqa: S310
        assert error_info.value.code == 404
        request = urllib.request.Request(  # noqa: S310
            f"{base_url}/studio/secret.txt",
            headers={"Authorization": "Bearer test-token"},
        )
        with pytest.raises(urllib.error.HTTPError) as error_info:
            urllib.request.urlopen(request, timeout=2)  # noqa: S310
        assert error_info.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        asyncio.run(service.aclose())


def test_published_migration_cockpit_contains_operational_controls() -> None:
    source = (Path(__file__).parents[1] / "web" / "js" / "app.js").read_text(encoding="utf-8")
    for marker in (
        "Migration runtime cockpit",
        "migration-cockpit-create",
        "migration-cockpit-discover",
        "migration-capture",
        "migration-optimize",
        "migration-export",
        "migration-cockpit-validate",
        "migration-validation-level",
        "/promote`,",
        "No synthetic benchmark is generated",
        "migration-submit-promotion",
        "migration-artifact-form",
        "source-artifacts/",
        "/export",
        "Portable migration script",
    ):
        assert marker in source


def test_studio_import_graph_resolves_every_relative_asset() -> None:
    root = Path(__file__).parents[1] / "web"
    referenced = referenced_assets(root)
    assert referenced
    assert all(asset.is_file() for asset in referenced)


def test_studio_import_graph_includes_css_url_resources(tmp_path: Path) -> None:
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text('<link rel="stylesheet" href="styles.css">', encoding="utf-8")
    (root / "styles.css").write_text("body { background: url('assets/bg.png'); }", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "bg.png").write_bytes(b"png")
    assert root / "assets" / "bg.png" in referenced_assets(root)


def test_active_route_manifest_requires_functional_smoke_contract() -> None:
    manifest = json.loads((Path(__file__).parents[1] / "web" / "routes.json").read_text())
    for route in manifest:
        assert route["id"]
        assert route["title"]
        assert route["state"]
        assert route["smoke_selector"]
        if route["id"] != "home" and route["state"] == "active":
            assert route["smoke_selector"] != "#view"
        for endpoint in route.get("required_api", []):
            assert isinstance(endpoint, str)
            assert endpoint.startswith("/")


def test_studio_index_has_one_valid_document_shell() -> None:
    class Structure(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.starts: list[str] = []
            self.module_scripts = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.starts.append(tag)
            if tag == "script" and dict(attrs).get("type") == "module":
                self.module_scripts += 1

    parser = Structure()
    parser.feed((Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8"))
    assert parser.starts.count("html") == 1
    assert parser.starts.count("head") == 1
    assert parser.starts.count("body") == 1
    assert parser.starts.count("main") == 1
    assert parser.module_scripts >= 1
