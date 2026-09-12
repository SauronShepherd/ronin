# Dependency qualification surfaces v0.1

Status: **code-level contract; exact legal evidence pending**.

Ronin keeps three dependency surfaces distinct instead of pretending they are one environment:

1. `requirements-dev.lock` is the hash-locked development/resolved graph used by the existing license inventory tooling.
2. PEP 517 `build-system.requires` in the root and `packages/pyronin/pyproject.toml` is an isolated build-tool surface.
3. `third_party/qualification-tools-v1.txt` records Python tools explicitly installed by the retained release/security qualification definitions when those definitions are active.

`python -m tools.dependency_surfaces` (or `make dependency-surfaces-check`) validates surfaces 2 and 3 using only the standard library. Every active entry must be an exact `name==version` pin. Ranges, direct/VCS URLs, environment markers, extras, duplicates and conflicting build-system versions fail closed rather than being normalized or ignored.

At the current repository state the build-system surface resolves to `setuptools==84.0.0` in both project files. The retained qualification definitions explicitly install `build==1.6.0`, `pytest==8.4.2` and `pip-audit==2.10.1`; those exact tool identities are recorded separately because qualification tooling may intentionally use a version different from the developer lock.

This contract does **not** claim that any of those packages were installed or legally approved in this execution. It does not fabricate `third_party/licenses-v1.json`, package review decisions, NOTICE obligations, attribution text or artifact hashes. Those outputs require the exact resolved/qualification environments plus maintainer legal review, as described in `LICENSE_QUALIFICATION_V01.md`.

If a retained release/security definition changes its explicitly installed Python tool set, `third_party/qualification-tools-v1.txt` must change in the same reviewed slice. When execution-derived qualification is restored, exact package/license evidence for these separate surfaces must be bound to the actual candidate environment rather than inferred from this declaration alone.
