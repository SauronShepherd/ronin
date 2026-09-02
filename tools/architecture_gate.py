"""Executable architecture gate for pure domain packages."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "requests",
        "sqlite3",
        "subprocess",
        "urllib.request",
    }
)
FORBIDDEN_CALLS = frozenset({"open", "os.environ"})


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    rule: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.detail}"


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent is None:
            return None
        return f"{parent}.{node.attr}"
    return None


def _import_is_forbidden(module: str) -> bool:
    return any(module == root or module.startswith(f"{root}.") for root in FORBIDDEN_IMPORT_ROOTS)


def inspect_file(path: Path) -> list[Violation]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _import_is_forbidden(alias.name):
                    violations.append(
                        Violation(path, node.lineno, "IO001", f"forbidden import {alias.name!r}")
                    )
        elif isinstance(node, ast.ImportFrom) and node.module and _import_is_forbidden(node.module):
            violations.append(
                Violation(path, node.lineno, "IO001", f"forbidden import {node.module!r}")
            )
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name in FORBIDDEN_CALLS:
                violations.append(Violation(path, node.lineno, "IO002", f"forbidden call {name!r}"))
        elif isinstance(node, ast.Attribute):
            name = _dotted_name(node)
            if name == "os.environ":
                violations.append(
                    Violation(path, node.lineno, "IO003", "environment access is forbidden")
                )

    return violations


def iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        yield from sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def inspect_roots(roots: Iterable[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for path in iter_python_files(roots):
        violations.extend(inspect_file(path))
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, default=[Path("python/studio_core")])
    args = parser.parse_args()

    violations = inspect_roots(args.roots)
    for violation in violations:
        print(violation.render())
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
