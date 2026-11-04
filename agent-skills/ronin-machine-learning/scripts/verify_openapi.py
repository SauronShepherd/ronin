#!/usr/bin/env python3
"""Validate that an OpenAPI document contains the Ronin ML Studio routes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED_PREFIXES = ("/v1/ml-studio",)
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}


def _emit(result: dict[str, Any], json_output: bool) -> None:
    print(json.dumps(result, sort_keys=True) if json_output else result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openapi", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        document = json.loads(Path(args.openapi).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        result = {"ok": False, "error": "invalid_openapi", "detail": str(error)}
        _emit(result, args.json)
        return 2

    paths = document.get("paths") if isinstance(document, dict) else None
    if not isinstance(paths, dict):
        _emit({"ok": False, "error": "missing_paths"}, args.json)
        return 2

    matched = sorted(path for path in paths if path.startswith(REQUIRED_PREFIXES))
    if any(not isinstance(paths[path], dict) for path in matched):
        _emit({"ok": False, "error": "invalid_path_item"}, args.json)
        return 2

    operation_count = sum(
        method.lower() in HTTP_METHODS for path in matched for method in paths[path]
    )
    result = {
        "ok": bool(matched),
        "ml_paths": len(matched),
        "ml_operations": operation_count,
        "sample": matched[:10],
    }
    _emit(result, args.json)
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
