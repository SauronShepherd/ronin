"""Load and validate packaged Performance Studio resources."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any


def _load(name: str) -> dict[str, Any]:
    value = json.loads(files("ronin_plugin_performance").joinpath(name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def load_ui_manifest() -> dict[str, Any]:
    manifest = _load("ui_manifest.json")
    if manifest.get("ui_api") != "1.0" or manifest.get("product") != "Performance Studio":
        raise ValueError("invalid Performance Studio UI manifest")
    return manifest


def load_config_schema() -> dict[str, Any]:
    schema = _load("config_schema.json")
    if schema.get("$id") != "ronin.performance/config-v1" or schema.get("type") != "object":
        raise ValueError("invalid Performance Studio config schema")
    return schema
