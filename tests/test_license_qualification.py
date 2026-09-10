from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.license_qualification import (
    LicenseQualificationError,
    locked_graph,
    qualify,
)


def _inventory(packages: list[dict[str, object]]) -> dict[str, object]:
    return {"schema_version": 1, "lock_file": "requirements-dev.lock", "packages": packages}


def _entry(name: str, version: str, license_name: str = "MIT") -> dict[str, object]:
    return {
        "package": name,
        "version": version,
        "direct": True,
        "source": f"https://example.invalid/{name}",
        "declared_license": license_name,
        "license_files": [f"{name}-{version}.dist-info/licenses/LICENSE"],
    }


def _policy(*keys: str, project_notice: str = "not_required") -> dict[str, object]:
    return {
        "schema_version": 1,
        "project_notice": project_notice,
        "reviews": {
            key: {"decision": "allow", "notice_required": False, "rationale": "reviewed fixture"}
            for key in keys
        },
    }


def test_locked_graph_reads_exact_versions_and_normalizes_names(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        "Foo_Bar==1.2.3 \\\n    --hash=sha256:abc\nother.pkg==4.5.6 \\\n    --hash=sha256:def\n",
        encoding="utf-8",
    )

    assert locked_graph(lock) == {"foo-bar": "1.2.3", "other-pkg": "4.5.6"}


def test_locked_graph_fails_closed_on_conflicting_versions(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text("demo==1.0.0\ndemo==2.0.0\n", encoding="utf-8")

    with pytest.raises(LicenseQualificationError, match="conflicting versions"):
        locked_graph(lock)


def test_qualify_accepts_exact_reviewed_locked_graph() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0", "Apache-2.0")])
    policy = _policy("alpha==1.0", "beta==2.0")

    qualify(inventory, policy, graph)


@pytest.mark.parametrize(
    "inventory, message",
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
        qualify(inventory, _policy("alpha==1.0", "beta==2.0"), graph)


def test_qualify_requires_exact_policy_key_set() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0")])

    with pytest.raises(LicenseQualificationError, match="exactly match"):
        qualify(inventory, _policy("alpha==1.0"), graph)


def test_qualify_rejects_denied_dependency() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy("alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    reviews["alpha==1.0"] = {
        "decision": "deny",
        "notice_required": False,
        "rationale": "fixture",
    }

    with pytest.raises(LicenseQualificationError, match="not approved"):
        qualify(inventory, policy, graph)


def test_qualify_requires_review_rationale() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy("alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    reviews["alpha==1.0"] = {
        "decision": "allow",
        "notice_required": False,
        "rationale": "",
    }

    with pytest.raises(LicenseQualificationError, match="rationale is required"):
        qualify(inventory, policy, graph)


def test_qualify_requires_explicit_notice_decision() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])

    with pytest.raises(LicenseQualificationError, match="NOTICE decision is unresolved"):
        qualify(inventory, _policy("alpha==1.0", project_notice="unknown"), graph)


def test_policy_and_inventory_are_machine_readable_json_fixtures(tmp_path: Path) -> None:
    inventory_path = tmp_path / "licenses.json"
    policy_path = tmp_path / "policy.json"
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy("alpha==1.0")
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    qualify(
        json.loads(inventory_path.read_text(encoding="utf-8")),
        json.loads(policy_path.read_text(encoding="utf-8")),
        {"alpha": "1.0"},
    )
