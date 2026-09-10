"""Generate and fail-closed validate exact third-party license evidence."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import re
import tomllib
from pathlib import Path

_LOCKED_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^ \\]+)")
_LICENSE_FILE_NAMES = ("license", "copying", "notice", "authors")


class LicenseQualificationError(ValueError):
    """Raised when dependency/license evidence is incomplete or inconsistent."""


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def locked_graph(path: Path) -> dict[str, str]:
    """Return the exact canonical package->version graph from a pip-compile lock."""
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = _LOCKED_REQUIREMENT.match(raw_line)
        if match is None:
            continue
        name = _canonical_name(match.group(1))
        version = match.group(2)
        previous = result.setdefault(name, version)
        if previous != version:
            raise LicenseQualificationError(f"lock contains conflicting versions for {name}")
    if not result:
        raise LicenseQualificationError("lock contains no exact requirements")
    return result


def direct_requirements(root: Path) -> set[str]:
    """Return direct root dev/build and pyronin build dependency names."""
    direct: set[str] = set()
    for path in (root / "pyproject.toml", root / "packages/pyronin/pyproject.toml"):
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        for requirement in data.get("build-system", {}).get("requires", []):
            direct.add(_canonical_name(re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0]))
        for requirement in data.get("project", {}).get("optional-dependencies", {}).get("dev", []):
            direct.add(_canonical_name(re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0]))
        for requirement in data.get("project", {}).get("dependencies", []):
            direct.add(_canonical_name(re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0]))
    return direct


def _declared_license(dist: metadata.Distribution) -> str | None:
    expression = dist.metadata.get("License-Expression")
    if expression and expression.strip():
        return expression.strip()
    value = dist.metadata.get("License")
    if value and value.strip() and value.strip().upper() != "UNKNOWN":
        return value.strip()
    classifiers = [
        item.removeprefix("License :: ").strip()
        for item in dist.metadata.get_all("Classifier", [])
        if item.startswith("License :: ")
    ]
    return " | ".join(classifiers) or None


def _source(dist: metadata.Distribution) -> str | None:
    project_urls = dist.metadata.get_all("Project-URL", [])
    for value in project_urls:
        label, separator, url = value.partition(",")
        if separator and label.strip().casefold() in {"source", "repository", "homepage"}:
            return url.strip() or None
    home_page = dist.metadata.get("Home-page")
    return home_page.strip() if home_page and home_page.strip() else None


def _license_files(dist: metadata.Distribution) -> list[str]:
    result: list[str] = []
    for file in dist.files or ():
        path = str(file)
        name = Path(path).name.casefold()
        if any(name.startswith(prefix) for prefix in _LICENSE_FILE_NAMES):
            result.append(path)
    return sorted(set(result))


def generate_inventory(root: Path) -> dict[str, object]:
    """Generate metadata evidence for exactly the committed locked graph."""
    graph = locked_graph(root / "requirements-dev.lock")
    direct = direct_requirements(root)
    installed = {_canonical_name(dist.metadata["Name"]): dist for dist in metadata.distributions()}
    entries: list[dict[str, object]] = []
    for name, version in sorted(graph.items()):
        dist = installed.get(name)
        if dist is None:
            raise LicenseQualificationError(f"locked distribution is not installed: {name}=={version}")
        if dist.version != version:
            raise LicenseQualificationError(
                f"installed version differs from lock: {name} expected {version}, got {dist.version}"
            )
        entries.append(
            {
                "package": name,
                "version": version,
                "direct": name in direct,
                "source": _source(dist),
                "declared_license": _declared_license(dist),
                "license_files": _license_files(dist),
            }
        )
    return {"schema_version": 1, "lock_file": "requirements-dev.lock", "packages": entries}


def qualify(inventory: object, policy: object, graph: dict[str, str]) -> None:
    """Fail unless inventory exactly matches the lock and every package is reviewed."""
    if not isinstance(inventory, dict) or inventory.get("schema_version") != 1:
        raise LicenseQualificationError("inventory schema_version must be 1")
    if inventory.get("lock_file") != "requirements-dev.lock":
        raise LicenseQualificationError("inventory lock_file must be requirements-dev.lock")
    packages = inventory.get("packages")
    if not isinstance(packages, list):
        raise LicenseQualificationError("inventory packages must be a list")
    seen: dict[str, str] = {}
    for entry in packages:
        if not isinstance(entry, dict):
            raise LicenseQualificationError("inventory entry must be an object")
        name = entry.get("package")
        version = entry.get("version")
        source = entry.get("source")
        declared = entry.get("declared_license")
        files = entry.get("license_files")
        if not isinstance(name, str) or not isinstance(version, str):
            raise LicenseQualificationError("inventory package/version must be strings")
        canonical = _canonical_name(name)
        if canonical in seen:
            raise LicenseQualificationError(f"duplicate inventory package: {canonical}")
        seen[canonical] = version
        if not isinstance(source, str) or not source.strip():
            raise LicenseQualificationError(f"missing distribution source: {canonical}=={version}")
        if not isinstance(declared, str) or not declared.strip():
            raise LicenseQualificationError(f"missing declared license: {canonical}=={version}")
        if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
            raise LicenseQualificationError(f"invalid license_files: {canonical}=={version}")
    if seen != graph:
        raise LicenseQualificationError("inventory does not exactly match the locked dependency graph")

    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise LicenseQualificationError("policy schema_version must be 1")
    reviews = policy.get("reviews")
    notice_decision = policy.get("project_notice")
    if not isinstance(reviews, dict):
        raise LicenseQualificationError("policy reviews must be an object")
    expected_review_keys = {f"{name}=={version}" for name, version in graph.items()}
    if set(reviews) != expected_review_keys:
        raise LicenseQualificationError("policy review keys must exactly match the locked graph")
    for key in sorted(expected_review_keys):
        review = reviews[key]
        if not isinstance(review, dict) or review.get("decision") not in {"allow", "deny"}:
            raise LicenseQualificationError(f"missing reviewed license decision: {key}")
        if review.get("decision") != "allow":
            raise LicenseQualificationError(f"dependency license is not approved: {key}")
        if review.get("notice_required") not in {True, False}:
            raise LicenseQualificationError(f"notice_required must be reviewed: {key}")
        rationale = review.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise LicenseQualificationError(f"review rationale is required: {key}")
    if notice_decision not in {"required", "not_required"}:
        raise LicenseQualificationError("project NOTICE decision is unresolved")


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LicenseQualificationError(f"cannot read valid JSON: {path}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--write-inventory", type=Path)
    parser.add_argument("--inventory", type=Path, default=Path("third_party/licenses-v1.json"))
    parser.add_argument("--policy", type=Path, default=Path("third_party/license-policy-v1.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.write_inventory is not None:
        payload = generate_inventory(root)
        args.write_inventory.parent.mkdir(parents=True, exist_ok=True)
        args.write_inventory.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return 0
    graph = locked_graph(root / "requirements-dev.lock")
    qualify(_load_json(root / args.inventory), _load_json(root / args.policy), graph)
    print(f"license qualification: ok ({len(graph)} locked distributions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
