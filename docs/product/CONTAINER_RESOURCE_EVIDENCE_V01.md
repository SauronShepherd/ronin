# Container resource evidence v0.1

Status: **implementation contract for the supported local-Docker runner**.

Ronin records configured resource ceilings and observed resource use as different facts. A configured limit is never presented as observed consumption, and an unavailable observation is never represented as zero.

## Evidence shape

Every persisted `resource` evidence document keeps the existing `duration_ms` and `limits` fields. When the supported runner can supervise the container command, it additionally emits:

```json
{
  "measurement_scope": "observed_cgroup_usage_and_enforced_limits",
  "observed": {
    "schema": "ronin.container-resource-observation/v1",
    "availability": "available",
    "cpu_seconds": 0.123456,
    "memory_peak_bytes": 33554432,
    "measurement_source": "cgroup_v2",
    "measurement_window": {
      "started_unix_ns": 0,
      "finished_unix_ns": 0
    },
    "units": {
      "cpu_seconds": "seconds",
      "memory_peak_bytes": "bytes"
    },
    "unavailable_reason": null
  }
}
```

The resource document also records the available execution correlation (`attempt_id`, `cell_id`, immutable runtime image identity) and instrumentation facts. It does not invent project/job/run dimensions that are not owned by this runner boundary.

## Measurement semantics

The default `AsyncioCommandRunner` starts the configured cell command under a minimal `/bin/sh` supervisor inside the same container and cgroup. The supervisor keeps a private bounded stderr control channel that is not exposed to the cell process. Cell stdout and stderr retain their normal merged/redacted log behavior.

On cgroup v2, CPU is the delta of `cpu.stat` `usage_usec` immediately before and after the cell command, converted to seconds. Peak memory is `memory.peak`, which is the peak for the cell container cgroup lifetime and therefore includes the small measurement supervisor as well as the cell process.

On cgroup v1, CPU is the delta of `cpuacct.usage`, converted from nanoseconds to seconds, and peak memory is `memory.max_usage_in_bytes`.

`measurement_window.started_unix_ns` and `finished_unix_ns` are host wall-clock timestamps bracketing the Docker run process. The cgroup CPU counter delta is taken inside that envelope, immediately around the cell command. The persisted duration remains the existing monotonic host duration.

The measurement supervisor consumes one process slot inside the existing `--pids-limit`; Ronin does not silently raise the configured container ceiling. If `pids=1`, the cell runs through the legacy direct path and observed resource measurement is explicitly unavailable.

## Fail-closed availability

`observed.availability` is either `available` or `unavailable`. When unavailable, `cpu_seconds` and `memory_peak_bytes` are `null`, `measurement_source` is `unavailable`, and `unavailable_reason` is mandatory. Expected reasons include:

- `pids_limit_prevents_measurement_supervisor`;
- `runner_control_channel_unavailable` for a replaceable command runner that cannot provide the trusted control channel;
- `cgroup_metrics_unavailable` or `final_cgroup_metrics_unavailable` when the supported cgroup files cannot be read;
- `execution_cancelled_before_final_measurement` or `execution_timed_out_before_final_measurement` when hard cleanup removes the container before the final cgroup read;
- `resource_measurement_frame_missing` or `resource_measurement_frame_invalid` when the control record cannot be trusted.

Hard cancellation and timeout cleanup remain authoritative over resource collection. Ronin does not delay cleanup to manufacture a final measurement.

## Collection overhead

A local host-only micro-check on 2026-09-11 used Python 3.13.5 and `/bin/sh`, one warm-up per path, then seven alternating short-command samples. The direct-command median was 637.405 ms; the shell-supervised median was 642.163 ms; the median delta was **4.758 ms**. These numbers characterize only the current execution environment and the supervisor mechanism. They are not Docker qualification evidence and do not establish production p50/p95 overhead.

Real-Docker qualification must measure the supported image on an exact Ronin SHA, include CPU-active and memory-active cells, retain succeeded/failed/cancelled/timed-out behavior, and record collection overhead before #115 can be closed.

## Cost boundary

v0.1 records physical quantities only. No currency, billing rate, inferred cloud cost, or showback price is emitted because Ronin has no versioned attributable rate basis for this local runner.
