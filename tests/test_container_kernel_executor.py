from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

import pytest
from studio_kernel import (
    CancellationSignal,
    CancellationToken,
    CellExecutionRequest,
    ExecutionAttemptId,
    ExecutionEvidenceReference,
    KernelDirective,
)
from studio_notebook import CellId
from studio_runners.container import (
    AsyncioCommandRunner,
    CommandOutcome,
    ContainerExecutionLimits,
    ContainerExecutorConfig,
    DockerContainerKernelExecutor,
    LocalExecutionEvidenceStore,
)

_IMAGE = "sha256:" + "a" * 64


def _cell(language: str = "python", source: str = "print('ok')") -> CellExecutionRequest:
    return CellExecutionRequest(
        CellId("cell-1"),
        "print('authored')",
        source,
        language,
        (),
        KernelDirective("test", "source.execute"),
    )


@dataclass
class _Runner:
    outcome: CommandOutcome
    calls: list[tuple[tuple[str, ...], str, float, tuple[str, ...]]] = field(default_factory=list)

    def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        assert cancellation.is_cancelled is False
        self.calls.append((args, input_text, timeout_seconds, cancellation_args))
        return self.outcome


@dataclass
class _EvidenceStore:
    payloads: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def persist_json(
        self,
        kind: str,
        attempt_id: ExecutionAttemptId,
        cell: CellExecutionRequest,
        payload: dict[str, object],
    ) -> ExecutionEvidenceReference:
        assert attempt_id == ExecutionAttemptId("attempt-1")
        assert cell.cell_id == CellId("cell-1")
        assert kind in {"log", "resource"}
        evidence_kind = cast(Literal["log", "resource"], kind)
        self.payloads.append((kind, payload))
        return ExecutionEvidenceReference(evidence_kind, f"memory://{kind}")


def _executor(
    outcome: CommandOutcome,
    store: _EvidenceStore | None = None,
) -> tuple[DockerContainerKernelExecutor, _Runner, _EvidenceStore]:
    runner = _Runner(outcome)
    evidence = store or _EvidenceStore()
    executor = DockerContainerKernelExecutor(
        ContainerExecutorConfig(_IMAGE),
        ExecutionAttemptId("attempt-1"),
        evidence,
        runner,
        "/usr/bin/docker",
    )
    return executor, runner, evidence


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"cpus": "0"}, "CPU"),
        ({"cpus": "invalid"}, "CPU"),
        ({"memory": "0m"}, "memory"),
        ({"pids": 0}, "PID"),
        ({"timeout_seconds": 0.0}, "timeout"),
    ],
)
def test_container_limits_reject_invalid_values(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ContainerExecutionLimits(**kwargs)  # type: ignore[arg-type]


def test_container_config_requires_immutable_clean_identity_and_command() -> None:
    ContainerExecutorConfig(_IMAGE)
    ContainerExecutorConfig("repo/image@sha256:" + "b" * 64)
    ContainerExecutorConfig(_IMAGE, user="1000:1000")

    for image in ("python:latest", " sha256:" + "a" * 64, "bad image@sha256:" + "a" * 64):
        with pytest.raises(ValueError):
            ContainerExecutorConfig(image)
    with pytest.raises(ValueError, match="engine"):
        ContainerExecutorConfig(_IMAGE, engine="bad\nengine")
    for user in ("", "root", "0:0", "0:1000", "1000:0", "1000"):
        with pytest.raises(ValueError, match="user"):
            ContainerExecutorConfig(_IMAGE, user=user)
    with pytest.raises(ValueError, match="command"):
        ContainerExecutorConfig(_IMAGE, command=())
    with pytest.raises(ValueError, match="argument"):
        ContainerExecutorConfig(_IMAGE, command=("python", "bad\x00arg"))


def test_container_executor_materializes_hardened_isolation_and_evidence() -> None:
    executor, runner, evidence = _executor(
        CommandOutcome(0, "token=secret-value", False, False, 17)
    )

    result = executor.execute(_cell(source="print('executed')"), CancellationToken())

    assert result.state == "succeeded"
    assert result.evidence == (
        ExecutionEvidenceReference("log", "memory://log"),
        ExecutionEvidenceReference("resource", "memory://resource"),
    )
    assert executor.isolation.mode == "container"
    assert executor.isolation.dedicated_identity is True
    assert executor.isolation.network_isolated is True
    assert executor.isolation.filesystem_isolated is True

    args, source, timeout, cancellation_args = runner.calls[0]
    assert source == "print('executed')"
    assert timeout == 300.0
    assert args[:5] == ("/usr/bin/docker", "run", "--rm", "--name", cancellation_args[-1])
    assert ("--network", "none") == (args[5], args[6])
    assert "--read-only" in args
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert args[args.index("--security-opt") + 1] == "no-new-privileges"
    assert args[args.index("--pids-limit") + 1] == "128"
    assert args[args.index("--memory") + 1] == "512m"
    assert args[args.index("--cpus") + 1] == "1.0"
    assert args[args.index("--user") + 1] == "65532:65532"
    assert args[args.index("--tmpfs") + 1] == "/tmp:rw,noexec,nosuid,nodev,size=64m"
    assert args[args.index("--workdir") + 1] == "/tmp"
    assert args[-4:] == (_IMAGE, "python", "-I", "-")
    assert cancellation_args[:3] == ("/usr/bin/docker", "rm", "-f")

    log_payload = evidence.payloads[0][1]
    resource_payload = evidence.payloads[1][1]
    assert "secret-value" not in str(log_payload)
    assert "[REDACTED]" in str(log_payload)
    assert resource_payload["duration_ms"] == 17
    assert resource_payload["measurement_scope"] == "duration_and_enforced_limits_only"


@pytest.mark.parametrize(
    ("outcome", "state", "failure"),
    [
        (CommandOutcome(137, "", True, False, 1), "cancelled", None),
        (CommandOutcome(-1, "", False, True, 1), "failed", "kernel.container.timeout"),
        (CommandOutcome(2, "", False, False, 1), "failed", "kernel.container.nonzero_exit"),
    ],
)
def test_container_executor_normalizes_runtime_outcomes(
    outcome: CommandOutcome, state: str, failure: str | None
) -> None:
    executor, _, _ = _executor(outcome)
    result = executor.execute(_cell(), CancellationToken())
    assert result.state == state
    assert result.failure_code == failure
    assert {reference.kind for reference in result.evidence} == {"log", "resource"}


def test_container_executor_fails_closed_before_launch() -> None:
    executor, runner, _ = _executor(CommandOutcome(0, "", False, False, 1))
    token = CancellationToken()
    token.cancel()
    assert executor.execute(_cell(), token).state == "cancelled"
    assert runner.calls == []

    unsupported = executor.execute(_cell(language="sql"), CancellationToken())
    assert unsupported.failure_code == "kernel.container.language_unsupported"
    assert runner.calls == []

    executor.engine_path = None
    executor.config = ContainerExecutorConfig(_IMAGE, engine="ronin-engine-that-does-not-exist")
    unavailable = executor.execute(_cell(), CancellationToken())
    assert unavailable.failure_code == "kernel.container.engine_unavailable"
    assert runner.calls == []


def test_local_evidence_store_persists_canonical_opaque_json(tmp_path: Path) -> None:
    store = LocalExecutionEvidenceStore(tmp_path)
    cell = _cell()
    reference = store.persist_json(
        "resource",
        ExecutionAttemptId("attempt-1"),
        cell,
        {"z": 1, "a": "value"},
    )
    assert reference.kind == "resource"
    assert reference.ref.startswith("local-evidence://")
    relative = reference.ref.removeprefix("local-evidence://")
    payload_path = tmp_path / relative
    assert json.loads(payload_path.read_text(encoding="utf-8")) == {"a": "value", "z": 1}
    assert payload_path.read_text(encoding="utf-8").endswith("\n")
    assert "attempt-1" not in reference.ref
    assert "cell-1" not in reference.ref
    with pytest.raises(ValueError, match="log/resource"):
        store.persist_json("cost", ExecutionAttemptId("attempt-1"), cell, {})


def test_asyncio_command_runner_redacts_output_within_limit() -> None:
    outcome = AsyncioCommandRunner(max_output_bytes=256).run(
        (sys.executable, "-c", "print('token=super-secret-value')"),
        input_text="",
        cancellation=CancellationToken(),
        timeout_seconds=2.0,
        cancellation_args=(sys.executable, "-c", "pass"),
    )
    assert outcome.returncode == 0
    assert outcome.cancelled is False
    assert outcome.timed_out is False
    assert "super-secret-value" not in outcome.output
    assert "[REDACTED]" in outcome.output
    assert outcome.duration_ms >= 0


def test_asyncio_command_runner_discards_oversized_output_fail_closed() -> None:
    outcome = AsyncioCommandRunner(max_output_bytes=32).run(
        (sys.executable, "-c", "print('token=super-secret-value-' + 'x' * 100)"),
        input_text="",
        cancellation=CancellationToken(),
        timeout_seconds=2.0,
        cancellation_args=(sys.executable, "-c", "pass"),
    )
    assert outcome.returncode == 0
    assert outcome.output == "[OUTPUT TRUNCATED]"
    assert "super-secret-value" not in outcome.output


def test_asyncio_command_runner_times_out_and_kills_slow_cleanup() -> None:
    runner = AsyncioCommandRunner(poll_seconds=0.005, cleanup_timeout_seconds=0.005)
    outcome = runner.run(
        (sys.executable, "-c", "import time; time.sleep(10)"),
        input_text="",
        cancellation=CancellationToken(),
        timeout_seconds=0.01,
        cancellation_args=(sys.executable, "-c", "import time; time.sleep(10)"),
    )
    assert outcome.timed_out is True
    assert outcome.cancelled is False
    assert outcome.returncode != 0


def test_asyncio_command_runner_observes_cancellation() -> None:
    token = CancellationToken()
    timer = threading.Thread(target=lambda: (time.sleep(0.02), token.cancel()))
    timer.start()
    try:
        outcome = AsyncioCommandRunner(poll_seconds=0.005).run(
            (sys.executable, "-c", "import time; time.sleep(10)"),
            input_text="",
            cancellation=token,
            timeout_seconds=2.0,
            cancellation_args=(sys.executable, "-c", "pass"),
        )
    finally:
        timer.join()
    assert outcome.cancelled is True
    assert outcome.timed_out is False


def test_asyncio_command_runner_validates_configuration_and_commands() -> None:
    with pytest.raises(ValueError, match="timeouts"):
        AsyncioCommandRunner(poll_seconds=0)
    with pytest.raises(ValueError, match="timeouts"):
        AsyncioCommandRunner(cleanup_timeout_seconds=0)
    with pytest.raises(ValueError, match="output"):
        AsyncioCommandRunner(max_output_bytes=0)

    runner = AsyncioCommandRunner()
    with pytest.raises(ValueError, match="commands"):
        runner.run(
            (),
            input_text="",
            cancellation=CancellationToken(),
            timeout_seconds=1.0,
            cancellation_args=(sys.executable,),
        )
    with pytest.raises(ValueError, match="commands"):
        runner.run(
            (sys.executable,),
            input_text="",
            cancellation=CancellationToken(),
            timeout_seconds=1.0,
            cancellation_args=(),
        )
