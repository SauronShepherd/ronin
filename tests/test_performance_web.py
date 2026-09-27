from pathlib import Path


def test_performance_studio_native_web_entry_is_packaged_and_declared() -> None:
    root = Path(__file__).parents[1]
    index = (root / "web" / "index.html").read_text(encoding="utf-8")
    module = (root / "web" / "js" / "performance-studio.js").read_text(encoding="utf-8")
    packaging = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert 'src="./js/performance-studio.js"' in index
    assert "#performance" in module
    assert "/api/v1/performance/analyze" in module
    assert "web/js/performance-studio.js" in packaging
