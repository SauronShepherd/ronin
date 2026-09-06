# Ronin decisions — 2026-09-06

These decisions resolve the five open `NEEDS_DECISION` automation handoffs observed on `main` at `069023ea65923ac16640d139088f0ea1fc1358b5`. They are canonical supplements to `DECISIONS.md` and should be folded into that rolling log during the next consolidation pass.

## ADR-V01-006 — Runtime release comparison tolerates vendor decoration but exact equality stays exact

**Status:** Accepted  
**Resolves:** #50

For ordered runtime-version constraints, parse the leading run of purely numeric dot-separated release segments. A recognized prerelease marker immediately following the release (`dev`, `alpha`, `beta`, `rc`, `pre`, `a`, `b`, `c`) orders below the corresponding bare release. Other trailing text such as `.x-scala2.12`, `-LTS` or `+build.1` is vendor decoration and is ignored for ordering. Release tuples compare right-padded with zeros, so `3.5` and `3.5.0` are equal for ordered comparison.

If no leading numeric release is present, the advertised version is non-comparable; the requirement is unsatisfied with recorded evidence and must not raise an uncaught exception. Exact `==` remains exact string equality. No third-party version parser is imported into the pure package.

Acceptance vectors:

| Advertised | Constraint | Expected |
|---|---|---|
| `14.3.x-scala2.12` | `>=14.3` | satisfied |
| `14.3.x-scala2.12` | `>=14.4` | not satisfied |
| `3.11.9rc1` | `>=3.11` | satisfied |
| `3.11.0rc1` | `>=3.11.0` | not satisfied |
| `1.2.3-beta` | `>=1.2` | satisfied |
| `17-LTS` | `>=17` | satisfied |
| `3.5` | `>=3.5.0` | satisfied |
| `latest` | `>=1.0` | non-comparable / unsatisfied |
| empty string | any | rejected at construction |

This is a provider-neutral comparison rule. Adapter-specific semantic channels remain outside canonical core.

## ADR-V01-007 — Crash reclamation is attempt replacement, not policy retry

**Status:** Accepted  
**Resolves:** #92  
**Depends on implementation:** #49

- Lease TTL: 30 seconds.
- Heartbeat cadence: 10 seconds.
- Expired lease: current attempt becomes `abandoned`; the same logical Run returns to `pending` with `not_before = now` and a replacement Attempt may be created.
- `RetryPolicy.max_runs = 1` for v0.1 means no automatic policy retry after a completed cell/run failure. It does not disable crash reclamation of an abandoned attempt.
- Abandoned-attempt replacement does not spend the policy retry budget, but v0.1 caps one Run at 10 Attempts to prevent unbounded crash loops.
- Heartbeat/lease ownership loss while executing is fail-closed: cancel the session immediately and mark the attempt abandoned. Two workers must never knowingly continue the same Run.

The mandatory acceptance journey therefore remains possible even if ordinary policy retries are cut: worker loss creates Attempt #2 for the same Run; a normal failed Run does not automatically retry.

## ADR-V01-008 — Repository protection is deferred only until the v0.1 release gate

**Status:** Accepted risk with dated trigger  
**Resolves decision state:** #63

Keep `main` repository protection disabled during the autonomous v0.1 construction window to avoid introducing a human approval dependency into every Builder merge. Compensating controls are mandatory: Builder PRs are qualified on their exact head SHA, only owned Builder PRs may be autonomously merged, and the exact published `main` SHA is qualified after merge.

This is temporary. Protection for `main` and semantic release refs must be enabled and verified **before the `v0.1.0` tag is created, no later than 2026-11-01**. Release qualification must not treat this ADR as permanent acceptance of an unprotected release ref.

## ADR-V01-009 — Language-neutral runner protocol is post-v0.1 work

**Status:** Deferred  
**Resolves:** #62

Ronin v0.1 has one local Python-owned Docker runner. A language-neutral wire protocol designed before a second implementation exists would mostly encode the first implementation's assumptions. Defer protocol-family/schema/conformance work until after v0.1 and before the first non-Python or remote agent/runner implementation.

The current Python execution contracts remain local implementation details and must not be advertised as a stable wire protocol.

## ADR-V01-010 — Governance is intentionally lightweight and truthful

**Status:** Accepted  
**Resolves decision state:** #72

Until Ronin demonstrates sustained independent participation, governance is documented through the smallest truthful public surface rather than inventing committees or roles that do not exist. The contributor/governance slice is scoped to:

1. `CONTRIBUTING.md` — setup/PR workflow, public proposal venue, consensus-seeking/disagreement escalation, contribution-based path to greater responsibility, and the Autonomous Builder boundary.
2. `CODE_OF_CONDUCT.md` — project-appropriate behavioral expectations and reporting route.
3. `SECURITY.md` — private vulnerability reporting and disclosure expectations.
4. `README.md` navigation/status paragraph — Ronin is currently single-maintainer with an autonomous build pipeline; automation implements accepted work but does not create human governance authority.

Substantial architecture/product changes require prior public issue discussion; bounded fixes may proceed through normal PR review. Private/synchronous decisions that affect the project are summarized into the public repository record. Governance is revisited after sustained participation by multiple independent contributors.
