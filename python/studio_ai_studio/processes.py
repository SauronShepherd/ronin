"""Opt-in, allowlisted process supervision for local model runtimes."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ProcessPolicyError(ValueError):
    """A managed process profile is unsafe or incomplete."""


@dataclass(frozen=True, slots=True)
class ProcessProfile:
    executable: str
    args: tuple[str, ...]
    cwd: str
    allowed_executables: frozenset[str]
    allowed_directories: frozenset[str]
    env: tuple[tuple[str, str], ...] = ()

    def validate(self) -> None:
        executable = str(Path(self.executable).resolve())
        if executable not in {str(Path(item).resolve()) for item in self.allowed_executables}:
            raise ProcessPolicyError("executable is not allowlisted")
        cwd = str(Path(self.cwd).resolve())
        allowed_directories = tuple(str(Path(item).resolve()) for item in self.allowed_directories)
        if not any(cwd == item or cwd.startswith(item + os.sep) for item in allowed_directories):
            raise ProcessPolicyError("working directory is not allowlisted")
        if not self.args or any("\x00" in value or "\n" in value for value in self.args):
            raise ProcessPolicyError("process arguments contain invalid control characters")
        if any(key.upper() in {"PATH", "PYTHONPATH", "LD_PRELOAD"} for key, _ in self.env):
            raise ProcessPolicyError("dangerous environment override is forbidden")


class Child(Protocol):
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


class ProcessSupervisor:
    def __init__(self, *, launcher: Callable[..., Child] = subprocess.Popen) -> None:
        self._launcher = launcher
        self._child: Child | None = None

    def start(self, profile: ProcessProfile) -> None:
        profile.validate()
        if self._child is not None:
            raise RuntimeError("managed process is already running")
        environment = dict(profile.env)
        self._child = self._launcher(
            [profile.executable, *profile.args],
            cwd=profile.cwd,
            env=environment or None,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self, *, grace_seconds: float = 5.0) -> None:
        if self._child is None:
            return
        child = self._child
        self._child = None
        child.terminate()
        try:
            child.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=grace_seconds)
