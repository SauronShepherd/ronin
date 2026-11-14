from __future__ import annotations

from pathlib import Path


def test_github_actions_workflows_are_absent_by_policy() -> None:
    root = Path(__file__).parents[1] / ".github" / "workflows"
    workflows = tuple(root.glob("*.yml")) + tuple(root.glob("*.yaml"))
    assert not workflows
