# Ronin v0.1 Python artifact qualification

`tools/artifact_qualification.py` defines the code-level qualification boundary for the `pyronin` release candidate.

## Candidate identity

The tool builds `packages/pyronin` once into an output directory outside the repository checkout. It requires exactly one wheel and one sdist, computes SHA-256 over the exact bytes of both files, and records SHA-256 over the exact wheel `.dist-info/RECORD` bytes. The resulting deterministic JSON record uses schema `ronin.python-artifact-candidate/v1`.

The wheel is installed from that exact path with `pip --no-index --no-deps --target` into an isolated `site-packages` directory outside the checkout. No rebuild occurs between candidate identity calculation and installation.

## Source-leakage guard

After installation, the tool starts a fresh Python process from the external qualification work directory with `PYTHONPATH` set only to the isolated target and imports `pyronin`. Qualification fails unless `pyronin.__file__` resolves under that isolated target and outside the repository checkout.

The SDK contract tests are copied to the external work directory and executed there with an isolated `pytest.ini` and `--import-mode=importlib`. This avoids inheriting the root `pyproject.toml` pytest `pythonpath` entries that include checkout source. Existing `pyronin` transport tests therefore continue to exercise HTTPS requirements, redirect rejection, bounded response bodies, and server-error suppression against the installed candidate rather than `packages/pyronin/src`.

## License evidence binding

`bind_license_evidence()` deliberately keeps two identities distinct and links them explicitly:

- `artifact_sha256`: SHA-256 of the exact selected wheel or sdist bytes;
- `license_evidence_sha256`: the evidence digest already stored for the exact `package==version` entry in `third_party/licenses-v1.json`.

The function fails closed on missing, duplicate, version-mismatched, or malformed inventory evidence. It never fabricates an artifact digest from installed metadata. This closes the code-level data path identified by the license qualification contract while preserving the distinction between selected artifact identity and installed license metadata.

## Current execution status

This document describes implementation mechanics, not release evidence. A real `pyronin` candidate must still be built with the exact pinned build backend, qualified outside the checkout, retained without rebuilding, and subsequently published as that exact candidate. GitHub Actions remain disabled, so no current exact-head workflow evidence is implied by this implementation.
