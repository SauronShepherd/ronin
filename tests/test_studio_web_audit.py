from pathlib import Path

from tools import studio_web_audit


def test_web_audit_accepts_json_and_mjs_assets(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<meta name="description"><script type="module"></script>'
        '<div id="view"></div><main id="main"></main>',
        encoding="utf-8",
    )
    scripts = tmp_path / "js"
    scripts.mkdir()
    (scripts / "fixture.test.mjs").write_text("export const value = 1;", encoding="utf-8")
    (tmp_path / "routes.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(studio_web_audit, "WEB", tmp_path)

    result = studio_web_audit.audit()

    assert result["failures"] == []
    assert result["module_count"] == 1
