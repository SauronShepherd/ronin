from __future__ import annotations

from pathlib import Path

import pytest

from tools.installed_studio_browser_smoke import _safe_artifact_target


@pytest.mark.parametrize(
    "member",
    [
        "../outside.txt",
        "skills/../../outside.txt",
        "/absolute/file",
        "C:/temp/file",
        r"a\..\b",
        ".",
        "",
    ],
)
def test_artifact_smoke_rejects_paths_outside_extraction_root(tmp_path: Path, member: str) -> None:
    root = tmp_path / "artifact"

    with pytest.raises(RuntimeError, match="unsafe artifact member path"):
        _safe_artifact_target(root, member)


def test_artifact_smoke_resolves_safe_posix_member_under_root(tmp_path: Path) -> None:
    root = tmp_path / "artifact"

    target = _safe_artifact_target(root, "agent-skills/ronin-core/SKILL.md")

    assert target == root.resolve() / "agent-skills" / "ronin-core" / "SKILL.md"
