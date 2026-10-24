from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from studio_cli.agent_skills import discover_skills, package_skill, skills_payload

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "agent-skills"


def test_repository_agent_skills_are_valid_and_deterministic() -> None:
    skills = discover_skills(SKILLS_ROOT)

    assert [skill.name for skill in skills] == [
        "ronin-core",
        "ronin-data-engineering",
        "ronin-machine-learning",
    ]
    assert all(skill.valid for skill in skills), skills_payload(skills)
    assert all("SKILL.md" in skill.files for skill in skills)
    assert all("agents/openai.yaml" in skill.files for skill in skills)


def test_agent_skill_package_contains_only_the_skill_tree(tmp_path: Path) -> None:
    skill = discover_skills(SKILLS_ROOT)[0]

    first = package_skill(skill, tmp_path / "one")
    first_bytes = first.read_bytes()
    second = package_skill(skill, tmp_path / "two")

    assert first_bytes == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert names == [f"{skill.name}/{relative}" for relative in skill.files]
        assert all(not name.startswith("/") for name in names)


def test_discovery_ignores_generated_output_and_bytecode(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    shutil.copytree(SKILLS_ROOT / "ronin-core", root / "ronin-core")
    bytecode = root / "ronin-core" / "scripts" / "__pycache__"
    bytecode.mkdir()
    (bytecode / "preflight.pyc").write_bytes(b"generated")
    (root / "dist" / "ronin-core").mkdir(parents=True)

    skills = discover_skills(root)

    assert [skill.name for skill in skills] == ["ronin-core"]
    assert all("__pycache__" not in path and not path.endswith(".pyc") for path in skills[0].files)
    assert skills[0].valid
