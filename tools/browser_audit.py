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
        page.on(
            "console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None
        )
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        await page.goto(url + "#home", wait_until="networkidle")
        for route in ("home", "runs", "workspaces", "workflows", "access", "sql", "catalog"):
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
