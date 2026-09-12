## Scope

Describe the smallest coherent change in this pull request and its explicit non-goals.

## Related issue / prior discussion

Link the issue or design discussion that owns this work. Substantial architecture or product changes should have public discussion before implementation.

## Compatibility and identity impact

State any effect on HTTP/OpenAPI/CLI/SDK compatibility, durable state, canonical JSON bytes/digests, migrations, evidence identity, or public contracts. Write `none` only when that has been checked.

## Evidence actually obtained

List only checks, inspections, or qualification that were actually performed. Do not claim CI, tests, Docker, coverage, mutation, or release evidence if they were not run.

## Known validation gaps

State what remains unverified, especially while GitHub Actions and automated tests are disabled.

## Architecture / security invariants

Confirm relevant invariants remain intact: package layering, fail-closed validation, lease fencing, durable storage settings, evidence privacy, and no new runtime dependency unless explicitly accepted.

## Completion

- [ ] The change stays within accepted project scope.
- [ ] No unrelated feature work was added.
- [ ] Documentation/contracts were updated if observable behavior changed.
- [ ] Evidence claims are exact and do not overstate release readiness.
- [ ] The source branch should be deleted after merge when no unmerged work remains.
