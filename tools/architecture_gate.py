"""Executable architecture contracts for Ronin Studio packages."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

PROJECT_DEPENDENCIES: dict[str, frozenset[str]] = {
    "studio_core": frozenset[str](),
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
PURE_STDLIB_IMPORT_ROOTS = frozenset(
    {
        "__future__",
        "abc",
        "ast",
        "bisect",
        "collections",
        "copy",
        "dataclasses",
        "decimal",
        "enum",
        "fractions",
        "functools",
        "hashlib",
        "heapq",
        "itertools",
        "json",
        "math",
        "operator",
        "re",
        "typing",
    }
)
PURE_STDLIB_EXACT_IMPORTS = frozenset({"urllib.parse"})
NONDETERMINISTIC_IMPORT_ROOTS = frozenset({"datetime", "random", "secrets", "time", "uuid"})
NONDETERMINISTIC_CALLS = frozenset(
    {
        "datetime.datetime.now",
        "datetime.datetime.today",
        "datetime.datetime.utcnow",
        "os.urandom",
        "random.random",
        "random.randrange",
        "random.randint",
        "secrets.token_bytes",
        "secrets.token_hex",
        "secrets.token_urlsafe",
        "time.monotonic",
        "time.time",
        "uuid.uuid1",
        "uuid.uuid4",
    }
)
ENVIRONMENT_NAMES = frozenset({"os.environ", "os.getenv"})
FORBIDDEN_OS_CALLS = frozenset(
    {
        "os.mkdir",
        "os.makedirs",
        "os.popen",
        "os.remove",
        "os.removedirs",
        "os.rename",
        "os.replace",
        "os.rmdir",
        "os.system",
        "os.unlink",
    }
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    rule: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.detail}"


def _source_package(path: Path, root: Path | None = None) -> str | None:
    if root is not None:
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            relative = path
        if relative.parts:
            candidate = relative.parts[0]
            return candidate if candidate.startswith("studio_") else None
    return next(
        (part for part in reversed(path.parent.parts) if part.startswith("studio_")),
        None,
    )


def _project_package(module: str) -> str | None:
    root = module.split(".", maxsplit=1)[0]
    return root if root.startswith("studio_") else None


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


def _allowed_pure_import(module: str) -> bool:
    root = module.split(".", maxsplit=1)[0]
    return root in PURE_STDLIB_IMPORT_ROOTS or module in PURE_STDLIB_EXACT_IMPORTS


def _pure_domain_violations(tree: ast.AST, path: Path, source: str | None) -> list[Violation]:
    if source not in PURE_DOMAIN_PACKAGES:
        return []

    aliases = _collect_aliases(tree)
    violations: list[Violation] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
            if node.module == "os" and any(
                alias.name in {"environ", "getenv"} for alias in node.names
            ):
                violations.append(
                    Violation(path, node.lineno, "IO003", "environment access is forbidden")
                )

        for module in modules:
            root = module.split(".", maxsplit=1)[0]
            if root.startswith("studio_"):
                continue
            if root in NONDETERMINISTIC_IMPORT_ROOTS:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "IO004",
                        f"nondeterministic import {module!r} is forbidden in pure domain code",
                    )
                )
            elif root == "os":
                continue
            elif not _allowed_pure_import(module):
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "IO001",
                        f"import {module!r} is not allowed in pure domain code",
                    )
                )

        if isinstance(node, ast.Call):
            name = _dotted_name(node.func, aliases)
            if name in {"open", "builtins.open"}:
                violations.append(Violation(path, node.lineno, "IO002", f"forbidden call {name!r}"))
            elif name in ENVIRONMENT_NAMES:
                violations.append(
                    Violation(path, node.lineno, "IO003", "environment access is forbidden")
                )
            elif name in NONDETERMINISTIC_CALLS:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "IO004",
                        f"nondeterministic call {name!r} is forbidden in pure domain code",
                    )
                )
            elif name in FORBIDDEN_OS_CALLS:
                violations.append(
                    Violation(path, node.lineno, "IO001", f"forbidden side-effect call {name!r}")
                )
        elif isinstance(node, ast.Attribute):
            name = _dotted_name(node, aliases)
            if name == "os.environ":
                violations.append(
                    Violation(path, node.lineno, "IO003", "environment access is forbidden")
                )

    return violations


def inspect_file(path: Path, *, root: Path | None = None) -> list[Violation]:
    try:
        source_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [Violation(path, 1, "PARSE001", f"source is not valid UTF-8: {exc}")]
    try:
        tree = ast.parse(source_text, filename=str(path))
    except SyntaxError as exc:
        return [
            Violation(
                path,
                exc.lineno or 1,
                "PARSE001",
                f"source contains invalid Python syntax: {exc.msg}",
            )
        ]
    source = _source_package(path, root)
    return _dependency_violations(tree, path, source) + _pure_domain_violations(tree, path, source)


def iter_python_files(roots: Iterable[Path]) -> Iterable[tuple[Path, Path]]:
    for root in roots:
        if not root.exists():
            continue
        yield from (
            (root, path) for path in sorted(root.rglob("*.py")) if "__pycache__" not in path.parts
        )


def inspect_roots(roots: Iterable[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for root, path in iter_python_files(roots):
        violations.extend(inspect_file(path, root=root))
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
    roots = cast(list[Path], args.roots)
    return run_gate(roots)


if __name__ == "__main__":
    raise SystemExit(main())
