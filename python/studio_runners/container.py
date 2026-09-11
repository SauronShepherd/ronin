"""Hardened local OCI/Docker execution behind the kernel executor boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast, runtime_checkable

from studio_kernel import (
    CancellationSignal,
    CellExecutionRequest,
    CellExecutionResult,
    ExecutionAttemptId,
    ExecutionEvidenceReference,
    ExecutorIsolation,
    redact_sensitive_text,
)

_IMMUTABLE_IMAGE = re.compile(r"^(?:[^\s]+@)?sha256:[0-9a-f]{64}$")
_CPU_LIMIT = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
_MEMORY_LIMIT = re.compile(r"^[1-9][0-9]*[kKmMgG]$")
_CONTAINER_USER = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")
_READ_CHUNK_BYTES = 64 * 1024
_TRUNCATED_OUTPUT = "[OUTPUT TRUNCATED]"
_CONTAINER_TMPFS = "/tmp:rw,noexec,nosuid,nodev,size=64m"  # noqa: S108
_CONTAINER_WORKDIR = "/tmp"  # noqa: S108
_RESOURCE_CONTROL_PREFIX = "RONIN_RESOURCE_V1\t"
_RESOURCE_CONTROL_MAX_BYTES = 16 * 1024
_RESOURCE_SCHEMA = "ronin.container-resource-observation/v1"
_MEASUREMENT_SCOPE = "observed_cgroup_usage_and_enforced_limits"
_RESOURCE_WRAPPER = r'''
exec 3>&2
exec 2>&1

read_v2_cpu() {
    usage=
    while IFS=" " read -r key value rest; do
        if [ "$key" = "usage_usec" ]; then
            usage=$value
        fi
    done < /sys/fs/cgroup/cpu.stat || return 1
    [ -n "$usage" ] || return 1
    printf "%s" "$usage"
}

read_value() {
    IFS= read -r value < "$1" || return 1
    [ -n "$value" ] || return 1
    printf "%s" "$value"
}

source_name=
scale=
cpu_start=
if [ -r /sys/fs/cgroup/cpu.stat ] && [ -r /sys/fs/cgroup/memory.peak ]; then
    cpu_start=$(read_v2_cpu) && source_name=cgroup_v2 && scale=1000000
elif [ -r /sys/fs/cgroup/cpuacct/cpuacct.usage ] \
    && [ -r /sys/fs/cgroup/memory/memory.max_usage_in_bytes ]; then
    cpu_start=$(read_value /sys/fs/cgroup/cpuacct/cpuacct.usage) \
        && source_name=cgroup_v1 \
        && scale=1000000000
fi

"$@" 3>&-
returncode=$?

cpu_end=
memory_peak=
if [ "$source_name" = cgroup_v2 ]; then
    cpu_end=$(read_v2_cpu) || cpu_end=
    memory_peak=$(read_value /sys/fs/cgroup/memory.peak) || memory_peak=
elif [ "$source_name" = cgroup_v1 ]; then
    cpu_end=$(read_value /sys/fs/cgroup/cpuacct/cpuacct.usage) || cpu_end=
    memory_peak=$(read_value /sys/fs/cgroup/memory/memory.max_usage_in_bytes) || memory_peak=
fi

if [ -n "$source_name" ] && [ -n "$cpu_start" ] && [ -n "$cpu_end" ] && [ -n "$memory_peak" ]; then
    printf "RONIN_RESOURCE_V1\tavailable\t%s\t%s\t%s\t%s\t%s\n" \
        "$source_name" "$cpu_start" "$cpu_end" "$scale" "$memory_peak" >&3
elif [ -z "$source_name" ]; then
    printf "RONIN_RESOURCE_V1\tunavailable\tcgroup_metrics_unavailable\n" >&3
else
    printf "RONIN_RESOURCE_V1\tunavailable\tfinal_cgroup_metrics_unavailable\n" >&3
fi
exec 3>&-
exit "$returncode"
'''.strip()


def _require_single_line(value: str, name: str) -> None:
    if not value or value.strip() != value or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, NUL-free, and single-line")


@dataclass(frozen=True, slots=True)
class ContainerExecutionLimits:
    """Explicit container ceilings; these are limits, not observed resource usage."""

    cpus: str = "1.0"
    memory: str = "512m"
    pids: int = 128
    nofile: int = 1024
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not _CPU_LIMIT.fullmatch(self.cpus) or float(self.cpus) <= 0:
            raise ValueError("container CPU limit must be a positive decimal")
        if not _MEMORY_LIMIT.fullmatch(self.memory):
            raise ValueError("container memory limit must include an explicit k/m/g Docker unit")
        if self.pids < 1:
            raise ValueError("container PID limit must be positive")
        if self.nofile < 1:
            raise ValueError("container nofile limit must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("container timeout must be positive")


@dataclass(frozen=True, slots=True)
class ContainerExecutorConfig:
    """Immutable local container execution configuration."""

    image: str
    limits: ContainerExecutionLimits = field(default_factory=ContainerExecutionLimits)
    engine: str = "docker"
    user: str = "65532:65532"
    command: tuple[str, ...] = ("python", "-I", "-")

    def __post_init__(self) -> None:
        _require_single_line(self.image, "container image")
        if not _IMMUTABLE_IMAGE.fullmatch(self.image):
            raise ValueError("container image must use an immutable sha256 digest or image id")
        _require_single_line(self.engine, "container engine")
        _require_single_line(self.user, "container user")
        if not _CONTAINER_USER.fullmatch(self.user):
            raise ValueError("container user must be an explicit non-root numeric uid:gid")
        if not self.command:
            raise ValueError("container command must not be empty")
        for argument in self.command:
            _require_single_line(argument, "container command argument")


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    returncode: int
    output: str
    cancelled: bool
    timed_out: bool
    duration_ms: int
    control_output: str = ""
    started_unix_ns: int | None = None
    finished_unix_ns: int | None = None


class CancellableCommandRunner(Protocol):
    async def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome: ...


@runtime_checkable
class ResourceControlCommandRunner(CancellableCommandRunner, Protocol):
    async def run_with_control(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome: ...


@dataclass(frozen=True, slots=True)
class AsyncioCommandRunner:
    """Awaitable subprocess runner with bounded redacted output and hard cancellation."""

    poll_seconds: float = 0.02
    cleanup_timeout_seconds: float = 5.0
    max_output_bytes: int = 8 * 1024 * 1024
    max_control_bytes: int = _RESOURCE_CONTROL_MAX_BYTES

    def __post_init__(self) -> None:
        if self.poll_seconds <= 0 or self.cleanup_timeout_seconds <= 0:
            raise ValueError("command runner timeouts must be positive")
        if self.max_output_bytes < 1 or self.max_control_bytes < 1:
            raise ValueError("command runner output limits must be positive")

    async def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        return await self._run(
            args,
            input_text=input_text,
            cancellation=cancellation,
            timeout_seconds=timeout_seconds,
            cancellation_args=cancellation_args,
            capture_control=False,
        )

    async def run_with_control(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        return await self._run(
            args,
            input_text=input_text,
            cancellation=cancellation,
            timeout_seconds=timeout_seconds,
            cancellation_args=cancellation_args,
            capture_control=True,
        )

    async def _run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
        capture_control: bool,
    ) -> CommandOutcome:
        if not args or not cancellation_args:
            raise ValueError("execution and cancellation commands must be non-empty")
        started = time.monotonic()
        started_unix_ns = time.time_ns()
        stderr_target = asyncio.subprocess.PIPE if capture_control else asyncio.subprocess.STDOUT
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr_target,
        )
        stdin = cast(asyncio.StreamWriter, process.stdin)
        stdout = cast(asyncio.StreamReader, process.stdout)
        output_task = asyncio.create_task(self._collect_stream(stdout, self.max_output_bytes))
        control_task: asyncio.Task[tuple[bytes, bool]] | None = None
        if capture_control:
            stderr = cast(asyncio.StreamReader, process.stderr)
            control_task = asyncio.create_task(
                self._collect_stream(stderr, self.max_control_bytes)
            )
        wait_task = asyncio.create_task(process.wait())
        completed_normally = False
        try:
            stdin.write(input_text.encode())
            await stdin.drain()
            stdin.close()
            cancelled = False
            timed_out = False
            needs_cleanup = False
            while not wait_task.done():
                elapsed = time.monotonic() - started
                cancelled = cancellation.is_cancelled
                timed_out = elapsed >= timeout_seconds
                if cancelled or timed_out:
                    needs_cleanup = True
                    await self._cleanup(cancellation_args)
                    if process.returncode is None:
                        process.kill()
                    break
                await asyncio.sleep(self.poll_seconds)
            returncode = await asyncio.shield(wait_task)
            raw_output, truncated = await asyncio.shield(output_task)
            control_output = ""
            if control_task is not None:
                raw_control, control_truncated = await asyncio.shield(control_task)
                raw_output, control_output, control_loss = self._separate_control(
                    raw_output, raw_control, control_truncated
                )
                truncated = truncated or control_loss
            if needs_cleanup:
                await self._cleanup(cancellation_args)
            duration_ms = max(0, int((time.monotonic() - started) * 1000))
            output = self._format_output(raw_output, truncated)
            finished_unix_ns = time.time_ns()
            completed_normally = True
            return CommandOutcome(
                returncode,
                output,
                cancelled,
                timed_out,
                duration_ms,
                control_output,
                started_unix_ns,
                finished_unix_ns,
            )
        finally:
            if not completed_normally:
                stream_tasks = (
                    (output_task,) if control_task is None else (output_task, control_task)
                )
                await self._reap_process(process, wait_task, stream_tasks, cancellation_args)

    def _separate_control(
        self,
        raw_output: bytes,
        raw_control: bytes,
        control_truncated: bool,
    ) -> tuple[bytes, str, bool]:
        if control_truncated:
            return raw_output + raw_control, "", True
        prefix = _RESOURCE_CONTROL_PREFIX.encode("utf-8")
        control_lines: list[bytes] = []
        diagnostics: list[bytes] = []
        for line in raw_control.splitlines(keepends=True):
            if line.startswith(prefix):
                control_lines.append(line)
            else:
                diagnostics.append(line)
        control_output = b"".join(control_lines).decode("utf-8", errors="replace")
        return raw_output + b"".join(diagnostics), control_output, False

    def _format_output(self, raw_output: bytes, truncated: bool) -> str:
        decoded = raw_output.decode("utf-8", errors="replace")
        output = redact_sensitive_text(decoded)
        if not truncated:
            return output
        if output != decoded:
            return _TRUNCATED_OUTPUT
        marker = f"\n{_TRUNCATED_OUTPUT}"
        if self.max_output_bytes <= len(marker):
            return _TRUNCATED_OUTPUT[: self.max_output_bytes]
        prefix_limit = self.max_output_bytes - len(marker)
        return output[:prefix_limit] + marker

    async def _reap_process(
        self,
        process: asyncio.subprocess.Process,
        wait_task: asyncio.Task[int],
        stream_tasks: tuple[asyncio.Task[tuple[bytes, bool]], ...],
        cancellation_args: tuple[str, ...],
    ) -> None:
        try:
            await self._cleanup(cancellation_args)
        finally:
            if process.returncode is None:
                process.kill()
            await asyncio.gather(wait_task, return_exceptions=True)
            for task in stream_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*stream_tasks, return_exceptions=True)

    async def _reap_after_task_cancellation(
        self,
        process: asyncio.subprocess.Process,
        wait_task: asyncio.Task[int],
        stream_tasks: tuple[asyncio.Task[tuple[bytes, bool]], ...],
        cancellation_args: tuple[str, ...],
    ) -> None:
        await self._reap_process(process, wait_task, stream_tasks, cancellation_args)

    @staticmethod
    async def _collect_stream(stream: asyncio.StreamReader, limit: int) -> tuple[bytes, bool]:
        captured = bytearray()
        truncated = False
        while chunk := await stream.read(_READ_CHUNK_BYTES):
            remaining = max(0, limit - len(captured))
            captured.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        return bytes(captured), truncated

    async def _cleanup(self, args: tuple[str, ...]) -> None:
        cleanup = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(cleanup.wait(), timeout=self.cleanup_timeout_seconds)
        except TimeoutError:
            cleanup.kill()
            await cleanup.wait()


class ExecutionEvidenceStore(Protocol):
    def persist_json(
        self,
        kind: str,
        attempt_id: ExecutionAttemptId,
        cell: CellExecutionRequest,
        payload: dict[str, object],
    ) -> ExecutionEvidenceReference: ...


@dataclass(frozen=True, slots=True)
class LocalExecutionEvidenceStore:
    """File-fsynced local evidence store addressed through opaque local-evidence references."""

    root: Path

    def persist_json(
        self,
        kind: str,
        attempt_id: ExecutionAttemptId,
        cell: CellExecutionRequest,
        payload: dict[str, object],
    ) -> ExecutionEvidenceReference:
        if kind not in {"log", "resource"}:
            raise ValueError("local container evidence store supports log/resource evidence only")
        evidence_kind = cast(Literal["log", "resource"], kind)
        attempt_key = hashlib.sha256(str(attempt_id).encode()).hexdigest()[:24]
        cell_key = hashlib.sha256(str(cell.cell_id).encode()).hexdigest()[:24]
        directory = self.root / attempt_key / cell_key
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{kind}.json"
        temporary = directory / f".{kind}.json.tmp"
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(target)
        return ExecutionEvidenceReference(
            evidence_kind, f"local-evidence://{attempt_key}/{cell_key}/{kind}.json"
        )


def _unavailable_observation(outcome: CommandOutcome, reason: str) -> dict[str, object]:
    return {
        "schema": _RESOURCE_SCHEMA,
        "availability": "unavailable",
        "cpu_seconds": None,
        "memory_peak_bytes": None,
        "measurement_source": "unavailable",
        "measurement_window": {
            "started_unix_ns": outcome.started_unix_ns,
            "finished_unix_ns": outcome.finished_unix_ns,
        },
        "units": {"cpu_seconds": "seconds", "memory_peak_bytes": "bytes"},
        "unavailable_reason": reason,
    }


def _observed_resources(
    outcome: CommandOutcome, *, unavailable_reason: str | None = None
) -> dict[str, object]:
    if outcome.cancelled:
        return _unavailable_observation(outcome, "execution_cancelled_before_final_measurement")
    if outcome.timed_out:
        return _unavailable_observation(outcome, "execution_timed_out_before_final_measurement")
    if unavailable_reason is not None:
        return _unavailable_observation(outcome, unavailable_reason)

    lines = [line for line in outcome.control_output.splitlines() if line]
    if not lines:
        return _unavailable_observation(outcome, "resource_measurement_frame_missing")
    if len(lines) != 1 or not lines[0].startswith(_RESOURCE_CONTROL_PREFIX):
        return _unavailable_observation(outcome, "resource_measurement_frame_invalid")
    fields = lines[0].split("\t")
    if len(fields) == 3 and fields[1] == "unavailable":
        reason = fields[2]
        if reason not in {"cgroup_metrics_unavailable", "final_cgroup_metrics_unavailable"}:
            return _unavailable_observation(outcome, "resource_measurement_frame_invalid")
        return _unavailable_observation(outcome, reason)
    if len(fields) != 7 or fields[1] != "available":
        return _unavailable_observation(outcome, "resource_measurement_frame_invalid")

    source = fields[2]
    if source not in {"cgroup_v1", "cgroup_v2"}:
        return _unavailable_observation(outcome, "resource_measurement_frame_invalid")
    try:
        cpu_start = int(fields[3])
        cpu_end = int(fields[4])
        cpu_scale = int(fields[5])
        memory_peak = int(fields[6])
    except ValueError:
        return _unavailable_observation(outcome, "resource_measurement_frame_invalid")
    if (
        cpu_start < 0
        or cpu_end < cpu_start
        or cpu_scale not in {1_000_000, 1_000_000_000}
        or memory_peak <= 0
        or (source == "cgroup_v2" and cpu_scale != 1_000_000)
        or (source == "cgroup_v1" and cpu_scale != 1_000_000_000)
        or outcome.started_unix_ns is None
        or outcome.finished_unix_ns is None
        or outcome.finished_unix_ns < outcome.started_unix_ns
    ):
        return _unavailable_observation(outcome, "resource_measurement_frame_invalid")
    return {
        "schema": _RESOURCE_SCHEMA,
        "availability": "available",
        "cpu_seconds": round((cpu_end - cpu_start) / cpu_scale, 9),
        "memory_peak_bytes": memory_peak,
        "measurement_source": source,
        "measurement_window": {
            "started_unix_ns": outcome.started_unix_ns,
            "finished_unix_ns": outcome.finished_unix_ns,
        },
        "units": {"cpu_seconds": "seconds", "memory_peak_bytes": "bytes"},
        "unavailable_reason": None,
    }


@dataclass(slots=True)
class DockerContainerKernelExecutor:
    """Execute prepared Python cells in a hardened, immutable-image Docker container."""

    config: ContainerExecutorConfig
    attempt_id: ExecutionAttemptId
    evidence_store: ExecutionEvidenceStore
    runner: CancellableCommandRunner = field(default_factory=AsyncioCommandRunner)
    engine_path: str | None = None

    @property
    def isolation(self) -> ExecutorIsolation:
        return ExecutorIsolation(
            "container",
            True,
            True,
            True,
            "tested",
            "ronin/docker-isolation",
            "1",
            self.config.image,
            "qualification://docker/real-adversarial-v1",
        )

    def _engine(self) -> str | None:
        if self.engine_path is not None:
            return self.engine_path
        return shutil.which(self.config.engine)

    def _container_name(self, cell: CellExecutionRequest) -> str:
        identity = f"{self.attempt_id}:{cell.cell_id}".encode()
        return "ronin-" + hashlib.sha256(identity).hexdigest()[:32]

    def _measurement_unavailable_reason(self) -> str | None:
        if self.config.limits.pids < 2:
            return "pids_limit_prevents_measurement_supervisor"
        if not isinstance(self.runner, ResourceControlCommandRunner):
            return "runner_control_channel_unavailable"
        return None

    def _docker_args(
        self,
        engine: str,
        cell: CellExecutionRequest,
        *,
        measurement_enabled: bool = True,
    ) -> tuple[str, ...]:
        limits = self.config.limits
        return (
            engine,
            "run",
            "--rm",
            "--name",
            self._container_name(cell),
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(limits.pids),
            "--memory",
            limits.memory,
            "--memory-swap",
            limits.memory,
            "--ulimit",
            f"nofile={limits.nofile}:{limits.nofile}",
            "--cpus",
            limits.cpus,
            "--user",
            self.config.user,
            "--tmpfs",
            _CONTAINER_TMPFS,
            "--workdir",
            _CONTAINER_WORKDIR,
            "-i",
            self.config.image,
            *(
                ("/bin/sh", "-c", _RESOURCE_WRAPPER, "--", *self.config.command)
                if measurement_enabled
                else self.config.command
            ),
        )

    async def execute(
        self,
        cell: CellExecutionRequest,
        cancellation: CancellationSignal,
    ) -> CellExecutionResult:
        if cancellation.is_cancelled:
            return CellExecutionResult(cell.cell_id, "cancelled")
        if cell.language.casefold() != "python":
            return CellExecutionResult(
                cell.cell_id, "failed", "kernel.container.language_unsupported"
            )
        engine = self._engine()
        if engine is None:
            return CellExecutionResult(
                cell.cell_id, "failed", "kernel.container.engine_unavailable"
            )
        name = self._container_name(cell)
        measurement_unavailable_reason = self._measurement_unavailable_reason()
        measurement_enabled = measurement_unavailable_reason is None
        args = self._docker_args(engine, cell, measurement_enabled=measurement_enabled)
        if measurement_enabled:
            control_runner = cast(ResourceControlCommandRunner, self.runner)
            outcome = await control_runner.run_with_control(
                args,
                input_text=cell.executable_source,
                cancellation=cancellation,
                timeout_seconds=self.config.limits.timeout_seconds,
                cancellation_args=(engine, "rm", "-f", name),
            )
        else:
            outcome = await self.runner.run(
                args,
                input_text=cell.executable_source,
                cancellation=cancellation,
                timeout_seconds=self.config.limits.timeout_seconds,
                cancellation_args=(engine, "rm", "-f", name),
            )
        log_ref = self.evidence_store.persist_json(
            "log",
            self.attempt_id,
            cell,
            {
                "container_name": name,
                "output": redact_sensitive_text(outcome.output),
                "returncode": outcome.returncode,
            },
        )
        resource_ref = self.evidence_store.persist_json(
            "resource",
            self.attempt_id,
            cell,
            {
                "container_name": name,
                "duration_ms": outcome.duration_ms,
                "limits": {
                    "cpus": self.config.limits.cpus,
                    "memory": self.config.limits.memory,
                    "memory_swap": self.config.limits.memory,
                    "pids": self.config.limits.pids,
                    "nofile": self.config.limits.nofile,
                },
                "observed": _observed_resources(
                    outcome, unavailable_reason=measurement_unavailable_reason
                ),
                "instrumentation": {
                    "measurement_supervisor_pids": 1 if measurement_enabled else 0,
                    "effective_container_pids_limit": self.config.limits.pids,
                },
                "execution_identity": {
                    "attempt_id": str(self.attempt_id),
                    "cell_id": str(cell.cell_id),
                    "runtime_image": self.config.image,
                },
                "measurement_scope": (
                    _MEASUREMENT_SCOPE
                    if measurement_enabled
                    else "duration_and_enforced_limits_only"
                ),
            },
        )
        evidence = (log_ref, resource_ref)
        if outcome.cancelled:
            return CellExecutionResult(cell.cell_id, "cancelled", evidence=evidence)
        if outcome.timed_out:
            return CellExecutionResult(cell.cell_id, "failed", "kernel.container.timeout", evidence)
        if outcome.returncode != 0:
            return CellExecutionResult(
                cell.cell_id, "failed", "kernel.container.nonzero_exit", evidence
            )
        return CellExecutionResult(cell.cell_id, "succeeded", evidence=evidence)
