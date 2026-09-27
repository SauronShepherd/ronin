from pathlib import Path

ROOT = Path(__file__).parents[1] / "web"


def test_data_engineering_studio_ui_bundle_is_present_and_wired() -> None:
    html = (ROOT / "data-enginerring-studio.html").read_text(encoding="utf-8")
    javascript = (ROOT / "data-enginerring-studio.js").read_text(encoding="utf-8")
    assert "Data Enginerring Studio" in html
    assert 'id="canvas"' in html
    assert "/v1/data-engineering/pipelines/validate" in javascript
    assert "/v1/data-engineering/pipelines/preview" in javascript
    assert "/v1/data-engineering/pipelines/runs" in javascript
    assert "workspace_id" in javascript
    assert "lastValidationDigest" in javascript
    assert "Connect selected" in html
    assert "Submit durable run" in html
    assert "spark-connect" in html
