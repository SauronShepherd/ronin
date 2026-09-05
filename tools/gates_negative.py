"""Prove that architecture gates reject deliberate violations."""

from __future__ import annotations

import tempfile
from pathlib import Path

from tools.architecture_gate import inspect_file, run_gate

NEGATIVE_CASES: tuple[tuple[str, str, str, str], ...] = (
    ("forbidden-io", "studio_core", "import sqlite3\n", "IO001"),
    (
        "environment-alias",
        "studio_core",
        "from os import environ\nTOKEN = environ['TOKEN']\n",
        "IO003",
    ),
    ("forbidden-layer", "studio_core", "from studio_server import app\n", "DEP001"),
    ("low-level-os", "studio_core", "import os\nos.open('/etc/passwd', os.O_RDONLY)\n", "IO001"),
    ("pathlib-io", "studio_core", "from pathlib import Path\nPath('x').write_text('y')\n", "IO001"),
    ("unknown-layer", "studio_core", "from studio_marketing import spam\n", "DEP002"),
    (
        "layer-inversion",
        "studio_orchestrator",
        "from studio_storage import SqliteJobStore\n",
        "DEP001",
    ),
)


def run_negative_cases() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "python"

        for name, package_name, source, expected_rule in NEGATIVE_CASES:
            package = root / package_name
            package.mkdir(parents=True, exist_ok=True)
            path = package / f"{name.replace('-', '_')}.py"
            path.write_text(source, encoding="utf-8")
            rules = {violation.rule for violation in inspect_file(path)}
            if expected_rule not in rules:
                failures.append(f"{name}: expected {expected_rule}, got {sorted(rules)}")
            path.unlink()

        package = root / "studio_core"
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
