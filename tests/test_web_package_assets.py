from __future__ import annotations

import tomllib
import re
from pathlib import Path

from tools.check_web_assets import referenced_assets


def test_every_runtime_studio_module_is_declared_as_package_data() -> None:
    root = Path(__file__).parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(project["tool"]["setuptools"]["data-files"]["share/ronin/web/js"])
    runtime_modules = {
        path.relative_to(root).as_posix()
        for path in (root / "web/js").glob("*.js")
        if not path.name.endswith(".test.js")
    }
    assert runtime_modules <= declared


def test_source_studio_asset_graph_is_complete() -> None:
    root = Path(__file__).parents[1] / "web"
    assert all(path.is_file() for path in referenced_assets(root))


def test_app_router_has_no_duplicate_function_declarations() -> None:
    """A duplicate top-level declaration prevents the browser module from loading."""
    root = Path(__file__).parents[1]
    source = (root / "web/js/app.js").read_text(encoding="utf-8")
    names = re.findall(r"(?:^|;)function\s+([A-Za-z_$][\w$]*)\s*\(", source)
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"duplicate app router declarations: {duplicates}"


def test_project_journey_keeps_public_lifecycle_operations() -> None:
    root = Path(__file__).parents[1]
    source = (root / "web/js/project-journey.js").read_text(encoding="utf-8")
    required_controls = (
        "project-journey-form",
        "project-bundle-import-form",
        "project-environment-form",
        "project-archive",
        "/bundle/archive",
        "/bundle/import",
        "/environments/",
        "/archive",
    )
    missing = [control for control in required_controls if control not in source]
    assert not missing, f"project lifecycle coverage regressed: {missing}"


def test_catalog_studio_exposes_glossary_publication() -> None:
    root = Path(__file__).parents[1]
    source = (root / "web/js/catalog-studio.js").read_text(encoding="utf-8")
    for marker in ("glossary-form", "glossary-search-form", "catalog-lineage-form", "/glossary/terms", "/catalog/lineage/", "Idempotency-Key", "references"):
        assert marker in source, f"catalog glossary integration missing: {marker}"


def test_ml_studio_exposes_feature_definition_lifecycle() -> None:
    root = Path(__file__).parents[1]
    source = (root / "web/js/ml-features-studio.js").read_text(encoding="utf-8")
    for marker in ("ml-feature-form", "/v1/ml-studio/features", "ronin.ml-feature/v1", "columns"):
        assert marker in source, f"ML feature lifecycle missing: {marker}"
