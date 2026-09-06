from __future__ import annotations

from pathlib import Path

import pytest
from studio_kernel import ExecutionAttemptId
from studio_runners.container import (
    ContainerExecutionLimits,
    ContainerExecutorConfig,
    DockerContainerKernelExecutor,
    LocalExecutionEvidenceStore,
)

_IMAGE = "sha256:" + "a" * 64


def test_memory_requires_explicit_unit() -> None:
    with pytest.raises(ValueError, match="explicit"):
        ContainerExecutionLimits(memory="512")
    assert ContainerExecutionLimits(memory="512m").memory == "512m"


def test_docker_args_cap_swap_and_nofile(tmp_path: Path) -> None:
    limits = ContainerExecutionLimits(memory="256m", nofile=2048)
    executor = DockerContainerKernelExecutor(
        ContainerExecutorConfig(_IMAGE, limits=limits),
        ExecutionAttemptId("attempt-resource-limits"),
        LocalExecutionEvidenceStore(tmp_path),
        engine_path="docker",
    )
    from studio_kernel import CellExecutionRequest, KernelDirective
    from studio_notebook import CellId

    cell = CellExecutionRequest(
        CellId("cell-1"),
        "print('ok')",
        "print('ok')",
        "python",
        (),
        KernelDirective("test", "source.execute"),
    )
    args = executor._docker_args("docker", cell)  # noqa: SLF001
    assert args[args.index("--memory") + 1] == "256m"
    assert args[args.index("--memory-swap") + 1] == "256m"
    assert args[args.index("--ulimit") + 1] == "nofile=2048:2048"


def test_nofile_limit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="nofile"):
        ContainerExecutionLimits(nofile=0)
