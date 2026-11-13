from tools.studio_surface import plugin_operations, ui_operations, unpublished_operations


def test_surface_scanner_recognizes_plugin_routes_and_normalizes_ui_paths() -> None:
    published = plugin_operations()
    invoked = ui_operations()

    assert not any("/genai/" in operation or "/ai-studio/" in operation for operation in published)
    assert "GET /v1/workspaces/{id}/catalog/assets" in invoked
    assert all("?" not in operation for operation in invoked)
    # The ternary is a computed client expression; its literal validate and
    # preview endpoints are supplied by the plugin contract scanner.
    assert not any(
        operation.startswith("POST /v1/data-engineering/pipelines/${") for operation in invoked
    )


def test_surface_gate_rejects_wrong_method_for_an_existing_path() -> None:
    published = {"GET /v1/workspaces/{id}/projects/{id}"}
    invoked = {
        "GET /v1/workspaces/workspace-a/projects/project-1",
        "POST /v1/workspaces/workspace-a/projects/project-1",
    }

    assert unpublished_operations(published, invoked) == (
        "POST /v1/workspaces/workspace-a/projects/project-1",
    )
