# Exact-head qualification evidence — 2026-09-17

The following GitHub Actions runs qualified the same source commit:

- Source SHA: `54acab60b7b2b9cb8a14e6f1c21272b2c9ebea1b`
- Status consistency: run `35179386638` — success
- Docker and PostgreSQL qualification: run `35179386661` — success
- Security qualification: run `35179386688` — success
- Release qualification: run `35179386691` — success
- General CI: run `35179386734` — success

The Docker qualification run completed the non-Docker suite, built the pinned
probe image, resolved its image digest, executed the real Docker worker tests,
and uploaded qualification evidence. The release run built and smoke-tested
the wheel and source distribution outside the checkout.

These records are evidence for this exact SHA only. A later source change
requires a new qualification cycle; historical green runs must not be reused
as evidence for a different candidate.
