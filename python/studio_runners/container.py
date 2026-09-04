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
from typing import Literal, Protocol, cast

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
_MEMORY_LIMIT = re.compile(r"^[1-9][0-9]*(?:[kKmMgG])?$")
_CONTAINER_USER = re.compile(r"^[1-9][0-9]*:[1-9][0-9]*$")
_READ_CHUNK_BYTES = 64 * 1024
_TRUNCATED_OUTPUT = "[OUTPUT TRUNCATED]"
_CONTAINER_TMPFS = "/tmp:rw,noexec,nosuid,nodev,size=64m"  # noqa: S108
_CONTAINER_WORKDIR = "/tmp"  # noqa: S108


def _require_single_line(value: str, name: str) -> None:
    if not value or value.strip() != value or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, NUL-free, and single-line")


@dataclass(frozen=True, slots=True)
class ContainerExecutionLimits:
    """Explicit container ceilings; these are limits, not observed resource usage."""

    cpus: str = "1.0"
    memory: str = "512m"
    pids: int = 128
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not _CPU_LIMIT.fullmatch(self.cpus) or float(self.cpus) <= 0:
            raise ValueError("container CPU limit must be a positive decimal")
        if not _MEMORY_LIMIT.fullmatch(self.memory):
            raise ValueError("container memory limit must be a positive Docker size")
        if self.pids < 1:
            raise ValueError("container PID limit must be positive")
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


@dataclass(frozen=True, slots=True)
class AsyncioCommandRunner:
    """Awaitable subprocess runner with bounded redacted output and hard cancellation."""

    poll_seconds: float = 0.02
    cleanup_timeout_seconds: float = 5.0
    max_output_bytes: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.poll_seconds <= 0 or self.cleanup_timeout_seconds <= 0:
            raise ValueError("command runner timeouts must be positive")
        if self.max_output_bytes < 1:
            raise ValueError("command runner output limit must be positive")

    async def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        if not args or not cancellation_args:
            raise ValueError("execution and cancellation commands must be non-empty")
        started = time.monotonic()
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdin = cast(asyncio.StreamWriter, process.stdin)
        stdout = cast(asyncio.StreamReader, process.stdout)
        stdin.write(input_text.encode())
        await stdin.drain()
        stdin.close()
        output_task = asyncio.create_task(self._collect_output(stdout))
        wait_task = asyncio.create_task(process.wait())
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
        returncode = await wait_task
        raw_output, truncated = await output_task
        if needs_cleanup:
            await self._cleanup(cancellation_args)
        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        output = (
            _TRUNCATED_OUTPUT
            if truncated
            else redact_sensitive_text(raw_output.decode("utf-8", errors="replace"))
        )
        return CommandOutcome(returncode, output, cancelled, timed_out, duration_ms)

    async def _collect_output(self, stream: asyncio.StreamReader) -> tuple[bytes, bool]:
        captured = bytearray()
        truncated = False
        while chunk := await stream.read(_READ_CHUNK_BYTES):
            remaining = max(0, self.max_output_bytes - len(captured))
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
        return ExecutorIsolation("container", True, True, True)

    def _engine(self) -> str | None:
        if self.engine_path is not None:
            return self.engine_path
        return shutil.which(self.config.engine)

    def _container_name(self, cell: CellExecutionRequest) -> str:
        identity = f"{self.attempt_id}:{cell.cell_id}".encode()
        return "ronin-" + hashlib.sha256(identity).hexdigest()[:32]

    def _docker_args(self, engine: str, cell: CellExecutionRequest) -> tuple[str, ...]:
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
            *self.config.command,
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
        outcome = await self.runner.run(
            self._docker_args(engine, cell),
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
                    "pids": self.config.limits.pids,
                },
                "measurement_scope": "duration_and_enforced_limits_only",
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
