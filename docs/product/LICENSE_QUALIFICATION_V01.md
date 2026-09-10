# Ronin v0.1 third-party license qualification

Ronin v0.1 release qualification must tie third-party license evidence to the exact resolved dependency graph rather than to floating requirement ranges or a manually maintained package list.

## Source of dependency identity

`requirements-dev.lock` is the committed exact, hash-locked root development graph. Root and `pyronin` build backends are exact-pinned separately in their `pyproject.toml` files. `tools/license_qualification.py` treats the lock as authoritative for the resolved runtime/development dependency inventory and records both its exact package/version graph and SHA-256 of the complete lock-file bytes.

The lock parser is intentionally fail closed. It accepts only exact `name==version` requirement records that end in a line continuation and are followed immediately by one or more indented SHA-256 hash continuations; the final hash line closes the requirement block. Comments and blank lines are allowed only between complete requirement blocks. Any other active syntax, detached hash line, interrupted/unterminated continuation, range, direct URL, VCS/editable requirement, malformed hash line, or unrecognized active continuation fails qualification instead of being silently omitted from the inventory.

The inventory generator must run in an environment installed from that exact lock. It refuses missing distributions and version drift. The generated inventory records, for each locked distribution:

- normalized package name and exact version;
- whether the package is directly declared by root/SDK project dependency metadata represented by this lock;
- the installed distribution's declared license metadata;
- installed license/copying/notice/authors/copyright file paths plus SHA-256 of each file's exact installed bytes;
- an `evidence_sha256` over the canonical package/version/direct/source/license/license-file evidence record;
- the complete `requirements-dev.lock` SHA-256 binding the inventory to one exact lock revision.

The direct-dependency set is part of the qualification boundary. Every root or `pyronin` `[project]` dependency represented by this release qualification surface, including the root `dev` extra used to generate `requirements-dev.lock`, must also be present in the lock; otherwise inventory generation and qualification fail closed. The `direct` classification is not merely informational: qualification recomputes those direct dependency names from the same project metadata and rejects any inventory whose boolean classification differs.

PEP 517 `build-system.requires` is a separate exact-pinned build-tool surface and is not classified as a direct dependency of `requirements-dev.lock`, because the current lock is generated from `pyproject.toml --extra dev` and does not resolve the isolated build environment. Build-tool licensing/security evidence therefore remains an explicit release-tool exception/surface to reconcile before #58 is complete; this validator does not pretend the runtime/development lock contains those packages.

Generation command after installing the exact lock:

```bash
python tools/license_qualification.py --write-inventory third_party/licenses-v1.json
```

The generated file is evidence, not an approval decision.

## Fail-closed review policy

A release review must separately commit `third_party/license-policy-v1.json`. The policy is keyed by exact normalized `package==version`. Every locked distribution must record:

- an explicit `allow` or `deny` decision;
- the exact package `evidence_sha256` that was reviewed;
- `notice_required: true|false`;
- `attribution_required: true|false`;
- a non-empty review rationale grounded in the inspected upstream evidence.

Unknown, missing, duplicate, unreviewed, denied, graph-drifted, unsupported-lock-syntax, direct-dependency-omitted, direct/transitive-misclassified, or evidence-mismatched dependencies fail qualification. Missing source or declared-license metadata also fails qualification instead of being guessed from package name or ecosystem reputation.

The evidence binding is intentionally stronger than `package==version`. Reinstalling the same package/version from a different allowed artifact can expose different distribution metadata or legal files. If source metadata, declared license metadata, license-file paths, or license-file bytes change, the package `evidence_sha256` changes and the previous review becomes stale. The package must be reviewed again before qualification can pass. This prevents an approval of one observed artifact/evidence set from silently authorizing materially different license evidence for the same version.

The policy must additionally contain an explicit project-level `project_notice` decision (`required` or `not_required`) and a non-empty `project_notice_rationale`. This is the repository-backed conclusion about whether Ronin itself must ship a project `NOTICE` file for the reviewed resolved graph. Do not add Apache Software Foundation-style NOTICE boilerplate merely because Ronin uses Apache-2.0; the conclusion must come from obligations actually present in the reviewed graph and distributed artifacts.

Qualification command:

```bash
python tools/license_qualification.py
```

The command succeeds only when the committed inventory has the exact current lock SHA-256, every active requirement is an exact structurally valid hash-qualified dependency block, the inventory exactly matches the parsed locked graph, the lock covers every direct project dependency represented by that graph, direct/transitive classifications agree with project metadata, each package evidence digest is internally valid, and every exact dependency has a review bound to that exact evidence digest with complete license/notice/attribution decisions plus the project-level NOTICE rationale.

## Review requirements

A maintainer reviewing a generated inventory must inspect the referenced installed license/notice material and upstream distribution metadata before marking a package allowed. If metadata is ambiguous, contradictory, custom, missing, or potentially incompatible with Ronin's Apache-2.0 distribution, leave the package unapproved or deny it until resolved. Do not convert classifier text to an SPDX identifier unless upstream evidence supports that conclusion.

`notice_required` and `attribution_required` are separate review decisions. When either is true, the release process must preserve the required upstream text in the distributed artifact or companion material before #58 can be considered complete. The validator deliberately does not invent or auto-copy legal text from ambiguous metadata.

If the lock file changes for any reason, even without changing its parsed package/version set, the recorded lock SHA-256 changes and qualification fails until inventory evidence is regenerated. If a dependency version changes, its exact policy key changes and the review also fails until the new version is assessed. If installed license/source evidence changes without a version change, the package evidence digest changes and the review also fails stale. If project dependency metadata changes the direct dependency surface represented by the lock, qualification fails until the lock and inventory are reconciled.

This package evidence digest is not claimed to be the immutable identity of the downloaded wheel or sdist. The current generator can reliably bind installed distribution metadata and installed legal-file contents, but does not fabricate a selected artifact hash when `importlib.metadata` cannot prove it. Exact candidate artifact identity belongs to the later release-artifact qualification path, including #95.

## Current validation mode

Automated tests and GitHub Actions are currently disabled by maintainer policy. The generator, validator, and adversarial unit tests are implemented in the repository, but this slice does not claim that an inventory was generated from an executed locked environment, that license decisions were completed, or that CI passed. #58 remains open until those evidence and review criteria are genuinely satisfied, including reconciliation of build-tool and security-audit surfaces with the resolved dependency evidence.
