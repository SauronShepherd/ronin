# Ronin v0.1 third-party license qualification

Ronin v0.1 release qualification must tie third-party license evidence to the exact resolved dependency graph rather than to floating requirement ranges or a manually maintained package list.

## Source of dependency identity

`requirements-dev.lock` is the committed exact, hash-locked root development graph. Root and `pyronin` build backends are exact-pinned in their `pyproject.toml` files. `tools/license_qualification.py` treats the lock as authoritative and records both its exact package/version graph and SHA-256 of the complete lock-file bytes.

The inventory generator must run in an environment installed from that exact lock. It refuses missing distributions and version drift. The generated inventory records, for each locked distribution:

- normalized package name and exact version;
- whether the package is directly declared by the root/SDK project metadata;
- the installed distribution's declared license metadata;
- installed license/copying/notice/authors/copyright file paths exposed by package metadata;
- the complete `requirements-dev.lock` SHA-256 binding the evidence to one exact lock revision.

Generation command after installing the exact lock:

```bash
python tools/license_qualification.py --write-inventory third_party/licenses-v1.json
```

The generated file is evidence, not an approval decision.

## Fail-closed review policy

A release review must separately commit `third_party/license-policy-v1.json`. The policy is keyed by exact normalized `package==version`. Every locked distribution must record:

- an explicit `allow` or `deny` decision;
- `notice_required: true|false`;
- `attribution_required: true|false`;
- a non-empty review rationale grounded in the inspected upstream evidence.

Unknown, missing, duplicate, unreviewed, denied, or graph-drifted dependencies fail qualification. Missing source or declared-license metadata also fails qualification instead of being guessed from package name or ecosystem reputation.

The policy must additionally contain an explicit project-level `project_notice` decision (`required` or `not_required`) and a non-empty `project_notice_rationale`. This is the repository-backed conclusion about whether Ronin itself must ship a project `NOTICE` file for the reviewed resolved graph. Do not add Apache Software Foundation-style NOTICE boilerplate merely because Ronin uses Apache-2.0; the conclusion must come from obligations actually present in the reviewed graph and distributed artifacts.

Qualification command:

```bash
python tools/license_qualification.py
```

The command succeeds only when the committed inventory has the exact current lock SHA-256, exactly matches the parsed locked graph, and every exact dependency has complete reviewed license/notice/attribution decisions plus the project-level NOTICE rationale.

## Review requirements

A maintainer reviewing a generated inventory must inspect the referenced installed license/notice material and upstream distribution metadata before marking a package allowed. If metadata is ambiguous, contradictory, custom, missing, or potentially incompatible with Ronin's Apache-2.0 distribution, leave the package unapproved or deny it until resolved. Do not convert classifier text to an SPDX identifier unless upstream evidence supports that conclusion.

`notice_required` and `attribution_required` are separate review decisions. When either is true, the release process must preserve the required upstream text in the distributed artifact or companion material before #58 can be considered complete. The validator deliberately does not invent or auto-copy legal text from ambiguous metadata.

If the lock file changes for any reason, even without changing its parsed package/version set, the recorded lock SHA-256 changes and qualification fails until inventory evidence is regenerated. If a dependency version changes, its exact policy key changes and the review also fails until the new version is assessed.

## Current validation mode

Automated tests and GitHub Actions are currently disabled by maintainer policy. The generator, validator, and adversarial unit tests are implemented in the repository, but this slice does not claim that an inventory was generated from an executed locked environment, that license decisions were completed, or that CI passed. #58 remains open until those evidence and review criteria are genuinely satisfied.
