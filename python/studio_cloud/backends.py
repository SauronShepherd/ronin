"""Backend abstraction for Cloud Studio emulation providers.

Only this module knows how an external emulator is addressed. The topology,
editor and plugin API remain provider-neutral.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .engine import CloudEmulator, CloudTopology, export_terraform


class EmulatorBackend(Protocol):
    name: str
    endpoint: str | None

    def apply(self, topology: CloudTopology) -> dict[str, object]: ...

    def health(self) -> dict[str, object]: ...

    def plan(self, topology: CloudTopology) -> dict[str, object]: ...

    def refresh(self) -> dict[str, object]: ...

    def destroy(self) -> dict[str, object]: ...


@dataclass
class InMemoryBackend:
    emulator: CloudEmulator
    name: str = "in-memory"
    endpoint: str | None = None

    def apply(self, topology: CloudTopology) -> dict[str, object]:
        return self.emulator.apply(topology)

    def health(self) -> dict[str, object]:
        return {"backend": self.name, "available": True, "endpoint": self.endpoint}

    def plan(self, topology: CloudTopology) -> dict[str, object]:
        return self.emulator.plan(topology)

    def refresh(self) -> dict[str, object]:
        return self.emulator.refresh()

    def destroy(self) -> dict[str, object]:
        return self.emulator.destroy()


@dataclass
class HttpEmulatorBackend:
    """Connection descriptor for AWS-wire-compatible external emulators.

    The HTTP request adapter is intentionally injected later; Cloud Studio does
    not make network calls merely by importing or selecting a backend.
    """

    name: str
    endpoint: str | None
    license_required: bool = False
    timeout_seconds: float = 2.0

    def apply(self, topology: CloudTopology) -> dict[str, object]:
        errors = topology.validate()
        if errors:
            raise ValueError("invalid topology: " + "; ".join(errors))
        return {"status": "delegated", "backend": self.name, "endpoint": self.endpoint}

    def plan(self, topology: CloudTopology) -> dict[str, object]:
        return {"status": "delegated", "backend": self.name, "valid": not topology.validate()}

    def refresh(self) -> dict[str, object]:
        return {"status": "delegated", "backend": self.name}

    def destroy(self) -> dict[str, object]:
        return {"status": "delegated", "backend": self.name}

    def health(self) -> dict[str, object]:
        result: dict[str, object] = {
            "backend": self.name,
            "available": False,
            "endpoint": self.endpoint,
            "license_required": self.license_required,
        }
        try:
            if self.endpoint is None:
                raise ValueError("emulator endpoint is not configured")
            if urlparse(self.endpoint).scheme not in {"http", "https"}:
                raise ValueError("emulator endpoint must use http or https")
            request = Request(self.endpoint, method="GET")  # noqa: S310
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                result["available"] = 200 <= response.status < 500
                result["status_code"] = response.status
        except (OSError, URLError, TimeoutError) as exc:
            result["error"] = str(exc)
        return result


@dataclass
class TerraformEmulatorBackend(HttpEmulatorBackend):
    """Execute Terraform against an AWS-wire-compatible local emulator."""

    workspace_dir: str = ".ronin/cloud-studio/terraform"
    terraform_executable: str = "terraform"
    command_timeout_seconds: float = 120.0
    plugin_cache_dir: str | None = None
    initialized: bool = False

    def _run(self, *arguments: str) -> dict[str, object]:
        environment = os.environ.copy()
        if self.plugin_cache_dir:
            Path(self.plugin_cache_dir).mkdir(parents=True, exist_ok=True)
            environment["TF_PLUGIN_CACHE_DIR"] = self.plugin_cache_dir
        try:
            completed = subprocess.run(  # noqa: S603 - executable is a configured local Terraform binary
                [self.terraform_executable, f"-chdir={self.workspace_dir}", *arguments],
                capture_output=True,
                text=True,
                timeout=self.command_timeout_seconds,
                check=False,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"Terraform command timed out after {self.command_timeout_seconds}s: {arguments}"
            ) from exc
        result: dict[str, object] = {
            "command": list(arguments),
            "returncode": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }
        if completed.returncode:
            raise RuntimeError(json.dumps(result))
        return result

    def _write_config(self, topology: CloudTopology) -> None:
        errors = topology.validate()
        if errors:
            raise ValueError("invalid topology: " + "; ".join(errors))
        root = Path(self.workspace_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "main.tf").write_text(
            terraform_provider_config(self) + "\n" + export_terraform(topology), encoding="utf-8"
        )

    def _ensure_initialized(self) -> None:
        if not self.initialized:
            self._run("init", "-backend=false", "-input=false")
            self.initialized = True

    def plan(self, topology: CloudTopology) -> dict[str, object]:
        self._write_config(topology)
        self._ensure_initialized()
        return self._run("plan", "-input=false", "-no-color")

    def apply(self, topology: CloudTopology) -> dict[str, object]:
        self._write_config(topology)
        self._ensure_initialized()
        return self._run("apply", "-auto-approve", "-input=false", "-no-color")

    def refresh(self) -> dict[str, object]:
        self._ensure_initialized()
        return self._run("refresh", "-input=false", "-no-color")

    def destroy(self) -> dict[str, object]:
        self._ensure_initialized()
        return self._run("destroy", "-auto-approve", "-input=false", "-no-color")


def terraform_provider_config(
    backend: EmulatorBackend, services: tuple[str, ...] = ("s3", "lambda", "sqs", "dynamodb")
) -> str:
    """Render endpoint overrides compatible with the AWS Terraform provider."""
    if backend.endpoint is None:
        return 'provider "aws" { region = "us-east-1" }\n'
    endpoints = "\n".join(f'    {service} = "{backend.endpoint}"' for service in services)
    return (
        'provider "aws" {\n'
        '  region                      = "us-east-1"\n'
        '  access_key                  = "cloud-studio"\n'
        '  secret_key                  = "cloud-studio"\n'
        "  skip_credentials_validation = true\n"
        "  skip_metadata_api_check     = true\n"
        "  skip_requesting_account_id  = true\n"
        "  s3_use_path_style           = true\n"
        "  endpoints {\n" + endpoints + "\n  }\n}\n"
    )


def create_backend(
    kind: str = "in-memory",
    endpoint: str | None = None,
    workspace_dir: str | None = None,
    iac_executable: str = "terraform",
) -> EmulatorBackend:
    if kind == "in-memory":
        return InMemoryBackend(CloudEmulator())
    if kind == "floci":
        return TerraformEmulatorBackend(
            "floci",
            endpoint or "http://127.0.0.1:4566",
            workspace_dir=workspace_dir or ".ronin/cloud-studio/terraform/floci",
            plugin_cache_dir=os.getenv("TF_PLUGIN_CACHE_DIR") or None,
            terraform_executable=iac_executable,
        )
    if kind == "localstack":
        return TerraformEmulatorBackend(
            "localstack",
            endpoint or "http://127.0.0.1:4566",
            license_required=True,
            workspace_dir=workspace_dir or ".ronin/cloud-studio/terraform/localstack",
            plugin_cache_dir=os.getenv("TF_PLUGIN_CACHE_DIR") or None,
            terraform_executable=iac_executable,
        )
    raise ValueError(f"unsupported emulator backend: {kind}")
