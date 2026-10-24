from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.installed_studio_browser_smoke import _safe_artifact_target


def test_artifact_smoke_starts_without_source_tree_pythonpath(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "tools/installed_studio_browser_smoke.py"
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    result = subprocess.run(  # noqa: S603 - fixed interpreter and checked-in script path
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "artifact" in result.stdout


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
