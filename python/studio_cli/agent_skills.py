"""Discovery, validation, and packaging for Ronin coding-agent skills."""

from __future__ import annotations

import ast
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from hashlib import sha256
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
            if "__pycache__" in item.parts or item.suffix in {".pyc", ".pyo"}:
                continue
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
        if path.is_dir() and not path.name.startswith(".") and path.name != "dist"
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


_INSTALL_MANIFEST = ".ronin/managed-agent-skills.json"


def _managed_manifest(destination: Path) -> Path:
    return destination / _INSTALL_MANIFEST


def _safe_destination(destination: Path, relative: str) -> Path:
    """Resolve a managed path while rejecting traversal and symlink parents."""

    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts or "." in relative_path.parts:
        raise ValueError(f"skill path is not confined to destination: {relative}")
    current = destination
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"skill path contains a symlink: {relative}")
    return current


def _file_digest(path: Path) -> str:
    digest = sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def install_skill(
    skill: SkillInspection,
    destination: Path,
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    """Install a validated skill without overwriting user files.

    Existing identical files are idempotent. Differing files fail closed; the
    manifest records only files written by this installer, enabling safe
    uninstall without touching unrelated user content.
    """

    if not skill.valid:
        raise ValueError(f"cannot install invalid skill {skill.name}: {'; '.join(skill.errors)}")
    target = destination.expanduser().resolve()
    entries: list[dict[str, str]] = []
    for relative in skill.files:
        source = skill.path / relative
        target_file = _safe_destination(target, f"{skill.name}/{relative}")
        digest = _file_digest(source)
        if target_file.exists() and (
            not target_file.is_file() or _file_digest(target_file) != digest
        ):
            raise FileExistsError(f"refusing to overwrite existing file: {target_file}")
        entries.append({"path": f"{skill.name}/{relative}", "sha256": digest})
    manifest_path = _managed_manifest(target)
    manifest = {"schema": "ronin.agent-skills-install/v1", "skills": {}}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.setdefault("skills", {})[skill.name] = {"files": entries}
    if not dry_run:
        for relative in skill.files:
            source = skill.path / relative
            target_file = _safe_destination(target, f"{skill.name}/{relative}")
            target_file.parent.mkdir(parents=True, exist_ok=True)
            if not target_file.exists():
                target_file.write_bytes(source.read_bytes())
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return {"skill": skill.name, "destination": str(target), "files": entries, "dry_run": dry_run}


def uninstall_skill(name: str, destination: Path, *, dry_run: bool = False) -> dict[str, object]:
    """Remove only files previously managed by :func:`install_skill`."""

    target = destination.expanduser().resolve()
    manifest_path = _managed_manifest(target)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"managed skill manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest.get("skills", {}).get(name)
    if not isinstance(record, dict):
        raise KeyError(f"skill is not managed: {name}")
    removed: list[str] = []
    for item in record.get("files", []):
        relative = item["path"]
        path = _safe_destination(target, relative)
        if path.is_file() and _file_digest(path) == item["sha256"]:
            removed.append(relative)
            if not dry_run:
                path.unlink()
    if not dry_run:
        manifest["skills"].pop(name, None)
        if manifest["skills"]:
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        else:
            manifest_path.unlink()
        skill_root = target / name
        for directory in sorted(
            (path for path in skill_root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            if not any(directory.iterdir()):
                directory.rmdir()
        if skill_root.is_dir() and not any(skill_root.iterdir()):
            skill_root.rmdir()
    return {"skill": name, "destination": str(target), "removed": removed, "dry_run": dry_run}
