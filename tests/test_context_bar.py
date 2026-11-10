from __future__ import annotations

from pathlib import Path


def test_context_bar_rehydrates_context_after_browser_history_navigation() -> None:
    source = (Path(__file__).parents[1] / "web/js/context-bar.js").read_text(encoding="utf-8")

    assert "function syncContextFromLocation()" in source
    assert "new URLSearchParams(location.search)" in source
    assert "window.addEventListener('popstate', syncContextFromLocation)" in source
    assert "window.dispatchEvent(new CustomEvent('ronin-context-change'" in source
