from __future__ import annotations

import re
from pathlib import Path


def test_github_actions_are_pinned_to_full_commit_shas() -> None:
    root = Path(__file__).parents[1] / ".github" / "workflows"
    uses_pattern = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
    sha_pattern = re.compile(r"@[0-9a-f]{40}$")
    workflows = tuple(root.glob("*.yml")) + tuple(root.glob("*.yaml"))
    assert workflows
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        for reference in uses_pattern.findall(text):
            assert sha_pattern.search(reference), f"unpinned action {reference} in {workflow}"
