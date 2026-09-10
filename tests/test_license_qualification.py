from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.license_qualification import (
    LicenseQualificationError,
    direct_requirements,
    locked_graph,
    qualify,
)

_LOCK_SHA = "0" * 64
_HASH = "a" * 64


def _inventory(packages: list[dict[str, object]], *, lock_sha256: str = _LOCK_SHA) -> dict[str, object]:
    return {
        "schema_version": 1,
        "lock_file": "requirements-dev.lock",
        "lock_sha256": lock_sha256,
        "packages": packages,
    }


def _entry(
    name: str,
    version: str,
    license_name: str = "MIT",
    *,
    direct: bool = True,
) -> dict[str, object]:
    return {
        "package": name,
        "version": version,
        "direct": direct,
        "source": f"https://example.invalid/{name}",
        "declared_license": license_name,
        "license_files": [f"{name}-{version}.dist-info/licenses/LICENSE"],
    }


def _policy(*keys: str, project_notice: str = "not_required") -> dict[str, object]:
    return {
        "schema_version": 1,
        "project_notice": project_notice,
        "project_notice_rationale": "reviewed fixture obligations",
        "reviews": {
            key: {
                "decision": "allow",
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
) -> None:
    qualify(
        inventory,
        policy,
        graph,
        expected_lock_sha256=_LOCK_SHA,
        expected_direct=set(graph) if expected_direct is None else expected_direct,
    )


def test_locked_graph_reads_exact_versions_and_normalizes_names(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f"Foo_Bar==1.2.3 \\\n    --hash=sha256:{_HASH}\nother.pkg==4.5.6 \\\n    --hash=sha256:{_HASH}\n",
        encoding="utf-8",
    )

    assert locked_graph(lock) == {"foo-bar": "1.2.3", "other-pkg": "4.5.6"}


def test_locked_graph_reads_multiple_hash_continuations(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text(
        f"demo==1.0.0 \\\n    --hash=sha256:{_HASH} \\\n    --hash=sha256:{'b' * 64}\n",
        encoding="utf-8",
    )

    assert locked_graph(lock) == {"demo": "1.0.0"}


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
        f"demo==1.0.0 \\\n    --hash=sha256:{_HASH} \\\nother==2.0.0 \\\n    --hash=sha256:{_HASH}\n",
        encoding="utf-8",
    )

    with pytest.raises(LicenseQualificationError, match="unterminated hash continuation"):
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
requires = [\"setuptools==84.0.0\"]
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
requires = [\"setuptools==84.0.0\"]
build-backend = \"setuptools.build_meta\"

[project]
name = \"pyronin\"
version = \"0.1.0\"
dependencies = [\"http-client>=1,<2\"]
""",
        encoding="utf-8",
    )

    assert direct_requirements(tmp_path) == {"http-client", "pytest", "runtime"}


def test_qualify_accepts_exact_reviewed_locked_graph() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0", "Apache-2.0")])
    policy = _policy("alpha==1.0", "beta==2.0")

    _qualify(inventory, policy, graph)


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
        _qualify(inventory, _policy("alpha==1.0", "beta==2.0"), graph)


def test_qualify_requires_exact_lock_file_identity() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")], lock_sha256="f" * 64)

    with pytest.raises(LicenseQualificationError, match="lock_sha256"):
        _qualify(inventory, _policy("alpha==1.0"), graph)


def test_qualify_rejects_direct_dependency_missing_from_lock() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])

    with pytest.raises(LicenseQualificationError, match="direct project dependencies missing"):
        _qualify(
            inventory,
            _policy("alpha==1.0"),
            graph,
            expected_direct={"alpha", "beta"},
        )


def test_qualify_rejects_wrong_direct_classification() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0", direct=True)])

    with pytest.raises(LicenseQualificationError, match="direct classification"):
        _qualify(
            inventory,
            _policy("alpha==1.0", "beta==2.0"),
            graph,
            expected_direct={"alpha"},
        )


def test_qualify_requires_boolean_direct_classification() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([{**_entry("alpha", "1.0"), "direct": "yes"}])

    with pytest.raises(LicenseQualificationError, match="direct classification must be boolean"):
        _qualify(inventory, _policy("alpha==1.0"), graph)


def test_qualify_requires_exact_policy_key_set() -> None:
    graph = {"alpha": "1.0", "beta": "2.0"}
    inventory = _inventory([_entry("alpha", "1.0"), _entry("beta", "2.0")])

    with pytest.raises(LicenseQualificationError, match="exactly match"):
        _qualify(inventory, _policy("alpha==1.0"), graph)


def test_qualify_rejects_denied_dependency() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy("alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    reviews["alpha==1.0"] = {
        "decision": "deny",
        "notice_required": False,
        "attribution_required": False,
        "rationale": "fixture",
    }

    with pytest.raises(LicenseQualificationError, match="not approved"):
        _qualify(inventory, policy, graph)


def test_qualify_requires_attribution_decision() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy("alpha==1.0")
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
    policy = _policy("alpha==1.0")
    reviews = policy["reviews"]
    assert isinstance(reviews, dict)
    reviews["alpha==1.0"] = {
        "decision": "allow",
        "notice_required": False,
        "attribution_required": False,
        "rationale": "",
    }

    with pytest.raises(LicenseQualificationError, match="rationale is required"):
        _qualify(inventory, policy, graph)


def test_qualify_requires_explicit_notice_decision() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])

    with pytest.raises(LicenseQualificationError, match="NOTICE decision is unresolved"):
        _qualify(inventory, _policy("alpha==1.0", project_notice="unknown"), graph)


def test_qualify_requires_project_notice_rationale() -> None:
    graph = {"alpha": "1.0"}
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy("alpha==1.0")
    policy["project_notice_rationale"] = ""

    with pytest.raises(LicenseQualificationError, match="NOTICE rationale"):
        _qualify(inventory, policy, graph)


def test_policy_and_inventory_are_machine_readable_json_fixtures(tmp_path: Path) -> None:
    inventory_path = tmp_path / "licenses.json"
    policy_path = tmp_path / "policy.json"
    inventory = _inventory([_entry("alpha", "1.0")])
    policy = _policy("alpha==1.0")
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    policy_path.write_text(json.dumps(policy), encoding="utf-8")

    _qualify(
        json.loads(inventory_path.read_text(encoding="utf-8")),
        json.loads(policy_path.read_text(encoding="utf-8")),
        {"alpha": "1.0"},
    )
