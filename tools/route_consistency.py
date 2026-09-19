"""Fail closed when published OpenAPI routes diverge from server registries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

try:
    from studio_server import CONTROL_PLANE_ROUTES, OIDC_ADMIN_ROUTES, SUPPORTED_ROUTES
except ModuleNotFoundError as exc:  # pragma: no cover - environment diagnostic
    if exc.name == "studio_server":
        raise SystemExit(
            "route consistency check requires the source tree on PYTHONPATH; "
            "run `PYTHONPATH=python python -m tools.route_consistency` or install the package"
        ) from exc
    raise

OPENAPI_PATH: Final = Path("api/openapi-v1.json")
_METHODS: Final = frozenset({"get", "post", "patch", "put", "delete"})


def documented_routes(path: Path = OPENAPI_PATH) -> frozenset[tuple[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("paths"), dict):
        raise ValueError("OpenAPI document must contain a paths object")
    routes: set[tuple[str, str]] = set()
    for route, item in raw["paths"].items():
        if not isinstance(route, str) or not isinstance(item, dict):
            raise ValueError("OpenAPI paths must map strings to objects")
        routes.update((method.upper(), route) for method in item if method in _METHODS)
    return frozenset(routes)


def registered_routes() -> frozenset[tuple[str, str]]:
    return frozenset(SUPPORTED_ROUTES | CONTROL_PLANE_ROUTES | OIDC_ADMIN_ROUTES)


def check(path: Path = OPENAPI_PATH) -> None:
    expected = registered_routes()
    actual = documented_routes(path)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing from OpenAPI: " + ", ".join(f"{m} {p}" for m, p in missing))
        if extra:
            details.append(
                "not registered by a server surface: " + ", ".join(f"{m} {p}" for m, p in extra)
            )
        raise SystemExit("route consistency check failed; " + "; ".join(details))
    print(f"route consistency check passed for {len(actual)} operations")


if __name__ == "__main__":
    check()
