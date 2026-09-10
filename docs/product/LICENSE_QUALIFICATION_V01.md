# Ronin v0.1 third-party license qualification

Ronin v0.1 release qualification must tie third-party license evidence to the exact resolved dependency graph rather than to floating requirement ranges or a manually maintained package list.

## Source of dependency identity

`requirements-dev.lock` is the committed exact, hash-locked root development graph. Root and `pyronin` build backends are exact-pinned in their `pyproject.toml` files. `tools/license_qualification.py` treats the locked package name/version set as the authoritative graph for this qualification slice.

The inventory generator must run in an environment installed from that exact lock. It refuses missing distributions and version drift. The generated inventory records, for each locked distribution:

- normalized package name and exact version;
- whether the package is directly declared by the root/SDK project metadata;
- the installed distribution's declared license metadata;
- installed license/copying/notice/author file paths exposed by package metadata.

Generation command after installing the exact lock:

```bash
python tools/license_qualification.py --write-inventory third_party/licenses-v1.json
```

The generated file is evidence, not an approval decision.

## Fail-closed review policy

A release review must separately commit `third_party/license-policy-v1.json`. The policy is keyed by exact normalized `package==version` and must record an explicit `allow` or `deny` decision plus `notice_required: true|false` for every locked distribution. Unknown, missing, duplicate, unreviewed, or denied dependencies fail qualification. Missing declared license metadata also fails qualification instead of being guessed from package name or ecosystem reputation.

The policy must also contain one explicit project-level `project_notice` decision: `required` or `not_required`. This is the repository-backed conclusion about whether Ronin itself must ship a project `NOTICE` file for the reviewed resolved graph. Do not add Apache Software Foundation-style NOTICE boilerplate merely because Ronin uses Apache-2.0; the conclusion must come from the obligations actually present in the reviewed graph and distributed artifacts.

Qualification command:

```bash
python tools/license_qualification.py
```

The command succeeds only when the committed inventory exactly matches `requirements-dev.lock` and every exact dependency has a reviewed allow/notice decision.

## Review requirements

A maintainer reviewing a generated inventory must inspect the referenced installed license/notice material and upstream distribution metadata before marking a package allowed. If metadata is ambiguous, contradictory, custom, missing, or potentially incompatible with Ronin's Apache-2.0 distribution, leave the package unapproved or deny it until resolved. Do not convert classifier text to an SPDX identifier unless the upstream package actually provides enough evidence for that conclusion.

If a dependency version changes, the exact policy key changes and qualification fails until the new version is reviewed. This deliberately prevents an earlier approval from silently applying to different upstream license terms.

## Current validation mode

Automated tests and GitHub Actions are currently disabled by maintainer policy. The generator, validator, and adversarial unit tests are implemented in the repository, but this slice does not claim that an inventory was generated from an executed locked environment, that license decisions were completed, or that CI passed. #58 remains open until those evidence and review criteria are genuinely satisfied.
