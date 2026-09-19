# ADR-V01-013 — Namespaced runtime capabilities and explicit ambiguity

**Status:** Accepted — 2026-09-18

**Resolves:** #50

## Decision

Ronin keeps one local/container runtime in v0.1 and does not add another
provider to manufacture conformance evidence. Runtime capability identity is
namespaced: canonical Ronin capabilities use the `ronin.core` namespace and a
versioned capability key; adapter-specific capabilities use an explicit
`adapter.<adapter-id>` namespace and are never silently interpreted as core
capabilities.

Capability values remain immutable typed contract values at the boundary. The
initial core families are boolean presence, bounded strings, and comparable
release values. Version constraints use the existing provider-neutral release
comparison rules; units and provider-specific ordering semantics stay outside
the core vocabulary. Unknown capability families, namespaces, constraint
versions, and units fail closed as an unsatisfied requirement with recorded
evidence. They are not silently coerced or treated as a newer compatible
version.

Resolution has three meaningful outcomes: `selected`, `no_match`, and
`ambiguous`. Equal compatible candidates with the same preference score are
ambiguous and are rejected; adapter and profile identifiers are canonicalized
for evidence ordering only, never used as a semantic preference. Explicit
profile pinning remains authoritative and must still satisfy the requested
requirements.

Every resolution snapshot records the requested capability requirements,
candidate evaluations, selected or ambiguous outcome, policy version, and the
canonical catalog identity used for evaluation. Dispatch must revalidate the
selected profile against the same catalog identity and capability evidence;
material drift fails closed instead of silently executing against a different
profile.

## Consequences

The existing single-runtime path remains compatible at the adapter boundary,
but its free-form capability representation must be migrated to the
namespaced/versioned form before a second runtime or remote adapter is
supported. Pure synthetic-adapter fixtures must cover namespace collisions,
incomparable values, equal candidates, unavailable profiles, explicit pinning,
and required-versus-preferred requirements. No provider-specific capability
implementation is part of v0.1.

## Alternatives rejected

- Choosing the lexicographically smallest adapter/profile as a semantic tie
  breaker.
- Treating unknown namespaces or constraint versions as compatible.
- Adding a second runtime before the public capability contract is stable.
