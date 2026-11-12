from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_operational_studio_actions_use_product_dialogs() -> None:
    graph = (ROOT / "web/js/graph-studio.js").read_text(encoding="utf-8")
    notebook = (ROOT / "web/js/notebook-studio.js").read_text(encoding="utf-8")
    features = (ROOT / "web/js/features.js").read_text(encoding="utf-8")

    assert "window.confirm" not in graph
    assert "confirmImpact('Execute this authorized graph action?" in graph
    assert "window.confirm" not in notebook
    assert "confirmImpact('Discard unsaved notebook changes?" in notebook
    assert "window.prompt" not in features
    assert 'data-feature-form="ml-deployment-input"' in features
