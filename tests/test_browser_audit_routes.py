from __future__ import annotations

import json
from pathlib import Path

from tools.browser_audit import load_routes


def test_every_studio_route_declares_a_unique_smoke_selector() -> None:
    manifest = json.loads((Path("web") / "routes.json").read_text(encoding="utf-8"))
    assert tuple(item["id"] for item in manifest) == load_routes()
    selectors = [item.get("smoke_selector") for item in manifest]
    assert all(isinstance(selector, str) and selector.strip() for selector in selectors)
    assert len(selectors) == len(set(selectors))
