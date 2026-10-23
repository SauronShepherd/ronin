"""Discovery, validation, and packaging for Ronin coding-agent skills."""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
_FIELD = re.compile(r"(?m)^([A-Za-z][A-Za-z0-9_-]*):\s*(.+?)\s*$")
_INTERFACE_FIELD = re.compile(r"(?m)^\s{2}([A-Za-z][A-Za-z0-9_-]*):\s*[\"']?(.+?)[\"']?\s*$")


@dataclass(frozen=True)
class SkillInspection:
    """Stable summary of one agent skill bundle."""

    name: str
    path: Path
    display_name: str
    description: str
    files: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "display_name": self.display_name,
            "description": self.description,
            "files": list(self.files),
            "errors": list(self.errors),
            "valid": self.valid,
        }


def default_skill_root() -> Path:
    """Return the repository skill root, with an environment override."""

    override = os.environ.get("RONIN_AGENT_SKILLS_DIR")
    if override:
        return Path(override).expanduser()
    repository_root = Path(__file__).resolve().parents[2]
    candidate = repository_root / "agent-skills"
    if candidate.is_dir():
        return candidate
    installed = Path(sys.prefix) / "share" / "ronin" / "agent-skills"
    if installed.is_dir():
        return installed
    return Path.cwd() / "agent-skills"


def _read(path: Path, label: str) -> tuple[str | None, str | None]:
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError as exc:
        return None, f"{label}: {exc}"


def _frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    match = _FRONTMATTER.match(text)
    if match is None:
        return {}, ["SKILL.md must start with YAML frontmatter"]
    fields = {key: value.strip().strip("\"'") for key, value in _FIELD.findall(match.group("body"))}
    errors = [field for field in ("name", "description") if not fields.get(field)]
    return fields, [f"SKILL.md frontmatter is missing {field}" for field in errors]


def _interface(text: str) -> tuple[str, list[str]]:
    fields = {key: value.strip().strip("\"'") for key, value in _INTERFACE_FIELD.findall(text)}
    errors = [field for field in ("display_name", "short_description") if not fields.get(field)]
    return fields.get("display_name", ""), [
        f"openai.yaml interface is missing {field}" for field in errors
    ]


def inspect_skill(path: Path) -> SkillInspection:
    """Inspect one skill without executing any bundled code."""

    errors: list[str] = []
    skill_path = path.resolve()
    name = skill_path.name
    skill_text, read_error = _read(skill_path / "SKILL.md", "cannot read SKILL.md")
    if read_error:
        errors.append(read_error)
        skill_text = ""
    skill_text = skill_text or ""
    fields, frontmatter_errors = _frontmatter(skill_text)
    errors.extend(frontmatter_errors)
    if fields.get("name") and fields["name"] != name:
        errors.append(f"SKILL.md name {fields['name']!r} does not match directory {name!r}")

    agent_text, read_error = _read(
        skill_path / "agents" / "openai.yaml", "cannot read agents/openai.yaml"
    )
    if read_error:
        errors.append(read_error)
        agent_text = ""
    agent_text = agent_text or ""
    display_name, interface_errors = _interface(agent_text)
    errors.extend(interface_errors)

    files: list[str] = []
    if skill_path.is_dir():
        for item in sorted(skill_path.rglob("*")):
            if item.is_symlink():
                errors.append(f"symlinks are not allowed: {item.relative_to(skill_path)}")
                continue
            if item.is_file():
                relative = item.relative_to(skill_path).as_posix()
                files.append(relative)
                if item.suffix == ".py":
                    source, syntax_error = _read(item, relative)
                    if syntax_error:
                        errors.append(syntax_error)
                    else:
                        try:
                            ast.parse(source or "", filename=relative)
                        except SyntaxError as exc:
                            errors.append(
                                f"{relative}: Python syntax error: {exc.msg} at line {exc.lineno}"
                            )
    else:
        errors.append(f"skill directory does not exist: {skill_path}")

    return SkillInspection(
        name=name,
        path=skill_path,
        display_name=display_name,
        description=fields.get("description", ""),
        files=tuple(files),
        errors=tuple(dict.fromkeys(errors)),
    )


def discover_skills(root: Path | None = None) -> tuple[SkillInspection, ...]:
    """Discover immediate child skill directories in deterministic order."""

    skill_root = (root or default_skill_root()).expanduser().resolve()
    if not skill_root.is_dir():
        return ()
    return tuple(
        inspect_skill(path)
        for path in sorted(skill_root.iterdir(), key=lambda item: item.name)
        if path.is_dir() and not path.name.startswith(".")
    )


def package_skill(skill: SkillInspection, output_root: Path) -> Path:
    """Write one deterministic skill ZIP and return its path."""

    if not skill.valid:
        raise ValueError(f"cannot package invalid skill {skill.name}: {'; '.join(skill.errors)}")
    destination = output_root / skill.name / "skill.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for relative in skill.files:
            source = skill.path / relative
            info = zipfile.ZipInfo(f"{skill.name}/{relative}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source.read_bytes())
    return destination


def skills_payload(skills: tuple[SkillInspection, ...]) -> dict[str, object]:
    """Build the machine-readable skills report."""

    return {
        "schema": "ronin.agent-skills/v1",
        "count": len(skills),
        "valid": all(skill.valid for skill in skills),
        "skills": [skill.to_payload() for skill in skills],
    }


def render_skills_json(skills: tuple[SkillInspection, ...]) -> str:
    return json.dumps(skills_payload(skills), sort_keys=True, separators=(",", ":"))
