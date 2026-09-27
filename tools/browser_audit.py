"""Run a real Chromium smoke audit against a served Studio shell."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from importlib import import_module
from pathlib import Path
from typing import cast


def load_routes(path: Path = Path("web/routes.json")) -> tuple[str, ...]:
    """Load the canonical Studio route manifest instead of duplicating it."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read Studio route manifest: {path}") from exc
    if not isinstance(manifest, list) or not manifest:
        raise RuntimeError("Studio route manifest must be a non-empty array")
    routes = tuple(item.get("id") for item in manifest if isinstance(item, dict))
    if not routes or any(not isinstance(route, str) or not route for route in routes):
        raise RuntimeError("Studio route manifest contains an invalid route")
    if len(set(routes)) != len(routes):
        raise RuntimeError("Studio route manifest contains duplicate routes")
    return cast(tuple[str, ...], routes)


STUDIO_ROUTES = load_routes()


async def run(url: str, *, headed: bool = False, slow_mo_ms: float = 0) -> dict[str, object]:
    async_playwright = import_module("playwright.async_api").async_playwright

    console_errors: list[str] = []
    pages: list[dict[str, object]] = []
    studio_routes = load_routes()
    route_specs = await asyncio.to_thread(_load_route_specs)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not headed, slow_mo=slow_mo_ms)
        page = await browser.new_page(viewport={"width": 320, "height": 800})
        await page.add_init_script(
            "sessionStorage.setItem('ronin.session', 'audit-token');"
            "sessionStorage.removeItem('ronin.api');"
        )
        page.on(
            "console",
            lambda msg: (
                console_errors.append(msg.text)
                if msg.type == "error" and not msg.text.startswith("Failed to load resource")
                else None
            ),
        )
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        await page.goto(url + "#home", wait_until="networkidle")
        for route in studio_routes:
            await page.goto(url + "#" + route, wait_until="networkidle")
            route_spec = route_specs[route]
            smoke_selector = route_spec.get("smoke_selector")
            if not isinstance(smoke_selector, str) or not smoke_selector.strip():
                raise RuntimeError(f"route {route} has no smoke_selector")
            pages.append(
                {
                    "route": route,
                    "status": await page.locator("#view-title").count(),
                    "h1_count": await page.locator("h1").count(),
                    "has_main": await page.locator("main").count() == 1,
                    "has_nav": await page.locator("nav").count() == 1,
                    "smoke_selector": smoke_selector,
                    "has_smoke_selector": await page.locator(smoke_selector).count() >= 1,
                    "horizontal_overflow": await page.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth"
                    ),
                }
            )
            if route == "mlstudio":
                pages[-1]["has_ml_controls"] = (
                    await page.locator(
                        '[data-feature-form="ml-create"], #ml-labs, #ml-output'
                    ).count()
                    == 3
                )
                pages[-1]["has_ml_score"] = (
                    await page.locator('[data-feature-form="ml-score"]').count() == 1
                )
            if route == "migration":
                pages[-1]["has_migration_controls"] = (
                    await page.locator(
                        "#migration-cockpit-create, #migration-cockpit-validate"
                    ).count()
                    == 2
                )
                pages[-1]["has_migration_artifact_form"] = (
                    await page.locator(
                        "#migration-artifact-form, #migration-artifact-file, "
                        "#migration-artifact-media"
                    ).count()
                    == 3
                )
        await page.goto(url + "#home", wait_until="networkidle")
        focused: list[str] = []
        for _ in range(8):
            await page.keyboard.press("Tab")
            focused.append(
                await page.evaluate(
                    "document.activeElement?.tagName + '#' + (document.activeElement?.id || '')"
                )
            )
        await browser.close()
    result = {
        "url": url,
        "pages_visited": len(pages),
        "routes": list(studio_routes),
        "pages": pages,
        "console_errors": console_errors,
        "tab_focus": focused,
    }
    await asyncio.to_thread(_write_audit, result)
    failures = [
        p["route"]
        for p in pages
        if p["h1_count"] != 1
        or not p["has_main"]
        or not p["has_nav"]
        or p["horizontal_overflow"]
        or not p["has_smoke_selector"]
        or (
            p["route"] == "mlstudio"
            and (not p.get("has_ml_controls", False) or not p.get("has_ml_score", False))
        )
        or (p["route"] == "migration" and not p.get("has_migration_controls", False))
        or (p["route"] == "migration" and not p.get("has_migration_artifact_form", False))
    ]
    if console_errors or failures:
        raise SystemExit(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return result


def _write_audit(result: dict[str, object]) -> None:
    Path("artifacts/studio").mkdir(parents=True, exist_ok=True)
    Path("artifacts/studio/audit.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )


def _load_route_specs(path: Path = Path("web/routes.json")) -> dict[str, dict[str, object]]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read Studio route manifest: {path}") from exc
    if not isinstance(manifest, list):
        raise RuntimeError("Studio route manifest must be an array")
    specs: dict[str, dict[str, object]] = {}
    for item in manifest:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise RuntimeError("Studio route manifest contains an invalid route")
        if item["id"] in specs:
            raise RuntimeError("Studio route manifest contains duplicate routes")
        specs[item["id"]] = item
    return specs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default="http://127.0.0.1:8765/")
    parser.add_argument("--headed", action="store_true", help="show the Chromium window")
    parser.add_argument(
        "--slow-mo-ms",
        type=float,
        default=float(os.environ.get("RONIN_UI_SLOW_MO_MS", "0")),
        help="delay each Playwright action by this many milliseconds",
    )
    args = parser.parse_args()
    asyncio.run(run(args.url, headed=args.headed, slow_mo_ms=args.slow_mo_ms))
