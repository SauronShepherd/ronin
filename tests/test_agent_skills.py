from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from studio_cli.agent_skills import (
    discover_skills,
    install_skill,
    package_skill,
    skills_payload,
    uninstall_skill,
)

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
    bytecode.mkdir(exist_ok=True)
    (bytecode / "preflight.pyc").write_bytes(b"generated")
    (root / "dist" / "ronin-core").mkdir(parents=True)

    skills = discover_skills(root)

    assert [skill.name for skill in skills] == ["ronin-core"]
    assert all("__pycache__" not in path and not path.endswith(".pyc") for path in skills[0].files)
    assert skills[0].valid


def test_install_is_idempotent_and_uninstall_removes_only_managed_files(tmp_path: Path) -> None:
    skill = discover_skills(SKILLS_ROOT)[0]
    destination = tmp_path / "agent"
    (destination / "user.txt").parent.mkdir(parents=True)
    (destination / "user.txt").write_text("keep", encoding="utf-8")

    first = install_skill(skill, destination)
    second = install_skill(skill, destination)
    assert first["files"] == second["files"]
    assert (destination / "user.txt").read_text(encoding="utf-8") == "keep"
    removed = uninstall_skill(skill.name, destination)
    assert len(removed["removed"]) == len(skill.files)
    assert (destination / "user.txt").exists()
    assert not (destination / skill.name).exists()


def test_install_refuses_to_overwrite_and_dry_run_writes_nothing(tmp_path: Path) -> None:
    skill = discover_skills(SKILLS_ROOT)[0]
    destination = tmp_path / "agent"
    first_path = destination / skill.name / skill.files[0]
    first_path.parent.mkdir(parents=True)
    first_path.write_text("user-owned", encoding="utf-8")
    try:
        install_skill(skill, destination)
    except FileExistsError:
        pass
    else:
        raise AssertionError("installer overwrote a user file")

    clean_destination = tmp_path / "dry-run"
    result = install_skill(skill, clean_destination, dry_run=True)
    assert result["dry_run"] is True
    assert not clean_destination.exists()
