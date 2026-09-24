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
