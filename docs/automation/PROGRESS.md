# Autonomous build progress

## Current stage

**E0 — Foundation**

The repository began with only `LICENSE`. No legacy product implementation is assumed to exist here. Work therefore starts from executable foundations rather than applying fixes from the historical Fakebrick review to absent code.

## 2026-09-02 — Foundation baseline

Completed in this increment:

- Added the Python package layout rooted at `python/` with `studio_core` as the first pure-domain package.
- Added Ruff, mypy strict and pytest configuration in `pyproject.toml`.
- Added an executable AST-based pure-domain I/O architecture gate.
- Added negative tests proving the gate catches forbidden SQLite/file access and environment access.
- Added a GitHub Actions quality workflow covering format, lint, strict typing, architecture contracts and tests.
- Added `Makefile`, repository status README, durable backlog and decision log for subsequent autonomous runs.

Publication history and evidence:

1. `9d9e55f812946b06792cc1ece8c627206c6e37bc` — initial E0 foundation. CI correctly failed at lint.
2. `83dad35bd1c3688310ca6add34c84de770eb8d70` — converted architecture tests to pytest style, explicitly allowed test assertions for Bandit rule S101, and fixed modern typing import. CI passed format, lint, mypy and architecture, then exposed a pytest import-path issue.
3. `a55d58a128c9bcf2b5f253756cf4a43951beb379` — made test invocation deterministic with `python -m pytest`. This is the final verified product-code SHA for the first execution.

Verified gates on `a55d58a128c9bcf2b5f253756cf4a43951beb379`:

- GitHub Actions `Format`: success.
- GitHub Actions `Lint`: success.
- GitHub Actions `Types` (`mypy` strict): success.
- GitHub Actions `Architecture contracts`: success.
- GitHub Actions `Tests`: success.
- Local stdlib checks before publication: `python -m compileall -q python tools tests`, `python tools/architecture_gate.py python/studio_core`, TOML parsing, and direct execution of all three architecture test functions.

Local installation of Ruff/mypy/pytest was attempted but the execution environment could not resolve package-index DNS. This did not reduce the gate: GitHub Actions installed the declared dependencies and supplied the authoritative full-toolchain result.

No issue was opened in this run because no separable product defect remained unresolved: both problems discovered by CI were corrected within the same E0 increment.

## 2026-09-02 — Package dependency contracts and negative gates

Completed in this increment:

- Extended `tools/architecture_gate.py` from a pure-I/O check into the executable package-dependency matrix defined by the technical architecture.
- Declared allowed imports for `studio_core`, notebook, codegen, bridge, native, debug, runners, kernel, orchestrator, storage, server and CLI layers before those packages are implemented.
- Added explicit failures for undeclared `studio_*` packages and unknown project imports, preventing new layers from appearing outside the architecture by accident.
- Hardened pure-domain I/O detection to catch `os.environ` through aliases and `from os import environ`, in addition to direct access.
- Added `tools/gates_negative.py` and a dedicated GitHub Actions `gates-negative` job. It proves the architecture gate rejects deliberate forbidden-I/O, environment-access and forbidden-layer fixtures.
- Expanded architecture tests to cover allowed dependencies, forbidden dependencies, undeclared packages and negative-gate behavior.
- Added `tools/__init__.py` and explicit `argparse` typing so repository tooling itself passes `mypy --strict`.

Publication history and evidence:

1. `3ae0db949c6aaad15598b178956a12e14adf4749` — dependency contracts and negative-gate job. The new negative gate passed; the quality job correctly rejected non-canonical formatting.
2. `cc1980e8caeed2ab1febab0bf590e250fbcc7ea0` — normalized formatter output. Format and lint passed; strict mypy then exposed package/typing ambiguity in the tooling.
3. `94c01b16b4eb4e8994928192272585d2d267f217` — made tooling an explicit package and removed the strict-typing ambiguity.

Verified gates on `94c01b16b4eb4e8994928192272585d2d267f217`:

- GitHub Actions `quality`: success.
- `Format`: success.
- `Lint`: success.
- `Types` (`mypy --strict`): success.
- `Architecture contracts`: success.
- `Tests`: success.
- GitHub Actions `gates-negative`: success; all deliberate architecture violations were rejected.

The intermediate failures were corrected without weakening any rule. They are retained in history as evidence that format, typing and negative gates are active rather than decorative.

No issue was opened because no separable defect remains unresolved from this increment. The next highest-value E0 work is security/static gate expansion and documentation/governance contracts before starting E1.
