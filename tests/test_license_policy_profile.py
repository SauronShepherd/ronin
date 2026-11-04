from __future__ import annotations

import pytest

from tools.license_policy_profile import LicensePolicyProfileError, project_policy

_HASH = "a" * 64


def _inventory(*packages: tuple[str, str, str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "packages": [
            {"package": name, "version": version, "evidence_sha256": digest}
            for name, version, digest in packages
        ],
    }


def _policy(*reviews: tuple[str, str, str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "project_notice": "not_required",
        "project_notice_rationale": "Reviewed project distribution evidence.",
        "reviews": {
            key: {
                "decision": decision,
                "evidence_sha256": digest,
                "notice_required": False,
                "attribution_required": False,
                "rationale": "Existing maintainer review.",
            }
            for key, decision, digest in reviews
        },
    }


def test_profile_keeps_only_matching_existing_reviews() -> None:
    inventory = _inventory(("pyyaml", "6.0.3", _HASH))
    policy = _policy(
        ("pyyaml==6.0.3", "allow", _HASH),
        ("pyyaml-ft==8.0.0", "allow", "b" * 64),
    )

    result, stale = project_policy(inventory, policy)

    assert set(result["reviews"]) == {"pyyaml==6.0.3"}
    assert result["reviews"]["pyyaml==6.0.3"]["evidence_sha256"] == _HASH
    assert stale == ()


def test_profile_refuses_stale_evidence_in_matching_package() -> None:
    inventory = _inventory(("pyyaml", "6.0.3", _HASH))
    policy = _policy(("pyyaml==6.0.3", "allow", "b" * 64))

    with pytest.raises(LicensePolicyProfileError, match="stale or mismatched"):
        project_policy(inventory, policy)


def test_profile_can_explicitly_omit_stale_reviews() -> None:
    inventory = _inventory(("pyyaml", "6.0.3", _HASH))
    policy = _policy(("pyyaml==6.0.3", "allow", "b" * 64))

    result, stale = project_policy(inventory, policy, omit_stale_reviews=True)

    assert result["reviews"] == {}
    assert stale == ("pyyaml==6.0.3",)


def test_profile_does_not_create_a_review_for_unreviewed_package() -> None:
    inventory = _inventory(("new-package", "1.0", _HASH))

    result, stale = project_policy(inventory, _policy())

    assert result["reviews"] == {}
    assert stale == ()


def test_profile_rejects_duplicate_inventory_identity() -> None:
    inventory = _inventory(("duplicate", "1.0", _HASH), ("duplicate", "1.0", _HASH))

    with pytest.raises(LicensePolicyProfileError, match="duplicate inventory package"):
        project_policy(inventory, _policy())


def test_profile_requires_project_notice_rationale() -> None:
    policy = _policy()
    policy["project_notice_rationale"] = "  "

    with pytest.raises(LicensePolicyProfileError, match="NOTICE rationale"):
        project_policy(_inventory(("pkg", "1.0", _HASH)), policy)
