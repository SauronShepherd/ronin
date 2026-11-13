# PyRonin wheel/sdist artifact qualification — current candidate

**Date:** 2026-11-13  
**Candidate SHA:** `f8e0260a1e3d42fe34e56e96a7c362eb08aa8b5e`

## Gate

The artifact runner used a detached clean worktree, built wheel and sdist,
installed the wheel into isolated site-packages outside the checkout and ran
the package contract suite.

Result: **90 passed, 0 failed, 0 skipped** in 11.99 seconds.

- Package: `pyronin`
- Version: `0.0.1a0`
- Wheel SHA-256: `898715702113483af2ba1ca66470e9a3a792969a7bded84a7ea5c78689dbcd86`
- sdist SHA-256: `1284b732d17ca51d892e5257682eed218c6e23a87f16b221d2d741718f9c87bf`
- Import origin: isolated site-packages
- Qualification JSON: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-artifact-qualification-current-20261113054800.json`

## Boundary

This closes the SDK artifact-installation lane. Application SBOM/provenance,
license/legal approval, complete Public v1 families and release aggregation
remain separate gates. Public v1 remains **0/13 (0%) — NO-GO**.
