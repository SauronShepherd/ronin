# Phase receipt — Helm/kind qualification refresh — 2026-11-12

## Candidate and image

- Source candidate: `8511344f04ac6d25900f7e8ccd5001afcfcbd15e`.
- Worktree mode: `DIRTY-WORKTREE DIAGNOSTIC` due to pre-existing untracked user artifacts.
- Image reference used by Helm: `ronin:qualification`.
- Image digest validated by the runner and loaded into kind: `sha256:9b50b39d9aa8616dbaf1e748b4a4f4b14a8376b8e5f14cc9ada9b416d62fb7e4`.
- Docker evidence was exact-source matched to the same candidate and reported strict acceptance `15/15`.

## Evidence

The real Helm/kind runner exited `0` and reported:

- Helm lint: passed.
- Secret-render boundary: passed; token confined to Secret.
- kind cluster creation and image load: passed.
- Helm install and deployment readiness: passed.
- Helm upgrade to revision 2: passed.
- Helm rollback to revision 1: passed.
- Health endpoint: HTTP 200.
- Studio and authorized jobs API: HTTP 200.
- Persistent queued job creation: HTTP 201.
- Pod restart and rollout: passed.
- Same queued job ID survived restart: passed.
- Cleanup: passed; isolated kind cluster removed.

## Corrective finding

An initial attempt supplied a bare digest as the Helm image name. Kubernetes correctly attempted a registry pull and entered `ImagePullBackOff`. The run was stopped and its cluster removed. The rerun used the local tag `ronin:qualification`; the runner verified the expected digest before loading it, and the full gate passed.

## Result

PASS for the complete Helm/kind qualification gate, with clean cleanup. This remains diagnostic rather than a clean release-candidate claim because the worktree contains unrelated pre-existing untracked artifacts. Public V1 remains `0/13 (0%)`.
