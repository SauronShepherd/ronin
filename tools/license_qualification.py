"""Generate and fail-closed validate exact third-party license evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import re
import tomllib
from pathlib import Path

_LOCKED_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^ \t\\]+)$")
_LOCKED_HASH = re.compile(r"^--hash=sha256:[0-9a-f]{64}$")
_LICENSE_FILE_NAMES = ("license", "copying", "notice", "authors", "copyright")


class LicenseQualificationError(ValueError):
    """Raised when dependency/license evidence is incomplete or inconsistent."""


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def lock_sha256(path: Path) -> str:
    """Return the SHA-256 identity of the complete committed lock file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locked_graph(path: Path) -> dict[str, str]:
    """Return the exact canonical package->version graph from a hash-locked file."""
    result: dict[str, str] = {}
    current_name: str | None = None
    current_hashes = 0
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            if current_name is not None:
                raise LicenseQualificationError(
                    f"continued locked requirement interrupted at line {line_number}: "
                    f"{current_name}"
                )
            continue

        if raw_line[:1].isspace():
            if current_name is None:
                raise LicenseQualificationError(
                    f"unsupported active lock syntax at line {line_number}"
                )
            continued = stripped.endswith(" \\")
            hash_text = stripped[:-2] if continued else stripped
            if _LOCKED_HASH.fullmatch(hash_text) is None:
                raise LicenseQualificationError(
                    f"unsupported active lock syntax at line {line_number}"
                )
            current_hashes += 1
            if not continued:
                current_name = None
                current_hashes = 0
            continue

        if current_name is not None:
            raise LicenseQualificationError(
                f"unterminated hash continuation before line {line_number}: {current_name}"
            )

        continued = raw_line.endswith(" \\")
        requirement_text = raw_line[:-2] if continued else raw_line
        match = _LOCKED_REQUIREMENT.fullmatch(requirement_text)
        if match is None:
            raise LicenseQualificationError(f"unsupported active lock syntax at line {line_number}")
        name = _canonical_name(match.group(1))
        version = match.group(2)
        if name in result:
            if result[name] != version:
                raise LicenseQualificationError(f"lock contains conflicting versions for {name}")
            raise LicenseQualificationError(f"lock contains duplicate requirement for {name}")
        if not continued:
            raise LicenseQualificationError(f"locked requirement has no sha256 hash: {name}")
        result[name] = version
        current_name = name
        current_hashes = 0

    if current_name is not None:
        if current_hashes == 0:
            raise LicenseQualificationError(
                f"locked requirement has no sha256 hash: {current_name}"
            )
        raise LicenseQualificationError(
            f"unterminated hash continuation at end of lock: {current_name}"
        )
    if not result:
        raise LicenseQualificationError("lock contains no exact requirements")
    return result


def direct_requirements(root: Path) -> set[str]:
    """Return direct dependencies represented by the resolved qualification graph."""
    direct: set[str] = set()
    for path in (root / "pyproject.toml", root / "packages/pyronin/pyproject.toml"):
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        for requirement in data.get("project", {}).get("optional-dependencies", {}).get("dev", []):
            direct.add(_canonical_name(re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0]))
        for requirement in data.get("project", {}).get("dependencies", []):
            direct.add(_canonical_name(re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0]))
    return direct


def _require_direct_coverage(graph: dict[str, str], direct: set[str]) -> None:
    missing = sorted(direct - set(graph))
    if missing:
        raise LicenseQualificationError(
            "direct project dependencies missing from requirements-dev.lock: " + ", ".join(missing)
        )


def _declared_license(dist: metadata.Distribution) -> str | None:
    expression = dist.metadata.get("License-Expression")
    if expression and expression.strip():
        return expression.strip()
    value = dist.metadata.get("License")
    if value and value.strip() and value.strip().upper() != "UNKNOWN":
        return value.strip()
    classifiers = [
        item.removeprefix("License :: ").strip()
        for item in (dist.metadata.get_all("Classifier") or [])
        if item.startswith("License :: ")
    ]
    return " | ".join(classifiers) or None


def _source(dist: metadata.Distribution) -> str | None:
    for value in dist.metadata.get_all("Project-URL") or []:
        label, separator, url = value.partition(",")
        if separator and label.strip().casefold() in {
            "source",
            "source code",
            "repository",
            "homepage",
        }:
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


def _locked_distributions(graph: dict[str, str]) -> dict[str, metadata.Distribution]:
    installed: dict[str, metadata.Distribution] = {}
    for dist in metadata.distributions():
        raw_name = dist.metadata.get("Name")
        if not raw_name or not raw_name.strip():
            continue
        name = _canonical_name(raw_name)
        if name not in graph:
            continue
        if name in installed:
            raise LicenseQualificationError(f"multiple installed distributions found for {name}")
        installed[name] = dist
    return installed


def generate_inventory(root: Path) -> dict[str, object]:
    """Generate metadata evidence for exactly the committed locked graph."""
    lock_path = root / "requirements-dev.lock"
    graph = locked_graph(lock_path)
    direct = direct_requirements(root)
    _require_direct_coverage(graph, direct)
    installed = _locked_distributions(graph)
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
    return {
        "schema_version": 1,
        "lock_file": "requirements-dev.lock",
        "lock_sha256": lock_sha256(lock_path),
        "packages": entries,
    }


def qualify(
    inventory: object,
    policy: object,
    graph: dict[str, str],
    *,
    expected_lock_sha256: str,
    expected_direct: set[str],
) -> None:
    """Fail unless inventory exactly matches the lock and every package is reviewed."""
    if not isinstance(inventory, dict) or inventory.get("schema_version") != 1:
        raise LicenseQualificationError("inventory schema_version must be 1")
    if inventory.get("lock_file") != "requirements-dev.lock":
        raise LicenseQualificationError("inventory lock_file must be requirements-dev.lock")
    if inventory.get("lock_sha256") != expected_lock_sha256:
        raise LicenseQualificationError("inventory lock_sha256 does not match requirements-dev.lock")
    _require_direct_coverage(graph, expected_direct)
    packages = inventory.get("packages")
    if not isinstance(packages, list):
        raise LicenseQualificationError("inventory packages must be a list")
    seen: dict[str, str] = {}
    for entry in packages:
        if not isinstance(entry, dict):
            raise LicenseQualificationError("inventory entry must be an object")
        name = entry.get("package")
        version = entry.get("version")
        is_direct = entry.get("direct")
        source = entry.get("source")
        declared = entry.get("declared_license")
        files = entry.get("license_files")
        if not isinstance(name, str) or not isinstance(version, str):
            raise LicenseQualificationError("inventory package/version must be strings")
        canonical = _canonical_name(name)
        if canonical in seen:
            raise LicenseQualificationError(f"duplicate inventory package: {canonical}")
        seen[canonical] = version
        if not isinstance(is_direct, bool):
            raise LicenseQualificationError(f"direct classification must be boolean: {canonical}=={version}")
        if is_direct != (canonical in expected_direct):
            raise LicenseQualificationError(
                f"direct classification does not match project metadata: {canonical}=={version}"
            )
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
    notice_rationale = policy.get("project_notice_rationale")
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
        if review.get("attribution_required") not in {True, False}:
            raise LicenseQualificationError(f"attribution_required must be reviewed: {key}")
        rationale = review.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise LicenseQualificationError(f"review rationale is required: {key}")
    if notice_decision not in {"required", "not_required"}:
        raise LicenseQualificationError("project NOTICE decision is unresolved")
    if not isinstance(notice_rationale, str) or not notice_rationale.strip():
        raise LicenseQualificationError("project NOTICE rationale is required")


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
    lock_path = root / "requirements-dev.lock"
    graph = locked_graph(lock_path)
    qualify(
        _load_json(root / args.inventory),
        _load_json(root / args.policy),
        graph,
        expected_lock_sha256=lock_sha256(lock_path),
        expected_direct=direct_requirements(root),
    )
    print(f"license qualification: ok ({len(graph)} locked distributions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
