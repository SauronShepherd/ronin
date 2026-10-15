import json
from pathlib import Path

from studio_migration import MIGRATION_ROUTES


def test_migration_routes_are_documented_in_openapi() -> None:
    document = json.loads((Path(__file__).parents[1] / "api" / "openapi-v1.json").read_text())
    paths = document["paths"]
    assert all(route in paths for _, route in MIGRATION_ROUTES)
    assert {"get", "post"} <= set(
        paths["/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions"]
    )
    assert (
        "get"
        in paths[
            "/v1/workspaces/{workspace_id}/projects/{project_id}/migration/sessions/{session_id}"
        ]
    )
