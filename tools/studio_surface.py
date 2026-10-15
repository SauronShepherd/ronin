"""Check that the Studio's declared API surface remains contract-backed."""

from __future__ import annotations

import json
import re
from pathlib import Path

OPENAPI = Path("api/openapi-v1.json")
WEB = Path("web/js")
MAP = Path("docs/ui/SCREEN_API_MAP.md")
METHODS = {"get", "post", "put", "patch", "delete"}
PLUGIN_ROUTE = re.compile(
    r'context\.contributions\.add_route\(\s*"(GET|POST|PUT|PATCH|DELETE)"\s*,\s*"(/v1/[^"?]+)"',
    re.MULTILINE,
)
PLUGIN_TUPLE_ROUTE = re.compile(
    r'\(\s*"(GET|POST|PUT|PATCH|DELETE)"\s*,\s*"(/v1/[^"?]+)"',
    re.MULTILINE,
)
UI_TEMPLATE = re.compile(r"\b(get|post|put|patch|del)\(\s*`([^`]+)`")
UI_QUOTED = re.compile(r"\b(get|post|put|patch|del)\(\s*['\"](/v1/[^'\"]+)")


def published_operations() -> set[str]:
    document = json.loads(OPENAPI.read_text(encoding="utf-8"))
    return {
        f"{method.upper()} {path}"
        for path, item in document["paths"].items()
        for method in item
        if method in METHODS
    }


def plugin_operations() -> set[str]:
    """Include routes published through the explicit plugin contribution port."""

    operations: set[str] = set()
    for path in Path("python").glob("studio_*/plugin.py"):
        source = path.read_text(encoding="utf-8")
        operations.update(f"{method} {route}" for method, route in PLUGIN_ROUTE.findall(source))
        operations.update(
            f"{method} {route}" for method, route in PLUGIN_TUPLE_ROUTE.findall(source)
        )
    return operations


def ui_operations() -> set[str]:
    source = "\n".join(path.read_text(encoding="utf-8") for path in WEB.rglob("*.js"))
    raw = UI_TEMPLATE.findall(source) + UI_QUOTED.findall(source)
    operations: set[str] = set()
    for method, path in raw:
        # Only the pathname is part of the published operation. Query
        # parameters are assembled inline in several Studio modules.
        path = path.split("?", 1)[0]
        # Ignore computed route expressions that the static scanner cannot
        # safely recover (the corresponding literal routes are declared by
        # the server/plugin contract and are checked separately).
        if not path.startswith("/v1/") or any(char.isspace() for char in path):
            continue
        normalized = re.sub(r"\$\{[^}]+\}", "{id}", path)
        # Query-string expressions are captured by the deliberately small
        # static scanner too. They are not path segments and must not make a
        # valid route appear unpublished (for example ``assets${suffix}``).
        normalized = re.sub(r"(?<=\})\{id\}$", "", normalized)
        normalized = re.sub(r"(?<=[A-Za-z0-9])\{id\}$", "", normalized)
        operations.add(f"{'DELETE' if method == 'del' else method.upper()} {normalized}")
    return operations


def declared_map() -> str:
    return MAP.read_text(encoding="utf-8")


def check() -> None:
    operations = published_operations() | plugin_operations()
    invoked = ui_operations()
    route_paths = {route.split(" ", 1)[1] for route in operations}

    def matches(path: str, route: str) -> bool:
        left, right = path.strip("/").split("/"), route.strip("/").split("/")
        return len(left) == len(right) and all(
            a == b or a.startswith("{") or b.startswith("{")
            for a, b in zip(left, right, strict=True)
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
