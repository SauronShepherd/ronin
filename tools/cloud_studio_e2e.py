"""Headless browser smoke test for the standalone Cloud Studio surface."""

from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def exercise(page: Page) -> None:
    page.goto((ROOT / "web" / "cloud-studio.html").as_uri())
    page.locator(".palette-item").first.drag_to(page.locator("#canvas"))
    page.locator(".palette-item").nth(1).drag_to(page.locator("#canvas"))
    assert page.locator(".node").count() == 2

    page.get_by_role("button", name="Zoom in").click()
    assert page.locator("#zoom-reset").inner_text() == "110%"

    page.locator(".node").first.click()
    assert page.locator("#name").is_enabled()
    page.locator("#name").fill("primary_bucket")
    page.get_by_role("button", name="Save node").click()
    assert "primary_bucket" in page.locator(".node").first.inner_text()

    page.get_by_role("button", name="Auto-layout").click()
    assert "Auto-layout applied" in page.locator("#status").inner_text()

    with page.expect_download() as download_info:
        page.get_by_role("button", name="Export JSON").click()
    assert download_info.value.suggested_filename == "cloud-topology.json"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        exercise(page)
        browser.close()
    print("Cloud Studio browser E2E passed")


if __name__ == "__main__":
    main()
