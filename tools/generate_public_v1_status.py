"""Synchronize observed source metadata in the Public v1 ledgers."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = ROOT / "docs/product/PUBLIC_V1_IMPLEMENTATION_STATUS.md"
MACHINE = ROOT / "docs/product/public-v1-status.json"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
HEAD_PATTERN = re.compile(r"(?m)^(\*\*Observed source head:\*\* `)[0-9a-f]{40}(` \()[^)]+(\)\.)$")


def _read_observed() -> tuple[str, str]:
    machine = json.loads(MACHINE.read_text(encoding="utf-8"))
    markdown = MARKDOWN.read_text(encoding="utf-8")
    match = HEAD_PATTERN.search(markdown)
    if match is None:
        raise ValueError("human ledger must contain one observed source head")
    return machine["observed_main_sha"], match.group(0).split("`")[1]


def synchronize(sha: str, observed_at: str) -> None:
    if not SHA_PATTERN.fullmatch(sha):
        raise ValueError("sha must be a 40-character lowercase hexadecimal Git SHA")
    datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    machine = json.loads(MACHINE.read_text(encoding="utf-8"))
    if machine.get("schema_version") != 1:
        raise ValueError("unsupported Public v1 ledger schema")
    markdown = MARKDOWN.read_text(encoding="utf-8")
    updated, count = HEAD_PATTERN.subn(
        rf"\g<1>{sha}\g<2>{observed_at[:10]}\g<3>", markdown, count=1
    )
    if count != 1:
        raise ValueError("human ledger must contain one observed source head")
    machine["observed_main_sha"] = sha
    machine["observed_at"] = observed_at
    MACHINE.write_text(json.dumps(machine, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    MARKDOWN.write_text(updated, encoding="utf-8")


def check() -> None:
    machine_sha, markdown_sha = _read_observed()
    if machine_sha != markdown_sha:
        raise SystemExit("Public v1 status ledgers disagree on observed source SHA")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sha", nargs="?")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--observed-at",
        default=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    args = parser.parse_args()
    if args.check:
        check()
        return 0
    if args.sha is None:
        parser.error("sha is required unless --check is used")
    synchronize(args.sha, args.observed_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
