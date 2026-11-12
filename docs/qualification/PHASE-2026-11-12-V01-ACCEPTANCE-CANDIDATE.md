# Phase 2026-11-12 — v0.1 acceptance candidate journey

## Scope

Run the frozen v0.1 acceptance journey with the real Docker worker path, using an image built from the exact tracked candidate.

## Candidate binding

- Source commit under test: `7258c95121a780dc5a0810cd34202ddfcd64e34b`
- Image tag used only for local naming: `ronin:qualification-7258c951`
- Immutable image ID passed to the test: `sha256:2b9533641513c04e2dc12a9e5dc277575777edaf5af51b305794099e31647db9`
- Image built with: `docker build --pull=false -f docker/Dockerfile -t ronin:qualification-7258c951 .`

## Execution

```text
$env:PYTHONPATH='python'
$env:RONIN_DOCKER_QUALIFICATION_IMAGE='sha256:2b9533641513c04e2dc12a9e5dc277575777edaf5af51b305794099e31647db9'
$env:RONIN_REAL_DOCKER_QUALIFICATION='1'
python -m pytest -q tests/e2e/test_v01_journey.py
```

Result: **PASS — 16 passed, 0 failed, 0 skipped, 75.14 s**.

The journey covers the frozen v0.1 steps, including real Compose health, worker execution, crash/reclaim/restart persistence, SDK/CLI parity, and cancellation cleanup.

## Iteration and correction

An initial run with the mutable value `ronin:qualification` failed closed at container configuration because the runtime requires an immutable digest or image ID. The image was then rebuilt from the candidate source and the journey was rerun with the immutable image ID above; the complete run passed.

## Qualification boundary

This closes the v0.1 acceptance journey phase. It is evidence for the shared execution/release surface, not by itself closure of any complete Public v1 capability family. The global release remains **NO-GO** and Public v1 remains **0/13 (0%)** pending the broader family journeys and independent human/legal/provider/recovery gates.

