"""Generate a deterministic inventory of Ronin extension surfaces.

The inventory is intentionally static: it uses the Python AST and project
metadata instead of importing application modules, so it is safe to run in a
clean environment and cannot trigger plugin startup side effects.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "route", "api_route"}
_CLI_MARKERS = {"click", "typer", "argparse", "console_scripts"}
_TEXT_MARKERS = {
    "jobs": ("Job", "job", "schedule", "worker", "task"),
    "events": ("event", "publish(", "subscribe(", "event_type"),
    "permissions": ("permission", "scope", "role", "authorize", "grant"),
    "migrations": ("migration", "alembic", "CREATE TABLE", "schema_version"),
    "stores": ("Store", "Repository", "repository", "sqlite", "postgres"),
}


@dataclass(frozen=True)
class FileInventory:
    path: str
    package: str | None
    imports: tuple[str, ...]
    classes: tuple[str, ...]
    functions: tuple[str, ...]
    routes: tuple[dict[str, str], ...]
    markers: dict[str, int]
    test: bool


def _package_for(path: Path, source_root: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(source_root.resolve())
    except ValueError:
        return None
    if not relative.parts:
        return None
    package = relative.parts[0]
    return package if package.startswith("studio_") else None


def _route_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[dict[str, str], ...]:
    routes: list[dict[str, str]] = []
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call else decorator
        if isinstance(target, ast.Attribute) and target.attr in _ROUTE_DECORATORS:
            method = target.attr.upper()
            if target.attr in {"route", "api_route"} and call and call.keywords:
                methods = next((kw.value for kw in call.keywords if kw.arg == "methods"), None)
                if isinstance(methods, (ast.List, ast.Tuple)):
                    method = ",".join(
                        item.value.upper()
                        for item in methods.elts
                        if isinstance(item, ast.Constant)
                    ) or method
            path = ""
            if call and call.args and isinstance(call.args[0], ast.Constant):
                path = str(call.args[0].value)
            routes.append({"method": method, "path": path, "function": node.name})
    return tuple(routes)


def inspect_python_file(path: Path, source_root: Path, tests_root: Path) -> FileInventory:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    imports: set[str] = set()
    classes: list[str] = []
    functions: list[str] = []
    routes: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            routes.extend(_route_info(node))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_route"
            and len(node.args) >= 3
        ):
                method = node.args[0]
                path_value = node.args[1]
                handler = node.args[2]
                if all(isinstance(value, ast.Constant) for value in (method, path_value)):
                    handler_name = (
                        handler.id if isinstance(handler, ast.Name) else ast.unparse(handler)
                    )
                    routes.append(
                        {
                            "method": str(method.value).upper(),
                            "path": str(path_value.value),
                            "function": handler_name,
                        }
                    )
    markers = {
        category: sum(source.lower().count(marker.lower()) for marker in marker_set)
        for category, marker_set in _TEXT_MARKERS.items()
    }
    return FileInventory(
        path=path.relative_to(source_root.parent).as_posix(),
        package=_package_for(path, source_root),
        imports=tuple(sorted(imports)),
        classes=tuple(sorted(classes)),
        functions=tuple(sorted(functions)),
        routes=tuple(
            sorted(routes, key=lambda item: (item["path"], item["method"], item["function"]))
        ),
        markers=markers,
        test=path.is_relative_to(tests_root),
    )


def _entry_points(pyproject: Path) -> dict[str, dict[str, str]]:
    if not pyproject.exists():
        return {}
    text = pyproject.read_text(encoding="utf-8")
    group = None
    result: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        header = re.match(r"\s*\[project\.entry-points\.\"([^\"]+)\"\]\s*$", line)
        if header:
            group = header.group(1)
            continue
        if line.startswith("["):
            group = None
            continue
        match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*=\s*\"([^\"]+)\"", line)
        if group and match:
            result.setdefault(group, {})[match.group(1)] = match.group(2)
    return result


def build_inventory(root: Path) -> dict[str, Any]:
    source_root = root / "python"
    tests_root = root / "tests"
    files = [
        inspect_python_file(path, source_root, tests_root)
        for path in sorted(root.rglob("*.py"))
        if ".venv" not in path.parts and "build" not in path.parts and "dist" not in path.parts
    ]
    package_counts = Counter(item.package for item in files if item.package)
    routes = [
        route | {"file": item.path, "package": item.package}
        for item in files
        for route in item.routes
    ]
    marker_counts = {
        category: sum(item.markers[category] for item in files)
        for category in _TEXT_MARKERS
    }
    return {
        "schema_version": 1,
        "root": root.name,
        "python_source": str(source_root.relative_to(root)).replace("\\", "/"),
        "files": [asdict(item) for item in files],
        "packages": dict(sorted(package_counts.items())),
        "routes": routes,
        "entry_points": _entry_points(root / "pyproject.toml"),
        "marker_counts": marker_counts,
        "summary": {
            "python_files": len(files),
            "test_files": sum(item.test for item in files),
            "routes": len(routes),
            "packages": len(package_counts),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    inventory = build_inventory(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
