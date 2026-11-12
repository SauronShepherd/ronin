# Phase receipt — clean candidate artifact chain — 2026-11-12

## Candidate

- Exact source SHA: `48086d60f9b99044839fd89a5e9a2cdf6ab7f57c`.
- Clean detached worktree: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-clean-candidate-48086d6`; `git status --porcelain` was empty.

## Artifact identity

- Wheel `ronin_studio-0.0.0-py3-none-any.whl`: SHA-256 `662640365d111debfd3a4d4fd5bc3b573266a5df0de759c033df76dfd1c6a675`, 2,699,392 bytes.
- sdist `ronin_studio-0.0.0.tar.gz`: SHA-256 `b24ec665a06fb075351e44323e992f3f660ecf95e605f66326961c15c75b6f9c`, 2,923,484 bytes.
- Artifact identity JSON is bound to the exact source SHA and both artifact digests.

## Qualification evidence

- Release SBOM generated from `requirements-test.lock` and verified against the identity and expected source SHA.
- Local in-toto/SLSA-shaped release provenance generated for the exact identity.
- `tools.artifact_qualification`: isolated `pyronin` sdist/wheel install and contract suite — **90 passed**; import origin was isolated site-packages.
- `tools.installed_studio_browser_smoke` against the exact release wheel: **25 routes**, **3 skills**, 0 failures, 0 console errors, and 0 failed requests.
- Evidence file hashes:
  - artifact identity: `0EE558B5EC6912E6BCEF34D7597E5851632BB37EB9B9502DBB73F60E460FB2C1`;
  - release SBOM: `9758EB6E340BDDBA3686C26CABC29DE2E8C809630468F54CCD092DBDD31B2AC4`;
  - provenance: `BE1ACB8C54DBF10C23B36CC31AE543E1111A9324453D3B3BC1EFF3FF3F0FE07D`.

## Result

PASS for clean-candidate artifact identity, SBOM/provenance generation and verification, isolated package qualification, and installed Studio smoke. Publication remains blocked by the separate license/human gate and complete candidate gate aggregation. Public V1 remains `0/13 (0%)`.
