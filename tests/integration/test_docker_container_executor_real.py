from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import cast

import pytest
from studio_kernel import (
    CancellationToken,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionAttemptId,
    KernelDirective,
)
from studio_notebook import CellId
from studio_runners.container import (
    AsyncioCommandRunner,
    ContainerExecutionLimits,
    ContainerExecutorConfig,
    DockerContainerKernelExecutor,
    LocalExecutionEvidenceStore,
)

if os.environ.get("RONIN_REAL_DOCKER_QUALIFICATION") != "1":
    pytest.skip(
        "real Docker qualification runs only in the dedicated CI job",
        allow_module_level=True,
    )

_IMAGE = os.environ["RONIN_DOCKER_QUALIFICATION_IMAGE"]
_REPO_DIGEST = os.environ.get("RONIN_DOCKER_QUALIFICATION_REPO_DIGEST", "unknown")
_EVIDENCE_ROOT = Path(os.environ["RONIN_DOCKER_QUALIFICATION_EVIDENCE"])
_DOCKER = shutil.which("docker")
if _DOCKER is None:
    raise RuntimeError("dedicated Docker qualification requires the docker client")

_PROBE_SOURCE = r"""
import json
import os
import resource
from pathlib import Path


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def status_value(name):
    prefix = name + ":"
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def root_mount_options():
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        before, _separator, _after = line.partition(" - ")
        fields = before.split()
        if len(fields) >= 6 and fields[4] == "/":
            return fields[5].split(",")
    return []


def cpu_usage_usec():
    cpu_stat = read_text("/sys/fs/cgroup/cpu.stat")
    if cpu_stat is not None:
        values = {}
        for line in cpu_stat.splitlines():
            key, value = line.split(None, 1)
            values[key] = value
        return values.get("usage_usec")
    usage_ns = read_text("/sys/fs/cgroup/cpuacct/cpuacct.usage")
    if usage_ns is None:
        return None
    return str(int(usage_ns) // 1000)


def memory_current_bytes():
    value = read_text("/sys/fs/cgroup/memory.current")
    if value is not None:
        return value
    return read_text("/sys/fs/cgroup/memory/memory.usage_in_bytes")


tmp_probe = Path("/tmp/ronin-qualification-write")
tmp_probe.write_text("ok", encoding="utf-8")
nofile_soft, nofile_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
payload = {
    "uid": os.getuid(),
    "gid": os.getgid(),
    "interfaces": sorted(os.listdir("/sys/class/net")),
    "root_mount_options": root_mount_options(),
    "tmp_write": tmp_probe.read_text(encoding="utf-8"),
    "cap_eff": status_value("CapEff"),
    "no_new_privs": status_value("NoNewPrivs"),
    "memory_max": read_text("/sys/fs/cgroup/memory.max"),
    "memory_swap_max": read_text("/sys/fs/cgroup/memory.swap.max"),
    "pids_max": read_text("/sys/fs/cgroup/pids.max"),
    "cpu_max": read_text("/sys/fs/cgroup/cpu.max"),
    "memory_limit_v1": read_text("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    "memory_memsw_limit_v1": read_text("/sys/fs/cgroup/memory/memory.memsw.limit_in_bytes"),
    "pids_limit_v1": read_text("/sys/fs/cgroup/pids/pids.max"),
    "cpu_quota_v1": read_text("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"),
    "cpu_period_v1": read_text("/sys/fs/cgroup/cpu/cpu.cfs_period_us"),
    "memory_current_bytes": memory_current_bytes(),
    "cpu_usage_usec": cpu_usage_usec(),
    "nofile_soft": nofile_soft,
    "nofile_hard": nofile_hard,
}
print(json.dumps(payload, sort_keys=True))
"""

_RESOURCE_WORKLOAD_SOURCE = r"""
payload = bytearray(16 * 1024 * 1024)
checksum = 0
for value in range(250_000):
    checksum = (checksum + value * value) % 1_000_000_007
print(checksum + payload[0])
"""


def _cell(cell_id: str, source: str) -> CellExecutionRequest:
    return CellExecutionRequest(
        CellId(cell_id), source, source, "python", (), KernelDirective("docker-qualification", "source.execute")
    )


def _executor(
    attempt_id: str,
    limits: ContainerExecutionLimits,
) -> DockerContainerKernelExecutor:
    return DockerContainerKernelExecutor(
        ContainerExecutorConfig(_IMAGE, limits=limits),
        ExecutionAttemptId(attempt_id),
        LocalExecutionEvidenceStore(_EVIDENCE_ROOT),
        engine_path=_DOCKER,
    )


def _read_evidence(reference: str) -> dict[str, object]:
    prefix = "local-evidence://"
    assert reference.startswith(prefix)
    path = _EVIDENCE_ROOT / reference.removeprefix(prefix)
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _resource_observation(result: CellExecutionResult) -> dict[str, object]:
    resource_reference = next(
        reference for reference in result.evidence if reference.kind == "resource"
    )
    payload = _read_evidence(resource_reference.ref)
    return cast(dict[str, object], payload["observed"])


def _assert_effective_limits(probe: dict[str, object]) -> str:
    memory_max = probe["memory_max"]
    pids_max = probe["pids_max"]
    cpu_max = probe["cpu_max"]
    if isinstance(memory_max, str) and isinstance(pids_max, str) and isinstance(cpu_max, str):
        assert int(memory_max) == 128 * 1024 * 1024
        assert int(pids_max) == 32
        quota_text, period_text = cpu_max.split()
        assert int(quota_text) / int(period_text) == pytest.approx(0.5)
        return "cgroup-v2"

    memory_v1 = probe["memory_limit_v1"]
    pids_v1 = probe["pids_limit_v1"]
    quota_v1 = probe["cpu_quota_v1"]
    period_v1 = probe["cpu_period_v1"]
    assert isinstance(memory_v1, str)
    assert isinstance(pids_v1, str)
    assert isinstance(quota_v1, str)
    assert isinstance(period_v1, str)
    assert int(memory_v1) == 128 * 1024 * 1024
    assert int(pids_v1) == 32
    assert int(quota_v1) / int(period_v1) == pytest.approx(0.5)
    return "cgroup-v1"


async def _docker_ps_names(container_name: str) -> tuple[str, ...]:
    outcome = await AsyncioCommandRunner(max_output_bytes=64 * 1024).run(
        (_DOCKER, "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Names}}"),
        input_text="",
        cancellation=CancellationToken(),
        timeout_seconds=10.0,
        cancellation_args=(_DOCKER, "ps"),
    )
    assert outcome.returncode == 0
    assert outcome.cancelled is False
    assert outcome.timed_out is False
    return tuple(line for line in outcome.output.splitlines() if line)


async def _exercise_cancellation_cleanup() -> tuple[str, tuple[str, ...], dict[str, object]]:
    attempt = ExecutionAttemptId("docker-real-cancel")
    cell = _cell("cancel-cell", "import time; time.sleep(30)")
    executor = _executor(
        str(attempt),
        ContainerExecutionLimits(cpus="0.5", memory="128m", pids=32, timeout_seconds=10.0),
    )
    token = CancellationToken()
    task = asyncio.create_task(executor.execute(cell, token))
    await asyncio.sleep(0.5)
    token.cancel()
    result = await task
    container_name = executor._container_name(cell)  # noqa: SLF001
    return result.state, await _docker_ps_names(container_name), _resource_observation(result)


async def _exercise_timeout_cleanup() -> tuple[str, str | None, tuple[str, ...], dict[str, object]]:
    attempt = ExecutionAttemptId("docker-real-timeout")
    cell = _cell("timeout-cell", "import time; time.sleep(30)")
    executor = _executor(
        str(attempt),
        ContainerExecutionLimits(cpus="0.5", memory="128m", pids=32, timeout_seconds=0.25),
    )
    result = await executor.execute(cell, CancellationToken())
    container_name = executor._container_name(cell)  # noqa: SLF001
    return (
        result.state,
        result.failure_code,
        await _docker_ps_names(container_name),
        _resource_observation(result),
    )


def test_real_docker_memory_swap_capped() -> None:
    limits = ContainerExecutionLimits(
        cpus="0.5", memory="128m", pids=32, nofile=1024, timeout_seconds=10.0
    )
    executor = _executor("docker-real-resource-limits", limits)
    result = asyncio.run(
        executor.execute(_cell("resource-limit-probe", _PROBE_SOURCE), CancellationToken())
    )
    assert result.state == "succeeded"
    log_reference = next(reference for reference in result.evidence if reference.kind == "log")
    probe = cast(
        dict[str, object], json.loads(cast(str, _read_evidence(log_reference.ref)["output"]))
    )
    memory_swap_max = probe["memory_swap_max"]
    if isinstance(memory_swap_max, str):
        assert int(memory_swap_max) == 0
    else:
        memory_limit_v1 = probe["memory_limit_v1"]
        memory_memsw_limit_v1 = probe["memory_memsw_limit_v1"]
        assert isinstance(memory_limit_v1, str)
        assert isinstance(memory_memsw_limit_v1, str)
        assert int(memory_memsw_limit_v1) == int(memory_limit_v1)
    assert probe["nofile_soft"] == 1024
    assert probe["nofile_hard"] == 1024


def test_real_docker_records_observed_cpu_and_memory() -> None:
    limits = ContainerExecutionLimits(cpus="0.5", memory="128m", pids=32, timeout_seconds=10.0)
    executor = _executor("docker-real-observed-resource", limits)
    result = asyncio.run(
        executor.execute(
            _cell("observed-resource-cell", _RESOURCE_WORKLOAD_SOURCE), CancellationToken()
        )
    )
    assert result.state == "succeeded"
    observed = _resource_observation(result)
    assert observed["availability"] == "available"
    assert observed["measurement_source"] in {"cgroup_v1", "cgroup_v2"}
    assert isinstance(observed["cpu_seconds"], float) and observed["cpu_seconds"] > 0
    assert isinstance(observed["memory_peak_bytes"], int)
    assert observed["memory_peak_bytes"] >= 16 * 1024 * 1024
    assert observed["unavailable_reason"] is None


def test_real_docker_isolation_limits_usage_and_cleanup() -> None:
    _EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    limits = ContainerExecutionLimits(cpus="0.5", memory="128m", pids=32, timeout_seconds=10.0)
    executor = _executor("docker-real-probe", limits)
    result = asyncio.run(executor.execute(_cell("probe-cell", _PROBE_SOURCE), CancellationToken()))
    assert result.state == "succeeded"
    log_reference = next(reference for reference in result.evidence if reference.kind == "log")
    resource_reference = next(reference for reference in result.evidence if reference.kind == "resource")
    probe = cast(dict[str, object], json.loads(cast(str, _read_evidence(log_reference.ref)["output"])))
    resource_payload = _read_evidence(resource_reference.ref)
    assert probe["uid"] == 65532
    assert probe["gid"] == 65532
    assert probe["interfaces"] == ["lo"]
    assert probe["cap_eff"] == "0000000000000000"
    assert probe["no_new_privs"] == "1"
    cgroup_version = _assert_effective_limits(probe)
    observed = cast(dict[str, object], resource_payload["observed"])
    assert resource_payload["measurement_scope"] == "observed_cgroup_usage_and_enforced_limits"
    assert resource_payload["limits"] == {
        "cpus": "0.5", "memory": "128m", "memory_swap": "128m", "nofile": 1024, "pids": 32
    }
    assert resource_payload["instrumentation"] == {
        "measurement_supervisor_pids": 1, "effective_container_pids_limit": 32
    }
    assert resource_payload["execution_identity"] == {
        "attempt_id": "docker-real-probe", "cell_id": "probe-cell", "runtime_image": _IMAGE
    }
    assert observed["availability"] == "available"
    assert observed["measurement_source"] == cgroup_version.replace("-", "_")

    cancelled_state, cancellation_names, cancelled_observed = asyncio.run(
        _exercise_cancellation_cleanup()
    )
    timeout_state, timeout_failure, timeout_names, timeout_observed = asyncio.run(
        _exercise_timeout_cleanup()
    )
    assert cancelled_state == "cancelled"
    assert cancellation_names == ()
    assert cancelled_observed["unavailable_reason"] == "execution_cancelled_before_final_measurement"
    assert timeout_state == "failed"
    assert timeout_failure == "kernel.container.timeout"
    assert timeout_names == ()
    assert timeout_observed["unavailable_reason"] == "execution_timed_out_before_final_measurement"

    summary = {
        "schema": "ronin.docker-qualification/v1",
        "executed_image_id": _IMAGE,
        "bootstrap_repository_digest": _REPO_DIGEST,
        "observed_usage": observed,
        "cleanup": {
            "cancellation_state": cancelled_state,
            "cancellation_containers_remaining": list(cancellation_names),
            "cancellation_observation": cancelled_observed,
            "timeout_state": timeout_state,
            "timeout_failure": timeout_failure,
            "timeout_containers_remaining": list(timeout_names),
            "timeout_observation": timeout_observed,
        },
        "cost_evidence": "not_emitted; physical quantities only",
    }
    (_EVIDENCE_ROOT / "qualification-summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
