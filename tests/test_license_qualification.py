from __future__ import annotations

import json
from pathlib import Path

import pytest
from packaging.markers import default_environment

from tools.license_qualification import (
    LicenseQualificationError,
    direct_requirements,
    locked_graph,
    package_evidence_sha256,
    qualify,
)

_LOCK_SHA = "0" * 64
_HASH = "a" * 64


def _inventory(
    packages: list[dict[str, object]],
    *,
    lock_sha256: str = _LOCK_SHA,
    lock_file: str = "requirements-dev.lock",
) -> dict[str, object]:
    enriched: list[dict[str, object]] = []
    for package in packages:
        entry = dict(package)
        entry["evidence_sha256"] = package_evidence_sha256(entry)
        enriched.append(entry)
    return {
        "schema_version": 1,
        "lock_file": lock_file,
        "lock_sha256": lock_sha256,
        "packages": enriched,
    }


def _entry(
    name: str,
    version: str,
    license_name: str = "MIT",
    *,
    direct: bool = True,
) -> dict[str, object]:
    declared_path = "LICENSE.custom"
    return {
        "package": name,
        "version": version,
        "direct": direct,
        "source": f"https://example.invalid/{name}",
        "declared_license": license_name,
        "declared_license_files": [declared_path],
        "license_files": [
            {
                "path": f"{name}-{version}.dist-info/licenses/{declared_path}",
                "sha256": _HASH,
            }
        ],
    }


def _policy(
    inventory: dict[str, object],
    *keys: str,
    project_notice: str = "not_required",
) -> dict[str, object]:
    packages = inventory["packages"]
    assert isinstance(packages, list)
    evidence = {
        f"{entry['package']}=={entry['version']}": entry["evidence_sha256"]
        for entry in packages
        if isinstance(entry, dict)
    }
    return {
        "schema_version": 1,
        "project_notice": project_notice,
        "project_notice_rationale": "reviewed fixture obligations",
        "reviews": {
            key: {
                "decision": "allow",
                "evidence_sha256": evidence[key],
                "notice_required": False,
                "attribution_required": False,
                "rationale": "reviewed fixture",
            }
            for key in keys
        },
    }


def _qualify(
    inventory: object,
    policy: object,
    graph: dict[str, str],
    *,
    expected_direct: set[str] | None = None,
    expected_lock_file: str = "requirements-dev.lock",
) -> None:
    qualify(
        inventory,
        policy,
        graph,
        expected_lock_file=expected_lock_file,
        expected_lock_sha256=_LOCK_SHA,
        expected_direct=set(graph) if expected_direct is None else expected_direct,
    )


def test_locked_graph_reads_exact_versions_and_normalizes_names(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f"Foo_Bar==1.2.3 \\\n    --hash=sha256:{_HASH}\n"
        f"other.pkg==4.5.6 \\\n    --hash=sha256:{_HASH}\n",
        encoding="utf-8",
    )

    assert locked_graph(lock) == {
        "foo-bar": "1.2.3",
        "other-pkg": "4.5.6",
    }


def test_locked_graph_reads_multiple_hash_continuations(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f"demo==1.0.0 \\\n    --hash=sha256:{_HASH} \\\n    --hash=sha256:{'b' * 64}\n",
        encoding="utf-8",
    )

    assert locked_graph(lock) == {"demo": "1.0.0"}


def test_locked_graph_accepts_pep508_environment_markers(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f'demo==1.0.0 ; python_version >= "3.13" {chr(92)}\n    --hash=sha256:{_HASH}\n',
        encoding="utf-8",
    )
    assert locked_graph(lock) == {"demo": "1.0.0"}


def test_locked_graph_selects_only_the_active_marker_variant(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-test.lock"
    lock.write_text(
        f'demo==1.0.0 ; python_version < "3.13" {chr(92)}\n'
        f"    --hash=sha256:{_HASH}\n"
        f'demo==2.0.0 ; python_version >= "3.13" {chr(92)}\n'
        f"    --hash=sha256:{_HASH}\n",
        encoding="utf-8",
    )
    python_312 = default_environment() | {"python_version": "3.12"}
    python_313 = default_environment() | {"python_version": "3.13"}

    assert locked_graph(lock, marker_environment=python_312) == {"demo": "1.0.0"}
    assert locked_graph(lock, marker_environment=python_313) == {"demo": "2.0.0"}


def test_locked_graph_fails_closed_on_conflicting_versions(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f"demo==1.0.0 \\\n    --hash=sha256:{_HASH}\ndemo==2.0.0 \\\n    --hash=sha256:{_HASH}\n",
        encoding="utf-8",
    )

    with pytest.raises(LicenseQualificationError, match="conflicting versions"):
        locked_graph(lock)


def test_locked_graph_rejects_requirement_without_hash(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text("demo==1.0.0\n", encoding="utf-8")

    with pytest.raises(LicenseQualificationError, match="no sha256 hash"):
        locked_graph(lock)


def test_locked_graph_rejects_hash_not_joined_to_requirement(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f"demo==1.0.0\n    --hash=sha256:{_HASH}\n",
        encoding="utf-8",
    )

    with pytest.raises(LicenseQualificationError, match="no sha256 hash"):
        locked_graph(lock)


def test_locked_graph_rejects_unterminated_hash_continuation(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f"demo==1.0.0 \\\n    --hash=sha256:{_HASH} \\\n"
        f"other==2.0.0 \\\n    --hash=sha256:{_HASH}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        LicenseQualificationError,
        match="unterminated hash continuation",
    ):
        locked_graph(lock)


def test_locked_graph_rejects_unsupported_active_dependency_syntax(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f"demo>=1.0 \\\n    --hash=sha256:{_HASH}\n",
        encoding="utf-8",
    )

    with pytest.raises(LicenseQualificationError, match="unsupported active lock syntax"):
        locked_graph(lock)


def test_direct_requirements_excludes_build_backend_not_present_in_resolved_lock(
    tmp_path: Path,
) -> None:
    (tmp_path / "packages/pyronin").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        """[build-system]
requires = [\"setuptools==84.2.1\"]
build-backend = \"setuptools.build_meta\"

[project]
name = \"root\"
version = \"0.0.0\"
dependencies = [\"runtime>=1,<2\"]

[project.optional-dependencies]
dev = [\"pytest>=9,<10\"]
""",
        encoding="utf-8",
    )
    (tmp_path / "packages/pyronin/pyproject.toml").write_text(
        """[build-system]
requires = [\"setuptools==84.2.1\"]
build-backend = \"setuptools.build_meta\"

[project]
name = \"pyronin\"
version = \"0.1.0\"
dependencies = [\"http-client>=1,<2\"]
""",
        encoding="utf-8",
    )

    assert direct_requirements(tmp_path) == {"http-client", "pytest", "runtime"}


def test_direct_requirements_covers_multiple_optional_extras(tmp_path: Path) -> None:
    (tmp_path / "packages/pyronin").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "root"
version = "0.0.0"
dependencies = ["runtime>=1,<2"]

[project.optional-dependencies]
dev = ["pytest>=9,<10"]
data-plane = ["pyarrow>=15,<24"]
ml = ["numpy>=1.23,<2.4"]
""",
        encoding="utf-8",
    )
    (tmp_path / "packages/pyronin/pyproject.toml").write_text(
        """[project]
name = "pyronin"
version = "0.1.0"
dependencies = ["http-client>=1,<2"]
""",
        encoding="utf-8",
    )

    assert direct_requirements(tmp_path, extras=("dev", "data-plane", "ml")) == {
        "http-client",
        "numpy",
        "pyarrow",
        "pytest",
        "runtime",
    }


def test_qualify_accepts_exact_reviewed_locked_graph() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0", "Apache-2.0")])
    policy = _policy(inventory, "alpha==1.0", "beta==2.0")

    _qualify(inventory, policy, graph)


def test_qualify_accepts_non_default_lock_file_identity() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")], lock_file="requirements-test.lock")
    policy = _policy(inventory, "alpha==1.0")

    _qualify(inventory, policy, graph, expected_lock_file="requirements-test.lock")


@pytest.mark.parametrize(
    ("inventory", "message"),
    [
        (_inventory([_entry("alpha", "1.0")]), "does not exactly match"),
        (_inventory([_entry("alpha", "1.0"), _entry("alpha", "1.0")]), "duplicate"),
        (
            _inventory([{**_entry("alpha", "1.0"), "declared_license": None}]),
            "missing declared license",
        ),
        (
            _inventory([{**_entry("alpha", "1.0"), "source": None}]),
            "missing distribution source",
        ),
    ],
)
def test_qualify_fails_closed_on_incomplete_or_ambiguous_inventory(
    inventory: dict[str, object],
    message: str,
) -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    with pytest.raises(LicenseQualificationError, match=message):
        _qualify(inventory, _policy(inventory, "alpha==1.0"), graph)


def test_qualify_requires_exact_lock_file_identity() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory(
        [_entry("alpha", "1.0")],
        lock_sha256="f" * 64,
        lock_file="requirements-test.lock",
    )
    with pytest.raises(LicenseQualificationError, match="requirements-test.lock"):
        _qualify(
            inventory,
            _policy(inventory, "alpha==1.0"),
            graph,
            expected_lock_file="requirements-test.lock",
        )


def test_qualify_rejects_direct_dependency_missing_from_lock() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory(
        [_entry("alpha", "1.0")],
        lock_file="requirements-test.lock",
    )
    with pytest.raises(
        LicenseQualificationError,
        match="requirements-test.lock: beta",
    ):
        _qualify(
            inventory,
            _policy(inventory, "alpha==1.0"),
            graph,
            expected_direct={"alpha", "beta"},
            expected_lock_file="requirements-test.lock",
        )


def test_qualify_rejects_wrong_direct_classification() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0", direct=True)])
    with pytest.raises(LicenseQualificationError, match="direct classification"):
        _qualify(
            inventory,
            _policy(inventory, "alpha==1.0", "beta==2.0"),
            graph,
            expected_direct={"alpha"},
        )


def test_qualify_requires_boolean_direct_classification() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([{**_entry("alpha", "1.0"), "direct": "yes"}])
    with pytest.raises(LicenseQualificationError, match="direct classification must be boolean"):
        _qualify(inventory, _policy(inventory, "alpha==1.0"), graph)


def test_qualify_requires_exact_policy_key_set() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0")])
    with pytest.raises(LicenseQualificationError, match="exactly match"):
        _qualify(inventory, _policy(inventory, "alpha==1.0"), graph)


def test_qualify_lists_missing_and_stale_policy_keys() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0")])
    policy = _policy(inventory, "alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    reviews["old-package==9.9"] = {
        "decision": "allow",
        "evidence_sha256": "b" * 64,
        "notice_required": False,
        "attribution_required": False,
        "rationale": "stale fixture entry",
    }

    with pytest.raises(LicenseQualificationError) as error:
        _qualify(inventory, policy, graph)

    message = str(error.value)
    assert "missing review decisions: beta==2.0" in message
    assert "stale policy entries: old-package==9.9" in message


def test_qualify_reports_missing_decisions_and_stale_evidence_together() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0")])
    policy = _policy(inventory, "alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    reviews["alpha==1.0"]["evidence_sha256"] = "b" * 64

    with pytest.raises(LicenseQualificationError) as error:
        _qualify(inventory, policy, graph)

    message = str(error.value)
    assert "missing review decisions: beta==2.0" in message
    assert "review evidence is stale or mismatched: alpha==1.0" in message


def test_qualify_rejects_stale_review_when_installed_evidence_changes() -> None:
    graph = {"alpha": "1.0"}
    original = _inventory([_entry("alpha", "1.0", "MIT")])
    policy = _policy(original, "alpha==1.0")
    changed = _inventory([_entry("alpha", "1.0", "Apache-2.0")])

    with pytest.raises(LicenseQualificationError, match="review evidence is stale or mismatched"):
        _qualify(changed, policy, graph)


def test_qualify_rejects_stale_review_when_declared_license_file_changes() -> None:
    graph = {"alpha": "1.0"}
    original = _inventory([_entry("alpha", "1.0")])
    policy = _policy(original, "alpha==1.0")
    changed_entry = _entry("alpha", "1.0")
    changed_entry["declared_license_files"] = ["THIRD_PARTY_TERMS.txt"]
    changed_entry["license_files"] = [
        {
            "path": "alpha-1.0.dist-info/licenses/THIRD_PARTY_TERMS.txt",
            "sha256": _HASH,
        }
    ]
    changed = _inventory([changed_entry])

    with pytest.raises(LicenseQualificationError, match="review evidence is stale or mismatched"):
        _qualify(changed, policy, graph)


def test_qualify_rejects_invalid_declared_license_file_path() -> None:
    graph = {"alpha": "1.0"}
    entry = _entry("alpha", "1.0")
    entry["declared_license_files"] = ["../LICENSE"]
    inventory = _inventory([entry])

    with pytest.raises(LicenseQualificationError, match="invalid declared_license_files"):
        _qualify(inventory, _policy(inventory, "alpha==1.0"), graph)


def test_qualify_rejects_tampered_license_file_digest() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    packages = inventory["packages"]
    assert isinstance(packages, list)
    entry = packages[0]
    assert isinstance(entry, dict)
    files = entry["license_files"]
    assert isinstance(files, list)
    file_entry = files[0]
    assert isinstance(file_entry, dict)
    file_entry["sha256"] = "b" * 64

    with pytest.raises(LicenseQualificationError, match="package evidence_sha256 does not match"):
        _qualify(inventory, _policy(_inventory([_entry("alpha", "1.0")]), "alpha==1.0"), graph)


def test_qualify_rejects_denied_dependency() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy(inventory, "alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    reviews["alpha==1.0"]["decision"] = "deny"

    with pytest.raises(LicenseQualificationError, match="not approved"):
        _qualify(inventory, policy, graph)


def test_qualify_requires_attribution_decision() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy(inventory, "alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    review = reviews["alpha==1.0"]
    assert isinstance(review, dict)
    review.pop("attribution_required")

    with pytest.raises(LicenseQualificationError, match="attribution_required"):
        _qualify(inventory, policy, graph)


def test_qualify_requires_review_rationale() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy(inventory, "alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    reviews["alpha==1.0"]["rationale"] = ""

    with pytest.raises(LicenseQualificationError, match="rationale is required"):
        _qualify(inventory, policy, graph)


def test_qualify_requires_explicit_notice_decision() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    with pytest.raises(LicenseQualificationError, match="NOTICE decision is unresolved"):
        _qualify(inventory, _policy(inventory, "alpha==1.0", project_notice="unknown"), graph)


def test_qualify_requires_project_notice_rationale() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy(inventory, "alpha==1.0")
    policy["project_notice_rationale"] = ""

    with pytest.raises(LicenseQualificationError, match="NOTICE rationale"):
        _qualify(inventory, policy, graph)


def test_policy_and_inventory_are_machine_readable_json_fixtures(tmp_path: Path) -> None:
    inventory_path = tmp_path / "licenses.json"
    policy_path = tmp_path / "policy.json"
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy(inventory, "alpha==1.0")
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    _qualify(
        json.loads(inventory_path.read_text(encoding="utf-8")),
        json.loads(policy_path.read_text(encoding="utf-8")),
        {"alpha": "1.0"},
    )
