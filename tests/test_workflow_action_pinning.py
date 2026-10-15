from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
_USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.MULTILINE)
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def test_github_actions_are_pinned_to_full_commit_shas() -> None:
    mutable: list[str] = []
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for reference in _USES_RE.findall(text):
            if "@" not in reference:
                mutable.append(f"{workflow.name}: {reference}")
                continue
            action, revision = reference.rsplit("@", 1)
            if not action or not _SHA_RE.fullmatch(revision):
                mutable.append(f"{workflow.name}: {reference}")

    assert not mutable, "GitHub Actions must use immutable commit SHAs:\n" + "\n".join(mutable)
