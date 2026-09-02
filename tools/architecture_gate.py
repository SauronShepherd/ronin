"""Executable architecture contracts for Ronin Studio packages."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PROJECT_DEPENDENCIES: dict[str, frozenset[str]] = {
    "studio_core": frozenset(),
    "studio_notebook": frozenset({"studio_core"}),
    "studio_codegen": frozenset({"studio_core"}),
    "studio_bridge": frozenset({"studio_core", "studio_notebook", "studio_codegen"}),
    "studio_native": frozenset({"studio_core"}),
    "studio_debug": frozenset(
        {"studio_core", "studio_notebook", "studio_codegen", "studio_native"}
    ),
    "studio_runners": frozenset({"studio_core", "studio_native"}),
    "studio_kernel": frozenset({"studio_core", "studio_notebook"}),
    "studio_orchestrator": frozenset({"studio_core", "studio_runners"}),
    "studio_storage": frozenset({"studio_core"}),
    "studio_server": frozenset(
        {
            "studio_core",
            "studio_notebook",
            "studio_codegen",
            "studio_bridge",
            "studio_native",
            "studio_debug",
            "studio_runners",
            "studio_kernel",
            "studio_orchestrator",
            "studio_storage",
        }
    ),
    "studio_cli": frozenset(
        {
            "studio_core",
            "studio_notebook",
            "studio_codegen",
            "studio_bridge",
            "studio_native",
            "studio_debug",
            "studio_runners",
            "studio_kernel",
            "studio_orchestrator",
            "studio_storage",
            "studio_server",
        }
    ),
}
PROJECT_PACKAGES = frozenset(PROJECT_DEPENDENCIES)
PURE_DOMAIN_PACKAGES = frozenset(
    {
        "studio_core",
        "studio_notebook",
        "studio_codegen",
        "studio_bridge",
        "studio_debug",
        "studio_native",
    }
)
FORBIDDEN_IMPORT_ROOTS = frozenset({"requests", "sqlite3", "subprocess", "urllib.request"})
FORBIDDEN_CALLS = frozenset({"open", "builtins.open"})


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    rule: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.detail}"


def _source_package(path: Path) -> str | None:
    return next((part for part in path.parts if part.startswith("studio_")), None)


def _project_package(module: str) -> str | None:
    root = module.split(".", maxsplit=1)[0]
    return root if root.startswith("studio_") else None


def _import_is_forbidden(module: str) -> bool:
    return any(module == root or module.startswith(f"{root}.") for root in FORBIDDEN_IMPORT_ROOTS)


def _collect_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:
                    root = alias.name.split(".", maxsplit=1)[0]
                    aliases[root] = root
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bound_name = alias.asname or alias.name
                aliases[bound_name] = f"{node.module}.{alias.name}"
    return aliases


def _dotted_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value, aliases)
        if parent is None:
            return None
        return f"{parent}.{node.attr}"
    return None


def _dependency_violations(tree: ast.AST, path: Path, source: str | None) -> list[Violation]:
    if source is None:
        return []
    if source not in PROJECT_DEPENDENCIES:
        return [Violation(path, 1, "DEP000", f"undeclared project package {source!r}")]

    violations: list[Violation] = []
    allowed = PROJECT_DEPENDENCIES[source]
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
        else:
            continue

        for module in modules:
            target = _project_package(module)
            if target is None or target == source:
                continue
            if target not in PROJECT_PACKAGES:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "DEP002",
                        f"unknown project import {target!r}",
                    )
                )
            elif target not in allowed:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "DEP001",
                        f"{source!r} may not import {target!r}",
                    )
                )
    return violations


def _io_violations(tree: ast.AST, path: Path, source: str | None) -> list[Violation]:
    if source not in PURE_DOMAIN_PACKAGES:
        return []

    aliases = _collect_aliases(tree)
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _import_is_forbidden(alias.name):
                    violations.append(
                        Violation(
                            path,
                            node.lineno,
                            "IO001",
                            f"forbidden import {alias.name!r}",
                        )
                    )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if _import_is_forbidden(node.module):
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "IO001",
                        f"forbidden import {node.module!r}",
                    )
                )
            if node.module == "os" and any(alias.name == "environ" for alias in node.names):
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "IO003",
                        "environment access is forbidden",
                    )
                )
        elif isinstance(node, ast.Call):
            name = _dotted_name(node.func, aliases)
            if name in FORBIDDEN_CALLS:
                violations.append(Violation(path, node.lineno, "IO002", f"forbidden call {name!r}"))
        elif isinstance(node, ast.Attribute):
            name = _dotted_name(node, aliases)
            if name == "os.environ":
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "IO003",
                        "environment access is forbidden",
                    )
                )
    return violations


def inspect_file(path: Path) -> list[Violation]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    source = _source_package(path)
    return _dependency_violations(tree, path, source) + _io_violations(tree, path, source)


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


def run_gate(roots: Iterable[Path]) -> int:
    violations = inspect_roots(roots)
    for violation in violations:
        print(violation.render())
    return 1 if violations else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, default=[Path("python")])
    args = parser.parse_args()
    return run_gate(args.roots)


if __name__ == "__main__":
    raise SystemExit(main())
