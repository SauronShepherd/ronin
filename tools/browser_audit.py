"""Run a real Chromium smoke audit against a served Studio shell."""

from __future__ import annotations

import asyncio
import json
import sys
from importlib import import_module
from pathlib import Path


async def run(url: str) -> dict[str, object]:
    async_playwright = import_module("playwright.async_api").async_playwright

    console_errors: list[str] = []
    pages: list[dict[str, object]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
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
        for route in (
            "home",
            "runs",
            "workspaces",
            "workflows",
            "access",
            "sql",
            "catalog",
            "migration",
            "mlstudio",
        ):
            await page.goto(url + "#" + route, wait_until="networkidle")
            pages.append(
                {
                    "route": route,
                    "status": await page.locator("#view-title").count(),
                    "h1_count": await page.locator("h1").count(),
                    "has_main": await page.locator("main").count() == 1,
                    "has_nav": await page.locator("nav").count() == 1,
                    "horizontal_overflow": await page.evaluate(
                        "document.documentElement.scrollWidth > window.innerWidth"
                    ),
                }
            )
            if route == "mlstudio":
                pages[-1]["has_ml_controls"] = await page.locator(
                    '[data-feature-form="ml-create"], #ml-labs, #ml-output'
                ).count() == 3
                pages[-1]["has_ml_score"] = await page.locator(
                    '[data-feature-form="ml-score"]'
                ).count() == 1
            if route == "migration":
                pages[-1]["has_migration_controls"] = await page.locator(
                    "#migration-cockpit-create, #migration-cockpit-validate"
                ).count() == 2
                pages[-1]["has_migration_artifact_form"] = await page.locator(
                    "#migration-artifact-form, #migration-artifact-file, #migration-artifact-media"
                ).count() == 3
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
        "pages": pages,
        "console_errors": console_errors,
        "tab_focus": focused,
    }
    await asyncio.to_thread(_write_audit, result)
    failures = [
        p["route"]
        for p in pages
        if p["h1_count"] != 1 or not p["has_main"] or not p["has_nav"] or p["horizontal_overflow"]
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


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"))
