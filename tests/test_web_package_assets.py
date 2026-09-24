from __future__ import annotations

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
