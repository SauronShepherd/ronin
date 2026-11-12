from pathlib import Path


def test_connection_submit_waits_for_active_route_render() -> None:
    app = Path("web/js/app.js").read_text(encoding="utf-8")
    assert "document.addEventListener('submit',async event=>" in app
    assert "await render();if(state.route==='workspaces')await loadWorkspaceJourney()" in app
