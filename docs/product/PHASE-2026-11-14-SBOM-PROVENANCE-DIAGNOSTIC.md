# SBOM and provenance — current candidate

Date: 2026-11-14  
Candidate: `33c01c45012ae03fac3702ccba4d4a5132b811d8`  
Policy: local/manual qualification only; GitHub Actions is intentionally absent.

## Gate executed

Using the exact wheel and sdist from the installed-artifact qualification:

- Candidate artifact identity: generated and validated for the two exact bytes.
- CycloneDX application SBOM: generated and verified against the lock and
  expected commit.
- Local in-toto/SLSA-format provenance: generated with explicit toolchain and
  timestamps; it remains self-reported and unsigned.
- Combined supply-chain evidence: accepted as
  `ronin.supply-chain-evidence/v1`.
- Wheel SHA-256: `d8a311996d834142a884886503e9c22a09ecd9db552ea35a476e325854097172`.
- sdist SHA-256: `1fe94c7bb9df035a4ba9315440de6eb9681eddfd16df356f76c23811a47405a2`.
- Combined evidence: `C:\Users\angel.alvarez\Downloads\ronin-supply-chain-33c01c45\combined-evidence.json`.

## Qualification boundary

This is a **diagnostic PASS for SDK/application artifacts only**. The identity
was built through the pure manifest function because the checkout contains
pre-existing untracked user artifacts; the CLI's clean-worktree release guard
was not bypassed for a release claim. No container image inventory was supplied
to this run, and license/legal review remains open. The official Public v1
ledger remains **0/13 (0%), NO-GO**.
