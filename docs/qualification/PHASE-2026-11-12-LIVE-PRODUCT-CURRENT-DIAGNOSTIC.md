# Live Studio product qualification — current candidate diagnostic

**Date:** 2026-11-12  
**Candidate SHA:** `777bc08aef6b0984ea1fc95a97a7d02019c1077a`  
**Worker image:** `ronin:qualification-777bc08`  
**Worker image ID:** `sha256:401c63e81ca6c26a121fd6ac765c4e79df18c78dcfb18f4fa1b2d27c9950199c`

## Full run

Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-live-qualification-777bc08`

The full live runner executed 33 Playwright cases against isolated PostgreSQL,
Kafka-compatible streaming and real Ronin APIs. **32 passed, 1 failed**, with
277 correlated API events, 0 server/network errors and cleanup completed.

The only failure was `live Runs saves server settings and retains the project
filter`; it observed the expected server-settings prompt instead of the runs
result within the test timeout.

## Isolated rerun

Evidence: `C:\Users\angel.alvarez\AppData\Local\Temp\ronin-live-qualification-777bc08-rerun`

The exact failing case was rerun with the same candidate and worker image:

```text
TestGrep = live Runs saves server settings
```

Result: **1/1 passed**, 2 correlated API events, 0 server/network errors and
cleanup completed in 44.96s.

## Verdict and boundary

This is a transient/flaky-suite diagnostic: the isolated reproduction is green,
but the complete 33-case gate is not claimed as passed because its full run was
32/33. The full installed Studio/Public v1 family gate remains open and the
official progress remains **0/13 (0%)**.

