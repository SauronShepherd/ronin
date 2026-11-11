from pathlib import Path


def test_project_authoring_form_uses_a_stable_submit_binding_and_error_copy() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "web/js/project-journey.js").read_text(encoding="utf-8")
    assert "form.onsubmit = async (event) =>" in source
    assert "Could not create project" in source
    assert "Could not update project" in source
    assert "${error.message}" in source
    assert source.index("const editing = form.dataset.editProject;") < source.index("catch (error)")
    assert source.index("await loadProjects(workspaceId);") < source.index("document.querySelector('#project-journey-result').textContent = json(data);")
    assert "const output = document.querySelector('#project-journey-result');" in source
