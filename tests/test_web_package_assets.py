from __future__ import annotations

import json
import re
import tomllib
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
    for marker in (
        "glossary-form",
        "glossary-search-form",
        "catalog-lineage-form",
        "/glossary/terms",
        "/catalog/lineage/",
        "Idempotency-Key",
        "references",
    ):
        assert marker in source, f"catalog glossary integration missing: {marker}"


def test_ml_studio_exposes_feature_definition_lifecycle() -> None:
    root = Path(__file__).parents[1]
    source = (root / "web/js/ml-features-studio.js").read_text(encoding="utf-8")
    for marker in ("ml-feature-form", "/v1/ml-studio/features", "ronin.ml-feature/v1", "columns"):
        assert marker in source, f"ML feature lifecycle missing: {marker}"


def test_public_studio_does_not_publish_model_invocation_or_genai_surfaces() -> None:
    root = Path(__file__).parents[1]
    routes = json.loads((root / "web/routes.json").read_text(encoding="utf-8"))
    route_ids = {route["id"] for route in routes}
    assert not {"ai", "genai", "access"} & route_ids

    features = (root / "web/js/features.js").read_text(encoding="utf-8")
    app = (root / "web/js/app.js").read_text(encoding="utf-8")
    assert "ai-studio.js" not in features
    assert "genai-studio.js" not in features
    assert "nav.ai" not in app
    assert "nav.genai" not in app
    assert "nav.access" not in app
    assert not (root / "web/js/access-studio.js").exists()

    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    plugins = project["project"]["entry-points"]["ronin.plugins.v1"]
    assert "ai_studio" not in plugins
    assert "genai_studio" not in plugins
    packages = project["tool"]["setuptools"]["packages"]["find"]
    assert "studio_genai" in packages["exclude"]
    assert "studio_ai_studio" in packages["exclude"]
    source = root / "python"
    assert not list((source / "studio_genai").glob("*.py"))
    assert not list((source / "studio_ai_studio").glob("*.py"))
    assert not (source / "studio_core/genai.py").exists()
    assert not (source / "studio_storage/genai.py").exists()
    assert not (source / "studio_storage/genai_bundle.py").exists()
    assert not list((source / "studio_storage/migrations").glob("genai_*.sql"))
    assert "genai.run" not in (source / "studio_execution/scheduler_bridge.py").read_text(
        encoding="utf-8"
    )
    assert "genai.run" not in (source / "studio_execution/scheduler_adapters.py").read_text(
        encoding="utf-8"
    )
    assert "genai.run" not in (source / "studio_worker/runtime.py").read_text(encoding="utf-8")
    assert "genai.read" not in (source / "studio_security/contracts.py").read_text(encoding="utf-8")
    openapi = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    assert not any(path.startswith("/v1/admin/security/") for path in openapi["paths"])
    assert not (source / "studio_server/oidc_admin.py").exists()
    assert not (source / "studio_server/oidc_http.py").exists()
    assert not (source / "studio_cli/oidc_serve.py").exists()
    assert not (source / "studio_security/oidc.py").exists()
    assert not (source / "studio_security/oidc_discovery.py").exists()
    assert not (source / "studio_security/rbac.py").exists()
    assert "oidc" not in (source / "studio_cli/entrypoint.py").read_text(encoding="utf-8").lower()


def test_data_engineering_query_surface_renders_routing_evidence() -> None:
    root = Path(__file__).parents[1]
    source = (root / "web/js/data-engineering-studio.js").read_text(encoding="utf-8")
    for marker in ("showQueryEvidence", "selected_engine", "routing_trace", "provider_version"):
        assert marker in source, f"query routing evidence UI missing: {marker}"


def test_environment_studio_exposes_deterministic_diff_preview() -> None:
    root = Path(__file__).parents[1]
    source = (root / "web/js/environment-studio.js").read_text(encoding="utf-8")
    for marker in ("environment-diff", "/diff`, definition", "JSON.parse"):
        assert marker in source, f"environment diff UI missing: {marker}"
