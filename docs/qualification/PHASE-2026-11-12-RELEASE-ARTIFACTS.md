# Phase receipt — release artifacts — 2026-11-12

## Candidate

- Source: `6bfcf33546d8d6708c324209a38df9684e0ddc00`
- Repository: `https://github.com/SauronShepherd/ronin.git`
- Build performed from a clean tracked-files worktree outside the development checkout.

## Evidence

- Wheel: `ronin_studio-0.0.0-py3-none-any.whl`, SHA-256 `b31d7f580b6662c0a6b4c1aca6bcf6ea57421d684035e66e711fe92dcedfa1d7`.
- sdist: `ronin_studio-0.0.0.tar.gz`, SHA-256 `c53fa0361b60280b37b0d7c7f8eca479488ed042bd081befc57f7b6588730069`.
- Artifact identity: generated and bound to the exact candidate SHA.
- Release SBOM: generated from `requirements-test.lock` and verified against the artifact identity; file SHA-256 `C4388CDEA0DCAD5126AB8E1393C9256328EB91E0CBB1BABE073B2452CA937718`.
- Artifact SBOM: generated and verified with the exact candidate SHA; file SHA-256 `F669F642279155B2334FD215EDCA4F820CFD803905475AAEA9DE3F4A9EB38972`.
- Local in-toto/SLSA-shaped provenance: generated for the exact artifacts and candidate; file SHA-256 `36CB40FB60579BAA3A8C3E0AAB4FBD16887C792AAE2A2AFA885B001FE1954259`.
- `tools.artifact_qualification` passed its isolated `pyronin` contract qualification: `90 passed`, imported from isolated site-packages. Its output was `pyronin-0.0.1a0`, as expected for that package-specific gate.

## Result

PASS for artifact identity, SBOM generation/verification, provenance generation, and the package-specific isolated `pyronin` contract gate.

This does not make the Public V1 release-qualified family count advance: the release runbook still requires the complete candidate-bound gate set, and the qualification utility covers the `pyronin` package rather than the `ronin_studio` distribution. The release artifacts remain un-published.

## Reproduction commands

```text
py -3 -m build --wheel --sdist --outdir <artifact-dir>
py -3 -m tools.artifact_identity --commit 6bfcf33546d8d6708c324209a38df9684e0ddc00 <wheel> <sdist> --output <identity.json>
py -3 -m tools.generate_release_sbom --artifact-identity <identity.json> --requirements-lock requirements-test.lock --project-file pyproject.toml --output <release-sbom.json>
py -3 -m tools.generate_release_sbom --artifact-identity <identity.json> --requirements-lock requirements-test.lock --project-file pyproject.toml --output <release-sbom.json> --verify --expected-commit 6bfcf33546d8d6708c324209a38df9684e0ddc00
py -3 -m tools.generate_sbom <wheel> <sdist> --root <clean-worktree> --output <artifact-sbom.json> --verify --expected-commit 6bfcf33546d8d6708c324209a38df9684e0ddc00
py -3 -m tools.artifact_qualification --checkout <clean-worktree> --work-root <qualification-work-root> --output <qualification.json>
```
