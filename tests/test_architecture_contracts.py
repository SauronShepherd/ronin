from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.architecture_gate import inspect_file, inspect_roots


class ArchitectureGateTests(unittest.TestCase):
    def test_current_domain_is_free_of_forbidden_io(self) -> None:
        self.assertEqual(inspect_roots([Path("python/studio_core")]), [])

    def test_gate_fails_on_deliberate_forbidden_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad_domain.py"
            path.write_text("import sqlite3\nopen('state.txt')\n", encoding="utf-8")

            violations = inspect_file(path)

        self.assertEqual({violation.rule for violation in violations}, {"IO001", "IO002"})

    def test_gate_rejects_environment_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad_env.py"
            path.write_text("import os\nvalue = os.environ['TOKEN']\n", encoding="utf-8")

            violations = inspect_file(path)

        self.assertEqual([violation.rule for violation in violations], ["IO003"])


if __name__ == "__main__":
    unittest.main()
