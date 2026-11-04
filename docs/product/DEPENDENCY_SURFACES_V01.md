# Dependency qualification surfaces v0.1

Status: **code-level contract; exact legal evidence pending**.

Ronin keeps four dependency surfaces distinct instead of pretending they are one environment:

1. `requirements-dev.lock` is the hash-locked development/resolved graph used by the existing license inventory tooling.
2. PEP 517 `build-system.requires` in the root and `packages/pyronin/pyproject.toml` is an isolated build-tool surface.
3. `third_party/qualification-tools-v1.in` declares the exact release/security toolchain and its resolved dependency closure; `third_party/qualification-tools-v1.txt` is its universal hash-locked install surface.
4. The declared runtime surface is the root base dependency set plus every optional feature extra except `dev`; the retained security workflow audits this surface separately from development tools.
5. `docker/pip-bootstrap.lock` is the hash-locked, build-only pip installer used to construct the runtime/probe images. Pip, setuptools, wheel and its bootstrap tooling are removed from the final images so the runtime contains only Ronin and its declared runtime dependencies.

`python -m tools.dependency_surfaces` (or `make dependency-surfaces-check`) validates surfaces 2 and 3 using only the standard library. Every active entry must be an exact `name==version` pin. Ranges, direct/VCS URLs, environment markers, extras, duplicates and conflicting build-system versions fail closed rather than being normalized or ignored.

At the current repository state the build-system surface resolves to `setuptools==84.2.1` in both project files. The retained qualification definitions explicitly install `build==1.6.0`, `pytest==8.4.2` and `pip-audit==2.10.1`; those exact tool identities and the complete pinned dependency closure are recorded separately because qualification tooling may intentionally use versions different from the developer lock. Regenerate the universal hash lock from the `.in` file with `uv pip compile third_party/qualification-tools-v1.in --no-deps --universal --generate-hashes --python-version 3.11 --no-annotate --no-header --output-file <temporary-lock>`, then preserve the two explanatory header lines in the committed `.txt`. The runtime audit derives its requirement file directly from `pyproject.toml` so feature extras cannot silently escape vulnerability review.

This contract does **not** claim that any of those packages were installed or legally approved in this execution. It does not fabricate `third_party/licenses-v1.json`, package review decisions, NOTICE obligations, attribution text or artifact hashes. Those outputs require the exact resolved/qualification environments plus maintainer legal review, as described in `LICENSE_QUALIFICATION_V01.md`.

If a retained release/security definition changes its explicitly installed Python tool set or a transitive pin, update the `.in` input and regenerate the `.txt` lock in the same reviewed slice. Validate the result with `python -m pip install --require-hashes -r third_party/qualification-tools-v1.txt`. The build-only container bootstrap lock has no transitive requirements and must also be installed with `--require-hashes`; update it from a verified wheel checksum and scan the built images. When execution-derived qualification is restored, exact package/license evidence for these separate surfaces must be bound to the actual candidate environment rather than inferred from this declaration alone.
