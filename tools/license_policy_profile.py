"""Project existing license reviews into one exact environment inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class LicensePolicyProfileError(ValueError):
    """Raised when a profile cannot safely preserve existing review evidence."""


def project_policy(
    inventory: object,
    policy: object,
    *,
    omit_stale_reviews: bool = False,
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Filter reviews without creating decisions or carrying stale evidence."""
    if not isinstance(inventory, dict) or inventory.get("schema_version") != 1:
        raise LicensePolicyProfileError("inventory schema_version must be 1")
    packages = inventory.get("packages")
    if not isinstance(packages, list):
        raise LicensePolicyProfileError("inventory packages must be a list")
    evidence_by_key: dict[str, str] = {}
    for package in packages:
        if not isinstance(package, dict):
            raise LicensePolicyProfileError("inventory package must be an object")
        name = package.get("package")
        version = package.get("version")
        digest = package.get("evidence_sha256")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(version, str)
            or not version.strip()
            or not isinstance(digest, str)
            or not digest.strip()
        ):
            raise LicensePolicyProfileError("inventory package identity and evidence are required")
        key = f"{name}=={version}"
        if key in evidence_by_key:
            raise LicensePolicyProfileError(f"duplicate inventory package: {key}")
        evidence_by_key[key] = digest

    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise LicensePolicyProfileError("policy schema_version must be 1")
    notice = policy.get("project_notice")
    rationale = policy.get("project_notice_rationale")
    reviews = policy.get("reviews")
    if notice not in {"required", "not_required"}:
        raise LicensePolicyProfileError("project NOTICE decision is unresolved")
    if not isinstance(rationale, str) or not rationale.strip():
        raise LicensePolicyProfileError("project NOTICE rationale is required")
    if not isinstance(reviews, dict):
        raise LicensePolicyProfileError("policy reviews must be an object")

    projected: dict[str, Any] = {}
    stale: list[str] = []
    for key in sorted(set(evidence_by_key) & set(reviews)):
        review = reviews[key]
        if not isinstance(review, dict):
            raise LicensePolicyProfileError(f"review entry must be an object: {key}")
        if review.get("evidence_sha256") != evidence_by_key[key]:
            if omit_stale_reviews:
                stale.append(key)
                continue
            raise LicensePolicyProfileError(f"review evidence is stale or mismatched: {key}")
        projected[key] = review

    return (
        {
            "schema_version": 1,
            "project_notice": notice,
            "project_notice_rationale": rationale,
            "reviews": projected,
        },
        tuple(stale),
    )


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LicensePolicyProfileError(f"cannot read valid JSON: {path}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--source-policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--omit-stale-reviews",
        action="store_true",
        help="omit mismatched review digests so they require fresh maintainer review",
    )
    args = parser.parse_args()
    try:
        result, stale = project_policy(
            _read_json(args.inventory),
            _read_json(args.source_policy),
            omit_stale_reviews=args.omit_stale_reviews,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except LicensePolicyProfileError as exc:
        parser.error(str(exc))
    reviews = result["reviews"]
    if not isinstance(reviews, dict):
        raise LicensePolicyProfileError("projected reviews must be an object")
    packages = _read_json(args.inventory)
    package_entries = packages["packages"] if isinstance(packages, dict) else []
    print(
        f"license policy profile: retained {len(reviews)} existing reviews for "
        f"{len(package_entries)} packages; omitted stale reviews={len(stale)}; "
        "no decisions created"
    )
    if stale:
        print("stale review decisions require fresh maintainer review: " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
