# Ronin release runbook

This runbook describes the intended v0.1 release sequence for the independent Ronin project. It does not claim that current `main` is release-ready. Required automated qualification is presently disabled and must be restored before publication.

## Release identity

Use semantic version tags. The v0.1 release line is `v0.1.0`; current development remains alpha (`0.1.0a*`). A release candidate is always one exact Git commit SHA plus the exact artifacts built from that SHA.

Do not rebuild between qualification and publication. Wheel, sdist, container image, SBOM, provenance/attestation, and any release evidence must bind to the exact candidate identities that were qualified.

## Preconditions

Before a v0.1 release-readiness claim:

1. Required CI, Security, Docker, release qualification, and prerelease publication automation must be restored or replaced by equivalent enforceable automation under maintainer authorization (#199).
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

When automation is restored, the required sequence is:

1. source/unit/integration qualification and architecture gates;
2. Security qualification including secret/dependency scanning and candidate-history coverage;
3. real-Docker qualification for worker/container/runtime invariants;
4. strict frozen v0.1 acceptance with all 15 named steps executed;
5. exact installed-artifact qualification for `pyronin` outside the checkout;
6. license/NOTICE/attribution qualification bound to exact dependency and artifact evidence;
7. release artifact identity, SBOM, provenance, and attestation generation;
8. publication only after all required evidence refers to the same candidate SHA and exact artifacts.

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

At the time this runbook was added, GitHub Actions and automated tests are intentionally disabled. Therefore this document is an operational contract for the future release gate, not evidence that current `main` has passed it. Do not make a new release-readiness claim until #199 and its dependent qualification blockers are resolved with exact-SHA evidence.
