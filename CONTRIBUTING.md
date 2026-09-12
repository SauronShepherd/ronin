# Contributing to Ronin

Ronin is currently a single-maintainer alpha project with an autonomous build pipeline. Contributions from external participants are welcome. Automation may implement accepted work, but it does not create human governance authority, replace contributor authorship, or substitute for public technical discussion.

## Before you start

Use Python versions supported by the repository configuration and install the exact locked development environment rather than an approximate dependency set:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install -e . --no-deps
```

Docker is required for the supported local container journey. Go is required only for the independent canonical JSON cross-language checker. Runtime product packages intentionally add no third-party runtime dependencies.

## Current validation policy

GitHub Actions and automated repository qualification are currently disabled by maintainer policy. Do not interpret a code review or merged change as current release qualification. The retained workflow definitions live under `.github/workflows-disabled/` and must not be reactivated as part of unrelated contribution work.

Useful repository commands include:

```bash
make format
make lint
make typecheck
make architecture
make gates-negative
```

`make test`, coverage, mutation, Docker qualification, release qualification, and CI-derived evidence are separate validation surfaces. Under the current code-only policy, a contribution must state exactly which checks were actually executed and must not claim checks that were not run.

The pure-domain architecture boundary is executable in `tools/architecture_gate.py`. Preserve the package layering and fail-closed invariants documented under `docs/product/` and `docs/automation/`.

## Proposing changes

Use a public GitHub issue as the proposal venue for substantial architecture, product, compatibility, persistence, security-policy, or release-process changes. Describe the user problem, proposed boundary, compatibility impact, alternatives, and evidence before implementation begins.

Bounded fixes and already-accepted implementation slices may proceed directly through a pull request when they do not create new product scope or override an unresolved decision.

Ronin seeks consensus through public asynchronous discussion. When disagreement remains after the relevant evidence and alternatives are recorded, the current maintainer makes the project decision and records the rationale publicly. Decisions made privately or synchronously that materially affect the project must be summarized back into the repository record.

## Pull requests

Keep each pull request small and coherent. Include:

- the problem or issue being addressed;
- the exact scope and explicit non-goals;
- compatibility or identity impact;
- files and contracts affected;
- evidence actually obtained;
- known validation gaps;
- related issues or prior design discussion.

Do not mix formatting-only changes with semantic changes when doing so would make review materially harder. Do not weaken fail-closed behavior, durability, fencing, identity, or security controls merely to make validation easier.

## Architecture and compatibility expectations

`studio_core`, `studio_notebook`, and `studio_orchestrator` are pure-domain packages. Keep provider/framework I/O out of those packages. Preserve the dependency direction enforced by the architecture gate. Physical evidence locators are not canonical public identity. Worker writes remain lease-fenced and storage durability settings are not opportunistically relaxed.

Identity-bearing JSON must follow `docs/product/CANONICAL_JSON_V1.md`. A change that alters canonical bytes for an input already accepted by v1 requires an explicit new identity/schema version and migration; it is not a formatting change.

The public HTTP/OpenAPI/CLI/SDK compatibility policy is defined in `docs/product/API_COMPATIBILITY_V1.md`.

## Types of contribution

Useful contributions include code, documentation, bug reports, design review, conformance analysis, interoperability work, test work when the validation policy permits it, and community support. Responsibility may grow over time through sustained high-quality participation across any of these areas; Ronin does not use a rigid contribution-count threshold.

## Autonomous Builder boundary

The Ronin Autonomous Builder can implement work that has already been accepted within project scope. It must not invent community consensus, create maintainer authority, hide external contributor authorship, or turn unresolved human decisions into implementation assumptions.

## Security and conduct reporting

Do not post undisclosed security vulnerabilities in public issues. A project-level private security reporting route has not yet been selected and verified; issue #45 owns that decision. Until that decision is complete, the repository must not invent an email address or claim that a private GitHub reporting feature is enabled.

A project conduct policy with an owned reporting route is also still pending. Do not fabricate a private conduct-reporting channel while that route is unresolved.
