from __future__ import annotations

import email.message
import json
from pathlib import Path, PurePosixPath

import pytest

from tools import license_qualification as license_tool

# Several parametrized rejection fixtures are intentionally kept inline.
# ruff: noqa: ARG005, E501

_HASH = "a" * 64


class FakeDistribution:
    def __init__(self, name: str | None, version: str, *, files=(), values=None) -> None:
        self.metadata = email.message.Message()
        if name is not None:
            self.metadata["Name"] = name
        self.metadata["Version"] = version
        for key, value in (values or {}).items():
            if isinstance(value, list):
                for item in value:
                    self.metadata.add_header(key, item)
            else:
                self.metadata[key] = value
        self.version = version
        self.files = list(files)
        self.root = Path("/")

    def locate_file(self, file):
        return self.root / str(file).lstrip("/")


def _project(
    root: Path, *, lock_lines: str = f"alpha==1.0 \\\n    --hash=sha256:{_HASH}\n"
) -> None:
    (root / "packages/pyronin").mkdir(parents=True)
    (root / "requirements-dev.lock").write_text(lock_lines, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname="root"\nversion="0"\ndependencies=["alpha>=1"]\n',
        encoding="utf-8",
    )
    (root / "packages/pyronin/pyproject.toml").write_text(
        '[project]\nname="pyronin"\nversion="0"\ndependencies=[]\n',
        encoding="utf-8",
    )


def _valid_inventory() -> tuple[dict[str, object], dict[str, object]]:
    entry: dict[str, object] = {
        "package": "alpha",
        "version": "1.0",
        "direct": True,
        "source": "https://example.invalid/alpha",
        "declared_license": "MIT",
        "declared_license_files": ["LICENSE"],
        "license_files": [{"path": "alpha-1.0.dist-info/licenses/LICENSE", "sha256": _HASH}],
    }
    entry["evidence_sha256"] = license_tool.package_evidence_sha256(entry)
    inventory = {
        "schema_version": 1,
        "lock_file": "requirements-dev.lock",
        "lock_sha256": "0" * 64,
        "packages": [entry],
    }
    policy = {
        "schema_version": 1,
        "project_notice": "not_required",
        "project_notice_rationale": "reviewed",
        "reviews": {
            "alpha==1.0": {
                "decision": "allow",
                "evidence_sha256": entry["evidence_sha256"],
                "notice_required": False,
                "attribution_required": False,
                "rationale": "reviewed",
            }
        },
    }
    return inventory, policy


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "# only comment\n",
        "  # leading comment\n",
        "alpha==1.0 \\\n# interrupted\n    --hash=sha256:" + _HASH + "\n",
        "alpha==1.0 \\\n    --hash=sha256:" + _HASH + " \\\n",
        "alpha==1.0 \\\n    --hash=sha256:" + "A" * 64 + "\n",
        "alpha==1.0 \\\n    --hash=sha256:"
        + _HASH
        + "\n alpha==1.0 \\\n    --hash=sha256:"
        + _HASH
        + "\n",
        "alpha==1.0 \\\n    --hash=sha256:"
        + _HASH
        + "\nalpha==2.0 \\\n    --hash=sha256:"
        + _HASH
        + "\n",
        "alpha==1.0 \\\n    --hash=sha256:" + _HASH + "\n    --hash=sha256:" + _HASH + "\n",
        "--hash=sha256:" + _HASH + "\n",
        "alpha==1.0 \\\n    --hash=sha256:" + _HASH + "\nnot a requirement\n",
    ],
)
def test_locked_graph_rejects_malformed_edges(tmp_path: Path, contents: str) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(contents, encoding="utf-8")
    with pytest.raises(license_tool.LicenseQualificationError):
        license_tool.locked_graph(lock)


@pytest.mark.parametrize(
    "value",
    ["", " ", "../LICENSE", "/LICENSE", "a\\b", "./LICENSE", "a/../b"],
)
def test_declared_file_normalization_rejects_unsafe_paths(value: str) -> None:
    with pytest.raises(license_tool.LicenseQualificationError):
        license_tool._normalize_declared_license_file(value)


@pytest.mark.parametrize(
    "value",
    ["", " ", "../LICENSE", "/LICENSE", "a\\b", "./LICENSE", "a/../b"],
)
def test_installed_file_normalization_rejects_unsafe_paths(value: str) -> None:
    with pytest.raises(license_tool.LicenseQualificationError):
        license_tool._normalize_installed_license_file_path(value)


@pytest.mark.parametrize(
    "declared",
    [None, "MIT", [1], ["LICENSE", "LICENSE"], ["NOTICE", "LICENSE"]],
)
def test_inventory_rejects_invalid_declared_file_lists(declared: object) -> None:
    inventory, policy = _valid_inventory()
    entry = inventory["packages"][0]
    entry["declared_license_files"] = declared
    entry["evidence_sha256"] = license_tool.package_evidence_sha256(entry)
    policy["reviews"]["alpha==1.0"]["evidence_sha256"] = entry["evidence_sha256"]
    with pytest.raises(license_tool.LicenseQualificationError):
        license_tool.qualify(
            inventory,
            policy,
            {"alpha": "1.0"},
            expected_lock_sha256="0" * 64,
            expected_direct={"alpha"},
        )


@pytest.mark.parametrize(
    "files",
    [
        None,
        [None],
        [{"path": "LICENSE", "sha256": _HASH, "extra": True}],
        [{"path": 1, "sha256": _HASH}],
        [{"path": "LICENSE", "sha256": "bad"}],
        [{"path": "LICENSE", "sha256": _HASH}, {"path": "LICENSE", "sha256": _HASH}],
        [{"path": "z", "sha256": _HASH}, {"path": "a", "sha256": _HASH}],
    ],
)
def test_inventory_rejects_invalid_installed_file_evidence(files: object) -> None:
    inventory, policy = _valid_inventory()
    entry = inventory["packages"][0]
    entry["license_files"] = files
    entry["evidence_sha256"] = license_tool.package_evidence_sha256(entry)
    policy["reviews"]["alpha==1.0"]["evidence_sha256"] = entry["evidence_sha256"]
    with pytest.raises(license_tool.LicenseQualificationError):
        license_tool.qualify(
            inventory,
            policy,
            {"alpha": "1.0"},
            expected_lock_sha256="0" * 64,
            expected_direct={"alpha"},
        )


def test_package_evidence_is_stable_and_only_binds_reviewed_fields() -> None:
    inventory, _ = _valid_inventory()
    entry = inventory["packages"][0]
    digest = license_tool.package_evidence_sha256(entry)
    entry["ignored"] = "outside evidence schema"
    assert license_tool.package_evidence_sha256(entry) == digest
    assert (
        license_tool.lock_sha256(Path(__file__))
        == __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest()
    )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"License-Expression": "MIT OR Apache-2.0", "License": "fallback"}, "MIT OR Apache-2.0"),
        ({"License": "Apache-2.0"}, "Apache-2.0"),
        (
            {"License": "UNKNOWN", "Classifier": ["License :: OSI Approved :: MIT License"]},
            "OSI Approved :: MIT License",
        ),
        ({}, None),
    ],
)
def test_declared_license_metadata_fallbacks(
    values: dict[str, object], expected: str | None
) -> None:
    dist = FakeDistribution("alpha", "1", values=values)
    assert license_tool._declared_license(dist) == expected


def test_source_metadata_fallbacks_and_url_escaping() -> None:
    dist = FakeDistribution(
        "package name",
        "1/2",
        values={"Project-URL": ["Homepage, https://docs.invalid", "Source, "]},
    )
    assert license_tool._source(dist) == "https://docs.invalid"
    dist = FakeDistribution(
        "package name", "1/2", values={"Project-URL": ["Repository, https://repo.invalid"]}
    )
    assert license_tool._source(dist) == "https://repo.invalid"
    dist = FakeDistribution("package name", "1/2")
    assert license_tool._source(dist) == "https://pypi.org/project/package%20name/1/2/"
    dist = FakeDistribution(None, "")
    assert license_tool._source(dist) is None


def test_license_file_discovery_matches_pep639_legacy_and_declared_paths(tmp_path: Path) -> None:
    files = [
        PurePosixPath("alpha-1.dist-info/licenses/LICENSE.txt"),
        PurePosixPath("alpha-1.dist-info/licenses/NOTICE.txt"),
        PurePosixPath("alpha-1.dist-info/licenses/custom/LEGAL.txt"),
        PurePosixPath("alpha-1.dist-info/metadata.json"),
    ]
    for file in files:
        target = tmp_path / str(file)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(file), encoding="utf-8")
    dist = FakeDistribution(
        "alpha",
        "1",
        files=files,
        values={"License-File": ["custom/LEGAL.txt"]},
    )
    dist.root = tmp_path
    found = license_tool._license_files(dist, ("custom/LEGAL.txt",))
    assert [item["path"] for item in found] == [str(files[i]) for i in range(3)]


def test_license_file_discovery_fails_for_missing_declared_or_unreadable_files(
    tmp_path: Path,
) -> None:
    dist = FakeDistribution("alpha", "1", files=[PurePosixPath("alpha.dist-info/metadata.json")])
    with pytest.raises(license_tool.LicenseQualificationError, match="not installed"):
        license_tool._license_files(dist, ("LICENSE",))
    file = PurePosixPath("alpha.dist-info/LICENSE")
    dist = FakeDistribution("alpha", "1", files=[file])
    dist.root = tmp_path
    with pytest.raises(license_tool.LicenseQualificationError, match="cannot read"):
        license_tool._license_files(dist, ())


def test_locked_distributions_filters_missing_names_and_rejects_duplicates(monkeypatch) -> None:
    monkeypatch.setattr(
        license_tool.metadata,
        "distributions",
        lambda: [
            FakeDistribution(None, "0"),
            FakeDistribution("other", "1"),
            FakeDistribution("Alpha", "1"),
        ],
    )
    assert set(license_tool._locked_distributions({"alpha": "1"})) == {"alpha"}
    monkeypatch.setattr(
        license_tool.metadata,
        "distributions",
        lambda: [FakeDistribution("alpha", "1"), FakeDistribution("ALPHA", "1")],
    )
    with pytest.raises(license_tool.LicenseQualificationError, match="multiple installed"):
        license_tool._locked_distributions({"alpha": "1"})


def test_generate_inventory_builds_exact_evidence_and_rejects_missing_or_wrong_distribution(
    tmp_path: Path, monkeypatch
) -> None:
    _project(tmp_path)
    legal = PurePosixPath("alpha-1.0.dist-info/licenses/LICENSE")
    target = tmp_path / str(legal)
    target.parent.mkdir(parents=True)
    target.write_text("MIT", encoding="utf-8")
    dist = FakeDistribution("Alpha", "1.0", files=[legal], values={"License-Expression": "MIT"})
    dist.root = tmp_path
    monkeypatch.setattr(license_tool.metadata, "distributions", lambda: [dist])
    result = license_tool.generate_inventory(tmp_path)
    assert result["packages"][0]["package"] == "alpha"
    assert (
        result["packages"][0]["license_files"][0]["sha256"]
        == __import__("hashlib").sha256(b"MIT").hexdigest()
    )

    monkeypatch.setattr(license_tool.metadata, "distributions", lambda: [])
    with pytest.raises(license_tool.LicenseQualificationError, match="not installed"):
        license_tool.generate_inventory(tmp_path)
    wrong = FakeDistribution("alpha", "2.0")
    monkeypatch.setattr(license_tool.metadata, "distributions", lambda: [wrong])
    with pytest.raises(license_tool.LicenseQualificationError, match="differs from lock"):
        license_tool.generate_inventory(tmp_path)


@pytest.mark.parametrize(
    ("inventory_change", "policy_change", "message"),
    [
        (lambda i: i.update(schema_version=2), lambda p: None, "schema_version"),
        (lambda i: i.update(lock_file="other.lock"), lambda p: None, "lock_file"),
        (lambda i: i.update(packages=None), lambda p: None, "packages must be a list"),
        (lambda i: i.update(packages=[None]), lambda p: None, "entry must be an object"),
        (lambda i: i["packages"][0].update(package="ALPHA"), lambda p: None, "normalized"),
        (lambda i: i["packages"][0].update(package=""), lambda p: None, "non-empty strings"),
        (lambda i: i["packages"][0].update(direct="yes"), lambda p: None, "must be boolean"),
        (
            lambda i: i["packages"][0].update(source=" "),
            lambda p: None,
            "missing distribution source",
        ),
        (
            lambda i: i["packages"][0].update(declared_license=" "),
            lambda p: None,
            "missing declared license",
        ),
        (
            lambda i: i["packages"][0].update(evidence_sha256="bad"),
            lambda p: None,
            "invalid package evidence",
        ),
        (lambda i: None, lambda p: p.update(schema_version=2), "policy schema_version"),
        (lambda i: None, lambda p: p.update(reviews=[]), "reviews must be an object"),
        (lambda i: None, lambda p: p["reviews"].update({"extra": {}}), "review keys"),
        (lambda i: None, lambda p: p["reviews"].update({"alpha==1.0": None}), "missing reviewed"),
        (
            lambda i: None,
            lambda p: p["reviews"]["alpha==1.0"].update(evidence_sha256="stale"),
            "stale or mismatched",
        ),
        (
            lambda i: None,
            lambda p: p["reviews"]["alpha==1.0"].update(decision="deny"),
            "not approved",
        ),
        (
            lambda i: None,
            lambda p: p["reviews"]["alpha==1.0"].update(notice_required="yes"),
            "notice_required",
        ),
        (
            lambda i: None,
            lambda p: p["reviews"]["alpha==1.0"].update(attribution_required="yes"),
            "attribution_required",
        ),
        (lambda i: None, lambda p: p.update(project_notice="unknown"), "NOTICE decision"),
        (lambda i: None, lambda p: p.update(project_notice_rationale=" "), "NOTICE rationale"),
    ],
)
def test_qualify_rejects_invalid_inventory_and_policy_edges(
    inventory_change, policy_change, message
) -> None:
    inventory, policy = _valid_inventory()
    inventory_change(inventory)
    policy_change(policy)
    with pytest.raises(license_tool.LicenseQualificationError, match=message):
        license_tool.qualify(
            inventory,
            policy,
            {"alpha": "1.0"},
            expected_lock_sha256="0" * 64,
            expected_direct={"alpha"},
        )


def test_json_loader_and_cli_report_errors_and_success(tmp_path: Path, monkeypatch, capsys) -> None:
    with pytest.raises(license_tool.LicenseQualificationError, match="cannot read valid JSON"):
        license_tool._load_json(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(license_tool.LicenseQualificationError, match="cannot read valid JSON"):
        license_tool._load_json(bad)

    _project(tmp_path)
    inventory, policy = _valid_inventory()
    inventory["lock_sha256"] = license_tool.lock_sha256(tmp_path / "requirements-dev.lock")
    (tmp_path / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    (tmp_path / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "license_qualification",
            "--root",
            str(tmp_path),
            "--inventory",
            "inventory.json",
            "--policy",
            "policy.json",
        ],
    )
    assert license_tool.main() == 0
    assert "license qualification: ok (1 locked distributions)" in capsys.readouterr().out


def test_cli_generates_inventory_to_requested_path(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path)
    monkeypatch.setattr(license_tool, "generate_inventory", lambda root: {"schema_version": 1})
    output = tmp_path / "nested/inventory.json"
    monkeypatch.setattr(
        "sys.argv",
        ["license_qualification", "--root", str(tmp_path), "--write-inventory", str(output)],
    )
    assert license_tool.main() == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {"schema_version": 1}
