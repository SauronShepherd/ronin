from pathlib import Path

import pytest

from tools.route_consistency import check, documented_routes, registered_routes


def test_published_openapi_matches_all_registered_routes() -> None:
    check()
    assert documented_routes() == registered_routes()


def test_route_gate_fails_closed_for_an_unpublished_operation(tmp_path: Path) -> None:
    source = Path("api/openapi-v1.json").read_text(encoding="utf-8")
    path = tmp_path / "openapi.json"
    path.write_text(source.replace('"/v1/sql"', '"/v1/hidden"', 1), encoding="utf-8")
    with pytest.raises(SystemExit, match="route consistency check failed"):
        check(path)
