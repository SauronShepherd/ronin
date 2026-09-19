"""Check that the Studio's declared API surface remains contract-backed."""

from __future__ import annotations

import json
import re
from pathlib import Path

OPENAPI = Path("api/openapi-v1.json")
WEB = Path("web/js")
MAP = Path("docs/ui/SCREEN_API_MAP.md")
METHODS = {"get", "post", "put", "patch", "delete"}


def published_operations() -> set[str]:
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    return {
        f"{method.upper()} {path}"
        for path, item in document["paths"].items()
        for method in item
        if method in METHODS
    }


def ui_operations() -> set[str]:
    source = "\n".join(path.read_text(encoding="utf-8") for path in WEB.rglob("*.js"))
    raw = re.findall(r"\b(get|post|put|patch|del)\(\s*[`'\"](/v1/[^`'\"? ]+)", source)
    operations: set[str] = set()
    for method, path in raw:
        normalized = re.sub(r"\$\{[^}]+\}", "{id}", path)
        operations.add(f"{'DELETE' if method == 'del' else method.upper()} {normalized}")
    return operations


def declared_map() -> str:
    return MAP.read_text(encoding="utf-8")


def check() -> None:
    operations = published_operations()
    invoked = ui_operations()
    route_paths = {route.split(" ", 1)[1] for route in operations}

    def matches(path: str, route: str) -> bool:
        left, right = path.strip("/").split("/"), route.strip("/").split("/")
        return len(left) == len(right) and all(
            a == b or b.startswith("{") for a, b in zip(left, right, strict=True)
        )

    unknown = sorted(
        path
        for path in invoked
        if not any(matches(path.split(" ", 1)[1], route) for route in route_paths)
    )
    if not MAP.exists():
        raise SystemExit(f"missing Studio surface declaration: {MAP}")
    if unknown:
        raise SystemExit("Studio invokes unpublished routes: " + ", ".join(unknown))
    required = ("/v1/jobs", "/v1/workspaces", "/v1/sql")
    if not all(route in declared_map() for route in required):
        raise SystemExit("SCREEN_API_MAP.md is missing a required first-slice operation")
    matched = {
        operation
        for operation in invoked
        if any(
            operation.split(" ", 1)[0] == published.split(" ", 1)[0]
            and matches(operation.split(" ", 1)[1], published.split(" ", 1)[1])
            for published in operations
        )
    }
    print(
        f"Studio surface check passed: {len(matched)}/{len(operations)} "
        "published operations matched"
    )
    if len(matched) < 24:
        raise SystemExit(f"Studio surface ratchet below target: {len(matched)}/26")


if __name__ == "__main__":
    check()
