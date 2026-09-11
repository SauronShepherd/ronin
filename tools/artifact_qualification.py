"""Build and qualify immutable Python release artifacts outside the checkout."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIST_INFO_RECORD = re.compile(r"^[^/]+-[^/]+\.dist-info/RECORD$")


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


class ArtifactQualificationError(ValueError):
    """Raised when artifact identity or installed-origin qualification fails."""


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of exact file bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _single_artifact(outdir: Path, suffix: str) -> Path:
    matches = sorted(
        path
        for path in outdir.iterdir()
        if path.is_file() and path.name.endswith(suffix)
    )
    if len(matches) != 1:
        raise ArtifactQualificationError(
            f"expected exactly one {suffix} artifact in {outdir}, found {len(matches)}"
        )
    return matches[0]


def _wheel_metadata(wheel: Path) -> tuple[str, str, str]:
    """Return canonical distribution name, version, and SHA-256 of exact RECORD bytes."""
    with zipfile.ZipFile(wheel) as archive:
        record_names = [name for name in archive.namelist() if _DIST_INFO_RECORD.fullmatch(name)]
        if len(record_names) != 1:
            raise ArtifactQualificationError(
                f"expected exactly one wheel RECORD, found {record_names}"
            )
        record_name = record_names[0]
        record_bytes = archive.read(record_name)
        try:
            rows = list(csv.reader(record_bytes.decode("utf-8").splitlines()))
        except UnicodeDecodeError as exc:
            raise ArtifactQualificationError("wheel RECORD is not UTF-8") from exc
        if not rows or any(len(row) != 3 for row in rows):
            raise ArtifactQualificationError("wheel RECORD is malformed")
        dist_info = PurePosixPath(record_name).parts[0]
        stem = dist_info.removesuffix(".dist-info")
        if "-" not in stem:
            raise ArtifactQualificationError("wheel dist-info name does not encode a version")
        raw_name, version = stem.rsplit("-", 1)
        if not raw_name or not version:
            raise ArtifactQualificationError("wheel dist-info name is malformed")
    return _canonical_name(raw_name), version, hashlib.sha256(record_bytes).hexdigest()


def artifact_record(wheel: Path, sdist: Path) -> dict[str, object]:
    """Create deterministic identity evidence for one wheel/sdist candidate pair."""
    name, version, record_sha256 = _wheel_metadata(wheel)
    return {
        "schema": "ronin.python-artifact-candidate/v1",
        "package": name,
        "version": version,
        "wheel": {"filename": wheel.name, "sha256": sha256_file(wheel)},
        "sdist": {"filename": sdist.name, "sha256": sha256_file(sdist)},
        "wheel_record_sha256": record_sha256,
    }


def assert_installed_origin(
    module_file: Path,
    *,
    checkout: Path,
    site_packages: Path,
) -> Path:
    """Fail unless an imported module resolves under isolated site-packages and outside checkout."""
    resolved_module = module_file.resolve(strict=True)
    resolved_checkout = checkout.resolve(strict=True)
    resolved_site = site_packages.resolve(strict=True)
    if resolved_module.is_relative_to(resolved_checkout):
        raise ArtifactQualificationError(
            f"installed import leaked to checkout source: {resolved_module}"
        )
    if not resolved_module.is_relative_to(resolved_site):
        raise ArtifactQualificationError(
            f"installed import is outside isolated site-packages: {resolved_module}"
        )
    return resolved_module


def _record_qualification(
    record: dict[str, object],
    *,
    imported_module: Path,
    site_packages: Path,
) -> dict[str, object]:
    """Attach machine-independent qualification facts to candidate identity evidence."""
    resolved_site = site_packages.resolve(strict=True)
    try:
        relative_module = imported_module.relative_to(resolved_site)
    except ValueError as exc:
        raise ArtifactQualificationError(
            "qualified import is outside isolated site-packages"
        ) from exc
    result = dict(record)
    result["qualification"] = {
        "contract_tests": "passed",
        "import_origin": "isolated-site-packages",
        "module_path": relative_module.as_posix(),
    }
    return result


def bind_license_evidence(
    *,
    package: str,
    version: str,
    artifact_sha256: str,
    inventory: object,
) -> dict[str, str]:
    """Bind one immutable selected artifact digest to exact installed license evidence."""
    if _SHA256.fullmatch(artifact_sha256) is None:
        raise ArtifactQualificationError("artifact_sha256 must be a lowercase SHA-256 digest")
    if not isinstance(inventory, dict) or inventory.get("schema_version") != 1:
        raise ArtifactQualificationError("license inventory schema_version must be 1")
    entries = inventory.get("packages")
    if not isinstance(entries, list):
        raise ArtifactQualificationError("license inventory packages must be a list")
    matches: list[dict[str, object]] = []
    canonical_package = _canonical_name(package)
    for entry in entries:
        if not isinstance(entry, dict):
            raise ArtifactQualificationError("license inventory entry must be an object")
        raw_package = entry.get("package")
        raw_version = entry.get("version")
        if isinstance(raw_package, str) and isinstance(raw_version, str):
            if _canonical_name(raw_package) == canonical_package and raw_version == version:
                matches.append(entry)
    if len(matches) != 1:
        raise ArtifactQualificationError(
            "expected one license inventory entry for "
            f"{canonical_package}=={version}, found {len(matches)}"
        )
    evidence = matches[0].get("evidence_sha256")
    if not isinstance(evidence, str) or _SHA256.fullmatch(evidence) is None:
        raise ArtifactQualificationError("license inventory entry has invalid evidence_sha256")
    return {
        "package": canonical_package,
        "version": version,
        "artifact_sha256": artifact_sha256,
        "license_evidence_sha256": evidence,
    }


def _run(argv: list[str], *, cwd: Path | None = None) -> None:
    completed = subprocess.run(argv, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise ArtifactQualificationError(
            f"command failed with exit code {completed.returncode}: {argv!r}"
        )


def qualify_pyronin(checkout: Path, work_root: Path) -> dict[str, object]:
    """Build once, install the exact wheel outside checkout, and return identity evidence."""
    checkout = checkout.resolve(strict=True)
    work_root = work_root.resolve(strict=True)
    if work_root == checkout or work_root.is_relative_to(checkout):
        raise ArtifactQualificationError("qualification work_root must be outside checkout")

    outdir = work_root / "dist"
    target = work_root / "site-packages"
    outdir.mkdir(parents=True, exist_ok=False)
    target.mkdir(parents=True, exist_ok=False)
    package_root = checkout / "packages" / "pyronin"
    _run([sys.executable, "-m", "build", "--outdir", str(outdir), str(package_root)])
    wheel = _single_artifact(outdir, ".whl")
    sdist = _single_artifact(outdir, ".tar.gz")
    record = artifact_record(wheel, sdist)
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-index",
            "--no-deps",
            "--target",
            str(target),
            str(wheel),
        ]
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,pyronin; "
                "print(pathlib.Path(pyronin.__file__).resolve())"
            ),
        ],
        cwd=work_root,
        env={**os.environ, "PYTHONPATH": str(target)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0:
        raise ArtifactQualificationError(
            "installed pyronin import probe failed: " + probe.stderr.strip()
        )
    imported = assert_installed_origin(
        Path(probe.stdout.strip()), checkout=checkout, site_packages=target
    )

    tests_root = work_root / "contract-tests"
    shutil.copytree(checkout / "packages" / "pyronin" / "tests", tests_root)
    pytest_config = work_root / "pytest.ini"
    pytest_config.write_text("[pytest]\n", encoding="utf-8")
    test_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(tests_root),
            "-q",
            "-c",
            str(pytest_config),
            "--import-mode=importlib",
        ],
        cwd=work_root,
        env={**os.environ, "PYTHONPATH": str(target)},
        check=False,
    )
    if test_run.returncode != 0:
        raise ArtifactQualificationError(
            f"installed pyronin contract tests failed with exit code {test_run.returncode}"
        )
    return _record_qualification(
        record,
        imported_module=imported,
        site_packages=target,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path.cwd())
    parser.add_argument("--work-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.work_root is None:
        with tempfile.TemporaryDirectory(prefix="ronin-artifact-qualification-") as temporary:
            record = qualify_pyronin(args.checkout, Path(temporary))
    else:
        args.work_root.mkdir(parents=True, exist_ok=True)
        record = qualify_pyronin(args.checkout, args.work_root)
    encoded = _canonical_json(record) + "\n"
    if args.output is None:
        sys.stdout.write(encoded)
    else:
        args.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
