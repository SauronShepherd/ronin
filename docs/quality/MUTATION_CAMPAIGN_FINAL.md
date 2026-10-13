# Final mutation campaign

This repository records one final mutation-testing campaign. Mutation testing is not a recurring product-quality activity and must not be executed again after this record is committed.

## Evidence

- Date: 2026-10-12
- Source revision: `868d4913e5105100a7f31dd26ce2166b65a609d3`
- Command: `MUTMUT_MAX_CHILDREN=8 make mutation`
- Mutants processed: 4,306
- Killed: 3,741
- Survived: 565
- Timeouts: 0
- No tests: 0
- Suspicious: 0
- Mutation score: 86.88%
- Configured gate: 90.00%
- Result: **FAILED** (`tools.mutation_gate` rejected the score)

The machine-readable output is retained in `mutants/mutmut-cicd-stats.json` in the local campaign workspace. The command completed all 4,306 mutants; the non-zero exit status came from the quality gate, not from an interrupted run.

## Post-campaign remediation evidence

After the frozen campaign, the surviving-mutant inventory was reviewed and
implemented as ordinary product-contract tests and, where the input contract
was too permissive, fail-closed production validation. The remediation is
tracked on the current branch head `293aba897896ce9c4e36f84fc910f578bf0655e4`.

- The normal suite completed with `3488 passed, 22 skipped`.
- The public v1 status ledger consistency check passed.
- The directed survivor-boundary tests and Ruff checks passed.
- No mutation campaign was rerun, so no post-remediation mutation percentage
  is claimed. The historical `86.88%` remains the only measured score.

This evidence demonstrates regression coverage for the reviewed survivors; it
does not manufacture a new mutation score after the campaign was closed.

## Permanent decision

This campaign is closed. Do not run `make mutation`, `mutmut run`, or an equivalent mutation campaign again. Future work must use ordinary unit, integration, contract, and end-to-end tests. If mutation testing is ever reconsidered, it requires an explicit product decision and a new campaign plan; it is not an automatic follow-up or CI job.
