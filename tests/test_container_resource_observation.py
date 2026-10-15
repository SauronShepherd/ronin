from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Literal, cast

import pytest
import studio_runners.container as container_module
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
)

_IMAGE = "sha256:" + "a" * 64
_FRAME = "RONIN_RESOURCE_V1\tavailable\tcgroup_v2\t10\t20\t1000000\t4096\n"


def _cell() -> CellExecutionRequest:
    return CellExecutionRequest(
        CellId("cell-resource"),
        "print('authored')",
        "print('executed')",
        "python",
        (),
        KernelDirective("test", "source.execute"),
    )


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
        assert attempt_id == ExecutionAttemptId("attempt-resource")
        assert cell.cell_id == CellId("cell-resource")
        evidence_kind = cast(Literal["log", "resource"], kind)
        self.payloads.append((kind, payload))
        return ExecutionEvidenceReference(evidence_kind, f"memory://{kind}")


@dataclass
class _ControlRunner:
    outcome: CommandOutcome
    plain_calls: list[tuple[str, ...]] = field(default_factory=list)
    control_calls: list[tuple[str, ...]] = field(default_factory=list)

    async def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        del input_text, cancellation, timeout_seconds, cancellation_args
        self.plain_calls.append(args)
        return self.outcome

    async def run_with_control(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        del input_text, cancellation, timeout_seconds, cancellation_args
        self.control_calls.append(args)
        return self.outcome


@dataclass
class _PlainRunner:
    outcome: CommandOutcome
    calls: list[tuple[str, ...]] = field(default_factory=list)

    async def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str,
        cancellation: CancellationSignal,
        timeout_seconds: float,
        cancellation_args: tuple[str, ...],
    ) -> CommandOutcome:
        del input_text, cancellation, timeout_seconds, cancellation_args
        self.calls.append(args)
        return self.outcome


def _outcome(*, frame: str = _FRAME) -> CommandOutcome:
    return CommandOutcome(
        0,
        "ok\n",
        False,
        False,
        17,
        frame,
        1_000_000_000,
        1_100_000_000,
    )


def test_observed_resource_frame_is_strict_and_unit_normalized() -> None:
    observed = container_module._observed_resources(_outcome())  # noqa: SLF001
    assert observed == {
        "schema": "ronin.container-resource-observation/v1",
        "availability": "available",
        "cpu_seconds": 0.00001,
        "memory_peak_bytes": 4096,
        "measurement_source": "cgroup_v2",
        "measurement_window": {
            "started_unix_ns": 1_000_000_000,
            "finished_unix_ns": 1_100_000_000,
        },
        "units": {"cpu_seconds": "seconds", "memory_peak_bytes": "bytes"},
        "unavailable_reason": None,
    }


@pytest.mark.parametrize(
    "frame",
    [
        "RONIN_RESOURCE_V1\tavailable\tother\t10\t20\t1000000\t4096\n",
        "RONIN_RESOURCE_V1\tavailable\tcgroup_v2\t20\t10\t1000000\t4096\n",
        "RONIN_RESOURCE_V1\tavailable\tcgroup_v1\t10\t20\t1000000\t4096\n",
        "RONIN_RESOURCE_V1\tavailable\tcgroup_v2\tx\t20\t1000000\t4096\n",
        (
            "RONIN_RESOURCE_V1\tavailable\tcgroup_v2\t10\t20\t1000000\t4096\n"
            "RONIN_RESOURCE_V1\tunavailable\tcgroup_metrics_unavailable\n"
        ),
    ],
)
def test_invalid_resource_control_frames_fail_closed(frame: str) -> None:
    observed = container_module._observed_resources(_outcome(frame=frame))  # noqa: SLF001
    assert observed["availability"] == "unavailable"
    assert observed["cpu_seconds"] is None
    assert observed["memory_peak_bytes"] is None
    assert observed["unavailable_reason"] == "resource_measurement_frame_invalid"


def test_resource_unavailability_reasons_are_explicit() -> None:
    missing = container_module._observed_resources(_outcome(frame=""))  # noqa: SLF001
    assert missing["unavailable_reason"] == "resource_measurement_frame_missing"

    unavailable = container_module._observed_resources(  # noqa: SLF001
        _outcome(frame="RONIN_RESOURCE_V1\tunavailable\tcgroup_metrics_unavailable\n")
    )
    assert unavailable["unavailable_reason"] == "cgroup_metrics_unavailable"

    cancelled = container_module._observed_resources(  # noqa: SLF001
        CommandOutcome(137, "", True, False, 1)
    )
    assert cancelled["unavailable_reason"] == "execution_cancelled_before_final_measurement"

    timed_out = container_module._observed_resources(  # noqa: SLF001
        CommandOutcome(137, "", False, True, 1)
    )
    assert timed_out["unavailable_reason"] == "execution_timed_out_before_final_measurement"


def test_control_channel_is_private_bounded_and_preserves_diagnostics() -> None:
    script = (
        "import sys; "
        "print('user-output'); "
        "print('engine-diagnostic', file=sys.stderr); "
        f"print({_FRAME.rstrip()!r}, file=sys.stderr)"
    )
    outcome = asyncio.run(
        AsyncioCommandRunner(max_output_bytes=1024, max_control_bytes=1024).run_with_control(
            (sys.executable, "-c", script),
            input_text="",
            cancellation=CancellationToken(),
            timeout_seconds=2.0,
            cancellation_args=(sys.executable, "-c", "pass"),
        )
    )
    assert outcome.returncode == 0
    assert "user-output" in outcome.output
    assert "engine-diagnostic" in outcome.output
    assert "RONIN_RESOURCE_V1" not in outcome.output
    assert outcome.control_output == _FRAME
    assert outcome.started_unix_ns is not None
    assert outcome.finished_unix_ns is not None


def test_executor_persists_observed_usage_separate_from_limits() -> None:
    runner = _ControlRunner(_outcome())
    evidence = _EvidenceStore()
    executor = DockerContainerKernelExecutor(
        ContainerExecutorConfig(
            _IMAGE,
            limits=ContainerExecutionLimits(cpus="0.5", memory="128m", pids=32),
        ),
        ExecutionAttemptId("attempt-resource"),
        evidence,
        runner,
        "/usr/bin/docker",
    )
    result = asyncio.run(executor.execute(_cell(), CancellationToken()))
    assert result.state == "succeeded"
    assert runner.plain_calls == []
    args = runner.control_calls[0]
    assert args[args.index("--pids-limit") + 1] == "32"
    image_index = args.index(_IMAGE)
    assert args[image_index + 1 : image_index + 5] == (
        "/bin/sh",
        "-c",
        container_module._RESOURCE_WRAPPER,  # noqa: SLF001
        "--",
    )
    assert args[-3:] == ("python", "-I", "-")

    resource = next(payload for kind, payload in evidence.payloads if kind == "resource")
    assert resource["limits"] == {
        "cpus": "0.5",
        "memory": "128m",
        "memory_swap": "128m",
        "pids": 32,
        "nofile": 1024,
    }
    assert resource["measurement_scope"] == "observed_cgroup_usage_and_enforced_limits"
    assert resource["instrumentation"] == {
        "measurement_supervisor_pids": 1,
        "effective_container_pids_limit": 32,
    }
    assert resource["execution_identity"] == {
        "attempt_id": "attempt-resource",
        "cell_id": "cell-resource",
        "runtime_image": _IMAGE,
    }
    observed = cast(dict[str, object], resource["observed"])
    assert observed["availability"] == "available"
    assert observed["cpu_seconds"] == 0.00001
    assert observed["memory_peak_bytes"] == 4096


def test_measurement_falls_back_without_lying_when_supervisor_cannot_run() -> None:
    evidence = _EvidenceStore()
    runner = _ControlRunner(_outcome())
    executor = DockerContainerKernelExecutor(
        ContainerExecutorConfig(_IMAGE, limits=ContainerExecutionLimits(pids=1)),
        ExecutionAttemptId("attempt-resource"),
        evidence,
        runner,
        "/usr/bin/docker",
    )
    asyncio.run(executor.execute(_cell(), CancellationToken()))
    assert runner.control_calls == []
    assert runner.plain_calls[0][-4:] == (_IMAGE, "python", "-I", "-")
    resource = next(payload for kind, payload in evidence.payloads if kind == "resource")
    observed = cast(dict[str, object], resource["observed"])
    assert observed["availability"] == "unavailable"
    assert observed["cpu_seconds"] is None
    assert observed["memory_peak_bytes"] is None
    assert observed["unavailable_reason"] == "pids_limit_prevents_measurement_supervisor"
    assert resource["measurement_scope"] == "duration_and_enforced_limits_only"

    plain_evidence = _EvidenceStore()
    plain_runner = _PlainRunner(CommandOutcome(0, "ok\n", False, False, 1))
    plain_executor = DockerContainerKernelExecutor(
        ContainerExecutorConfig(_IMAGE),
        ExecutionAttemptId("attempt-resource"),
        plain_evidence,
        plain_runner,
        "/usr/bin/docker",
    )
    asyncio.run(plain_executor.execute(_cell(), CancellationToken()))
    plain_resource = next(
        payload for kind, payload in plain_evidence.payloads if kind == "resource"
    )
    plain_observed = cast(dict[str, object], plain_resource["observed"])
    assert plain_observed["unavailable_reason"] == "runner_control_channel_unavailable"
    assert plain_runner.calls[0][-4:] == (_IMAGE, "python", "-I", "-")
