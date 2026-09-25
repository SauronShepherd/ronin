"""Run standards-based axe-core and responsive checks against an installed wheel."""

from __future__ import annotations

import argparse
import json
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

# mypy: ignore-errors

try:
    from tools.installed_studio_browser_smoke import unpack_web as _unpack_web
except ModuleNotFoundError:  # Direct ``python tools/...`` execution.
    from installed_studio_browser_smoke import (
        unpack_web as _unpack_web,  # type: ignore[import-untyped, no-redef]
    )

VIEWPORTS = ((320, 800), (768, 1024), (1440, 900))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    axe_path = next(
        (
            candidate
            for candidate in (
                Path("node_modules/axe-core/axe.min.js"),
                Path("web-tests/node_modules/axe-core/axe.min.js"),
            )
            if candidate.is_file()
        ),
        None,
    )
    if axe_path is None:
        raise SystemExit("run npm ci before the accessibility audit")

    with tempfile.TemporaryDirectory(prefix="ronin-installed-a11y-") as temporary:
        web_root = _unpack_web(args.wheel, Path(temporary))
        manifest = json.loads((web_root / "routes.json").read_text(encoding="utf-8"))
        routes = tuple(item["id"] for item in manifest)

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass

        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(QuietHandler, directory=str(web_root))
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        violations: list[dict[str, object]] = []
        layout_failures: list[dict[str, object]] = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.route(
                    "**/v1/**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body='{"items":[],"surfaces":[]}',
                    ),
                )
                page.add_init_script(script=axe_path.read_text(encoding="utf-8"))
                for width, height in VIEWPORTS:
                    page.set_viewport_size({"width": width, "height": height})
                    for route in routes:
                        page.goto(
                            f"http://127.0.0.1:{server.server_port}/index.html#{route}",
                            wait_until="networkidle",
                        )
                        result = page.evaluate(
                            """async () => (await axe.run(document, {
                              runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}
                            })).violations"""
                        )
                        for violation in result:
                            if violation["impact"] in {"critical", "serious"}:
                                violations.append(
                                    {"viewport": [width, height], "route": route, **violation}
                                )
                        overflow = page.evaluate(
                            """() => ({
                              page: document.documentElement.scrollWidth > window.innerWidth,
                              scrollWidth: document.documentElement.scrollWidth,
                              clientWidth: document.documentElement.clientWidth,
                              offenders: [...document.querySelectorAll('*')]
                                .filter(element =>
                                  element.getBoundingClientRect().right > window.innerWidth + 1
                                )
                                .slice(0, 8).map(element => ({
                                  tag: element.tagName,
                                  className: element.className,
                                  right: element.getBoundingClientRect().right
                                })),
                              scrollContainers: [...document.querySelectorAll('*')]
                                .filter(element => element.scrollWidth > element.clientWidth + 1)
                                .slice(0, 8).map(element => ({
                                  tag: element.tagName,
                                  className: element.className,
                                  scrollWidth: element.scrollWidth,
                                  clientWidth: element.clientWidth
                                }))
                            })"""
                        )
                        if overflow["page"]:
                            layout_failures.append(
                                {"viewport": [width, height], "route": route, **overflow}
                            )
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    result = {"violations": violations, "layout_failures": layout_failures}
    print(json.dumps(result, indent=2))
    if violations or layout_failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
