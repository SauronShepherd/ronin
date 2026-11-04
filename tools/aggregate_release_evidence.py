"""Merge exact-candidate evidence bundles and emit the authoritative verdict."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.release_evidence import (
    GATE_PROFILES,
    EvidenceError,
    merge,
    release_verdict,
    required_gates,
)


def main() -> int:
    parser = argparse.ArgumentParser(prog="aggregate-release-evidence")
    parser.add_argument("bundles", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verdict-output", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(GATE_PROFILES), default="release_required")
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        bundle = merge(args.bundles)
        if bundle["commit"] != args.expected_commit:
            raise EvidenceError(
                f"bundle commit {bundle['commit']!r} does not match expected commit "
                f"{args.expected_commit!r}"
            )
        if bundle.get("qualification_profile") != args.profile:
            raise EvidenceError(
                f"evidence profile {bundle.get('qualification_profile')!r} does not match "
                f"expected profile {args.profile!r}"
            )
        verdict = release_verdict(
            bundle,
            set(required_gates(args.profile)),
            expected_commit=args.expected_commit,
            expected_profile=args.profile,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.verdict_output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        args.verdict_output.write_text(
            json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(verdict, sort_keys=True))
        return 0
    except EvidenceError as exc:
        print(f"release evidence invalid: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
