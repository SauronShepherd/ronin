from tools.browser_audit import STUDIO_ROUTES, load_routes


def test_browser_audit_covers_every_canonical_studio_route() -> None:
    assert load_routes() == STUDIO_ROUTES
    assert len(STUDIO_ROUTES) == 27
    assert len(STUDIO_ROUTES) == len(set(STUDIO_ROUTES))
    assert STUDIO_ROUTES[0] == "home"
    assert "settings" in STUDIO_ROUTES
    assert "mlstudio" in STUDIO_ROUTES
