"""Browser-qualify the Studio shell from an installed wheel, never the checkout."""

from __future__ import annotations

import argparse
import contextlib
import json
import tarfile
import tempfile
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import cast

from playwright.sync_api import sync_playwright

try:
    from tools.check_web_assets import referenced_assets as _referenced_assets
except ModuleNotFoundError:  # Direct ``python tools/...`` execution.
    from check_web_assets import referenced_assets as _referenced_assets  # type: ignore[import-untyped, no-redef]

ROUTES = ()


def unpack_web(artifact: Path, destination: Path) -> Path:
    web_root = destination / "web"
    if artifact.name.endswith(".whl"):
        with zipfile.ZipFile(artifact) as archive:
            wheel_members = [
                name for name in archive.namelist() if ".data/data/share/ronin/web/" in name
            ]
            if not wheel_members:
                raise RuntimeError("wheel does not contain installed Studio data files")
            prefix = next(
                name.split(".data/data/share/ronin/web/", 1)[0] for name in wheel_members
            )
            for name in wheel_members:
                relative = name.split(f"{prefix}.data/data/share/ronin/web/", 1)[1]
                target = web_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(name))
    else:
        with tarfile.open(artifact, mode="r:gz") as archive:
            sdist_members: list[tarfile.TarInfo] = [
                member
                for member in archive.getmembers()
                if "/web/" in member.name and member.isfile()
            ]
            if not sdist_members:
                raise RuntimeError("sdist does not contain Studio data files")
            marker = next(member.name.index("/web/") for member in sdist_members)
            for member in sdist_members:
                source = archive.extractfile(member)
                if source is None:
                    raise RuntimeError(f"cannot read sdist member: {member.name}")
                target = web_root / member.name[marker + len("/web/") :]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
    return web_root


def qualify(wheel: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ronin-installed-studio-") as temporary:
        web_root = unpack_web(wheel, Path(temporary))
        missing = sorted(path for path in _referenced_assets(web_root) if not path.is_file())
        if missing:
            raise AssertionError(
                "installed Studio import graph references missing assets: "
                + ", ".join(str(path) for path in missing)
            )
        routes_manifest = json.loads((web_root / "routes.json").read_text(encoding="utf-8"))
        routes = tuple(item["id"] for item in routes_manifest)
        route_contracts = {item["id"]: item for item in routes_manifest}

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass

        handler = partial(QuietHandler, directory=str(web_root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        console_errors: list[str] = []
        failed_requests: list[str] = []
        csp_violations: list[str] = []
        pages: list[dict[str, object]] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.route(
                    "**/v1/**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"items": [], "surfaces": []}),
                    ),
                )
                page.route(
                    "**/api/v1/**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"score": 1, "issues": [], "series": {"stages": []}}),
                    ),
                )
                page.on(
                    "console",
                    lambda message: (
                        console_errors.append(message.text) if message.type == "error" else None
                    ),
                )
                page.on("pageerror", lambda error: console_errors.append(str(error)))
                page.on(
                    "requestfailed",
                    lambda request: failed_requests.append(
                        f"{request.method} {request.url}: {request.failure}"
                    ),
                )
                page.on(
                    "response",
                    lambda response: (
                        failed_requests.append(f"{response.status} {response.url}")
                        if response.status >= 400
                        else None
                    ),
                )
                page.on(
                    "console",
                    lambda message: (
                        csp_violations.append(message.text)
                        if "content security policy" in message.text.lower()
                        or "violates the following csp" in message.text.lower()
                        else None
                    ),
                )
                for route in routes:
                    page.goto(f"{base}/index.html#{route}", wait_until="networkidle")
                    contract = route_contracts[route]
                    selector = contract.get("smoke_selector")
                    if selector:
                        with contextlib.suppress(Exception):
                            page.locator(selector).first.wait_for(state="attached", timeout=3000)
                    selector_count = page.locator(selector).count() if selector else 0
                    pages.append(
                        {
                            "route": route,
                            "status": page.locator("h1").count(),
                            "h1": page.locator("h1").count(),
                            "main": page.locator("main").count(),
                            "nav": page.locator("nav").count(),
                            "overflow": page.evaluate(
                                "document.documentElement.scrollWidth > window.innerWidth"
                            ),
                            "smoke_selector": selector,
                            "smoke_selector_count": selector_count,
                        }
                    )
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        failures = [
            page
            for page in pages
            if cast(int, page["status"]) != 1
            or cast(int, page["h1"]) != 1
            or cast(int, page["main"]) != 1
            or cast(int, page["nav"]) != 1
            or cast(bool, page["overflow"])
            or cast(int, page["smoke_selector_count"]) < 1
        ]
        result: dict[str, object] = {
            "wheel": str(wheel),
            "routes": pages,
            "console_errors": console_errors,
            "failed_requests": failed_requests,
            "csp_violations": csp_violations,
            "failures": failures,
        }
        if failures or console_errors or failed_requests or csp_violations:
            raise AssertionError(json.dumps(result, indent=2))
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    print(json.dumps(qualify(args.wheel), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
