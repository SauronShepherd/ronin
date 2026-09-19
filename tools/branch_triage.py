"""Classify remote branches by content relative to origin/main."""

# The subprocess calls below intentionally invoke the fixed git executable
# with refs obtained from git itself; shell interpolation is never used.
# ruff: noqa: S603, S607

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def git(*args: str) -> str:
    return subprocess.check_output(  # noqa: S603, S607 - fixed git executable and internal refs
        ("git", *args), text=True, encoding="utf-8"
    ).strip()


def triage(output: Path | None = None) -> tuple[list[str], list[str]]:
    refs = [
        ref
        for ref in git(
            "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"
        ).splitlines()
        if ref not in {"origin", "origin/HEAD", "origin/main"}
    ]
    identical: list[str] = []
    review: list[str] = []
    for ref in refs:
        branch = ref.removeprefix("origin/")
        result = subprocess.run(  # noqa: S603, S607 - fixed git executable and validated remote ref
            ("git", "diff", "--quiet", "origin/main", ref), check=False
        )
        (identical if result.returncode == 0 else review).append(branch)
    lines = [
        *(f"IDENTICA {branch}" for branch in sorted(identical)),
        *(f"REVISAR {branch}" for branch in sorted(review)),
    ]
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"branch triage: total={len(refs)} identical={len(identical)} review={len(review)}")
    return identical, review


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    triage(args.output)
