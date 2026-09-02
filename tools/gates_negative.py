"""Prove that architecture gates reject deliberate violations."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.architecture_gate import inspect_file, run_gate

NEGATIVE_CASES: tuple[tuple[str, str, str], ...] = (
    ("forbidden-io", "import sqlite3\n", "IO001"),
    (
        "environment-alias",
        "from os import environ\nTOKEN = environ['TOKEN']\n",
        "IO003",
    ),
    ("forbidden-layer", "from studio_server import app\n", "DEP001"),
)


def run_negative_cases() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "python"
        package = root / "studio_core"
        package.mkdir(parents=True)

        for name, source, expected_rule in NEGATIVE_CASES:
            path = package / f"{name.replace('-', '_')}.py"
            path.write_text(source, encoding="utf-8")
            rules = {violation.rule for violation in inspect_file(path)}
            if expected_rule not in rules:
                failures.append(f"{name}: expected {expected_rule}, got {sorted(rules)}")
            path.unlink()

        combined = package / "combined.py"
        combined.write_text("import sqlite3\nfrom studio_server import app\n", encoding="utf-8")
        if run_gate([root]) == 0:
            failures.append("architecture gate returned success for deliberate violations")

    return failures


def main() -> int:
    failures = run_negative_cases()
    for failure in failures:
        print(failure)
    if failures:
        return 1
    print("all deliberate architecture violations were rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
