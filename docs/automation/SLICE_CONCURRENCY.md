# Builder slice concurrency

**Decision:** accepted — 2026-09-06

Ronin relaxes global single-writer serialization to **single writer per file domain**. The domains and claim rules are normative in `BUILDER_OPERATING_RULES.md`.

## Rationale

The prior global rule prevented independent work from progressing concurrently even when slices touched disjoint architectural packages. Ronin's executable dependency matrix already keeps those package groups structurally separated, so file-domain claims provide a bounded concurrency model without permitting two autonomous writers to edit the same surface.

## Safety rules

- One open Builder PR per claimed domain.
- A multi-domain slice claims every affected domain.
- Claims are stated in the PR body via `Builder-Domains:`.
- Conflicts are resolved by rebasing the later claimant; no force merge over newer domain work.
- `infra` changes that alter shared CI/release policy may not run concurrently with another `infra` Builder PR.
- `main` and release/tag publication continue to receive full, unfiltered qualification.

## Revisit trigger

Revisit after v0.1.0 or after the first two material cross-domain conflicts, whichever occurs first. If conflict/rebase cost erases throughput gains, return to global single-writer until the domain map is refined.
