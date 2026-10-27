# Ronin release runbook

This runbook describes the intended v0.1 release sequence for the independent Ronin project. Ronin intentionally has no continuous integration: all qualification is run and recorded manually on the exact candidate. This runbook does not claim that current `main` is release-ready.

## Release identity

Use semantic version tags. The v0.1 release line is `v0.1.0`; current development remains alpha (`0.1.0a*`). A release candidate is always one exact Git commit SHA plus the exact artifacts built from that SHA.

Do not rebuild between qualification and publication. Wheel, sdist, container image, SBOM, provenance/attestation, and any release evidence must bind to the exact candidate identities that were qualified.

## Preconditions

Before a v0.1 release-readiness claim:

1. The maintainer must complete the manual qualification sequence below and record each command, environment, result, skip, candidate SHA, and artifact digest in one candidate-bound report. No workflow result is required or produced.
2. The frozen v0.1 journey must execute 15/15 on one exact candidate SHA with zero skip, xfail, failure, error, missing, or unexpected result (#57/#202/#96).
3. The exact `pyronin` artifact intended for publication must be clean-installed and qualified outside the checkout, then published unchanged (#95).
4. Direct and transitive dependency/license evidence must be generated from the exact resolved environment and reviewed; NOTICE/attribution decisions must be evidence-based (#58).
5. `main` and semantic release refs must be protected and verified before `v0.1.0`, no later than 2026-11-01, per ADR-V01-008 (#63).
6. Security reporting policy requires a real verified private reporting route before `SECURITY.md` can truthfully advertise one (#45).

If any precondition is unmet, stop and record the blocker. Do not weaken a gate or fabricate evidence to continue.

## Candidate preparation

1. Select the exact candidate SHA from `main`.
2. Confirm the working tree and release metadata correspond to that SHA.
3. Build candidate artifacts once in the isolated release path.
4. Record immutable identities for wheel, sdist, container image, lockfile, runtime/toolchain, and any generated legal evidence.
5. Preserve the exact artifacts for all subsequent qualification and publication steps.

## Qualification sequence

Run and record each applicable step locally against the same candidate SHA:

1. Run source, unit, integration, formatting, lint, typing, architecture, and OpenAPI checks using the local commands in `CONTRIBUTING.md` and `DEVELOPMENT_QUALIFICATION.md`.
2. Run local secret/dependency scans and review the candidate's complete diff and history.
3. Run the real-Docker qualification script for worker/container/runtime invariants and PostgreSQL-backed storage.
4. Run the frozen v0.1 acceptance journey; all 15 named steps must execute with no skip, xfail, failure, error, missing, or unexpected result.
5. Build the exact `pyronin` artifact once and qualify the installed artifact outside the checkout.
6. Complete license/NOTICE/attribution review using the exact resolved dependencies and built artifacts.
7. Generate artifact identity, SBOM, provenance, and any required attestations locally; record their hashes and source SHA.
8. Publish only after every report is manually reviewed and binds to the same candidate SHA and exact artifacts.

Historical runs from earlier SHAs are context, not qualification for the current candidate.

## Maintainer actions versus automation

The following require explicit maintainer action or decision even when automation is active:

- authorize the release candidate;
- complete legal/license review where policy requires human judgment;
- verify the private security-reporting channel;
- verify repository/ref protection and bypass policy;
- approve publication and any rollback/revocation action.

Automation may build, verify, retain evidence, and publish only within the permissions and gates explicitly configured for the release process.

## Publication

Publish only artifacts already qualified. Do not rebuild a wheel, sdist, or image during the publication step. Record the source tag/SHA and immutable artifact identities in release notes.

Release notes must link to installation/first-run guidance, public API/CLI/SDK documentation, known limitations, compatibility notes, and migrations where applicable.

## Failure and rollback

If any required qualification fails, stop publication. Fix the underlying issue on a new commit and qualify a new exact candidate; do not reuse evidence from the rejected candidate.

If a published artifact must be withdrawn or superseded, preserve the audit trail and release notes explaining the affected version and corrective release. Semantic tags must not be silently repointed.

## Post-release verification

After publication, verify that:

- the released tag resolves to the intended source SHA;
- published artifact digests match qualified identities;
- installation uses the published artifact rather than the checkout;
- release notes and changelog identify breaking changes, features, fixes, security-relevant changes, and known limitations accurately;
- repository/ref protection remains in force.

## Current code-only state

This runbook is an operational contract, not evidence that current `main` has
passed every release gate. There are no qualification workflows. Do not make a
release-readiness claim until every manual gate above is complete with candidate-
bound evidence and the maintainer has recorded the release decision.
