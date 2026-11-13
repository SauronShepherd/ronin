"""Fail-closed qualification of Cloud Studio against local Floci + Terraform."""

from __future__ import annotations

import argparse
import ipaddress
import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from studio_cloud.backends import EmulatorBackend, create_backend
from studio_cloud.engine import CloudResource, CloudTopology, export_terraform

_EXPECTED_TERRAFORM_VERSION = "1.13.5"
_EXPECTED_AWS_PROVIDER_VERSION = "6.65.0"
_FIXTURE_BUCKET = "qualification-bucket"
_FIXTURE_QUEUE = "qualification-queue"


def fixture() -> CloudTopology:
    return CloudTopology(
        resources=(
            CloudResource(
                "bucket", "aws.s3.bucket", "qualification-bucket", {"force_destroy": True}
            ),
            CloudResource("queue", "aws.sqs.queue", "qualification-queue", {}),
        ),
        edges=(("bucket", "queue"),),
    )


def _check_command(stage: str, result: dict[str, object]) -> None:
    if result.get("returncode") != 0:
        raise RuntimeError(f"Terraform {stage} did not return exit code 0: {result}")


def _require_loopback_endpoint(endpoint: str) -> None:
    """Refuse Terraform qualification against a non-local or credentialed URL."""
    try:
        parsed = urlsplit(endpoint)
        hostname = parsed.hostname
        is_loopback = hostname == "localhost" or (
            hostname is not None and ipaddress.ip_address(hostname).is_loopback
        )
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(
            "Floci Terraform qualification requires a valid loopback endpoint"
        ) from exc
    if (
        parsed.scheme != "http"
        or not is_loopback
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Floci Terraform qualification is restricted to a plain loopback endpoint")


def _verify_terraform_version(backend: EmulatorBackend) -> str | None:
    """Check the actual executable when the selected backend exposes its path."""
    executable = getattr(backend, "terraform_executable", None)
    if not isinstance(executable, str) or not executable:
        return None
    completed = subprocess.run(  # noqa: S603 - executable is the configured local Terraform binary
        [executable, "version", "-json"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Terraform version probe failed")
    try:
        version_payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Terraform version probe returned invalid JSON") from exc
    if not isinstance(version_payload, dict):
        raise RuntimeError("Terraform version probe returned invalid JSON")
    actual = version_payload.get("terraform_version")
    if not isinstance(actual, str):
        raise RuntimeError("Terraform version probe omitted a version string")
    if actual != _EXPECTED_TERRAFORM_VERSION:
        raise RuntimeError(f"Terraform {_EXPECTED_TERRAFORM_VERSION} is required; found {actual!r}")
    return actual


def _list_floci_fixture_resources(endpoint: str) -> list[str]:
    """Read the fixture's real S3/SQS resources from Floci, not just Terraform state."""
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "Floci resource verification requires the boto3 data-plane extra"
        ) from exc

    config = Config(
        connect_timeout=3,
        read_timeout=3,
        retries={"max_attempts": 0},
        s3={"addressing_style": "path"},
    )
    client_options = {
        "endpoint_url": endpoint,
        "region_name": "us-east-1",
        "aws_access_key_id": "cloud-studio",
        "aws_secret_access_key": "cloud-studio",
        "config": config,
    }
    s3 = boto3.client("s3", **client_options)
    sqs = boto3.client("sqs", **client_options)
    residual: list[str] = []
    buckets = s3.list_buckets().get("Buckets", [])
    if any(bucket.get("Name") == _FIXTURE_BUCKET for bucket in buckets):
        residual.append(f"s3://{_FIXTURE_BUCKET}")
    paginator = sqs.get_paginator("list_queues")
    for page in paginator.paginate(QueueNamePrefix=_FIXTURE_QUEUE):
        for queue_url in page.get("QueueUrls", []):
            queue_name = urlsplit(queue_url).path.rsplit("/", 1)[-1]
            if queue_name == _FIXTURE_QUEUE:
                residual.append(f"sqs://{_FIXTURE_QUEUE}")
    return sorted(set(residual))


def qualify(
    endpoint: str,
    workspace: str,
    terraform: bool = False,
    *,
    backend: EmulatorBackend | None = None,
    backend_kind: str = "floci",
    command_timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    Path(workspace).mkdir(parents=True, exist_ok=True)
    selected = backend or create_backend(backend_kind, endpoint, workspace_dir=workspace)
    if hasattr(selected, "command_timeout_seconds"):
        selected.command_timeout_seconds = command_timeout_seconds
    topology = fixture()
    config = export_terraform(topology)
    result: dict[str, Any] = {
        "schema": "ronin.cloud-studio.floci-qualification/v1",
        "backend": backend_kind,
        "endpoint": endpoint,
        "workspace": str(Path(workspace).resolve()),
        "health": None,
        "topology_valid": not topology.validate(),
        "terraform_config_generated": bool(config),
        "terraform_versions": {
            "terraform": _EXPECTED_TERRAFORM_VERSION,
            "aws_provider": _EXPECTED_AWS_PROVIDER_VERSION,
        },
        "terraform": {},
        "residual_resources": [],
        "floci_fixture_resources_after_apply": None,
        "floci_fixture_residual_resources": None,
        "errors": [],
        "status": "blocked",
    }
    try:
        _require_loopback_endpoint(endpoint)
    except ValueError as exc:
        result["errors"].append(str(exc))
        result["status"] = "failed"
        return result
    result["health"] = selected.health()
    if not result["health"].get("available"):
        result["errors"].append("Floci health check failed")
        result["status"] = "failed"
        return result
    if topology.validate() or not config:
        result["errors"].append("qualification topology is invalid or empty")
        result["status"] = "failed"
        return result
    if not terraform:
        result["reason"] = "Terraform qualification was not requested; no PASS is permitted"
        return result

    apply_attempted = False
    try:
        actual_terraform_version = _verify_terraform_version(selected)
        if actual_terraform_version is not None:
            result["terraform_versions"]["terraform"] = actual_terraform_version
        validate = getattr(selected, "validate", None)
        if callable(validate):
            validated = validate()
            result["terraform"]["validate"] = validated
            _check_command("validate", validated)
        plan = selected.plan(topology)
        result["terraform"]["plan"] = plan
        _check_command("plan", plan)
        apply_attempted = True
        applied = selected.apply(topology)
        result["terraform"]["apply"] = applied
        _check_command("apply", applied)
        if getattr(selected, "name", None) == "floci":
            resources = _list_floci_fixture_resources(endpoint)
            result["floci_fixture_resources_after_apply"] = resources
            expected = {f"s3://{_FIXTURE_BUCKET}", f"sqs://{_FIXTURE_QUEUE}"}
            missing = sorted(expected - set(resources))
            if missing:
                raise RuntimeError(
                    "Floci did not expose the applied fixture resources: " + ", ".join(missing)
                )
        refreshed = selected.refresh()
        result["terraform"]["refresh"] = refreshed
        _check_command("refresh", refreshed)
    except Exception as exc:  # keep failure evidence serializable for the caller
        result["errors"].append(f"Terraform qualification failed: {exc}")
    finally:
        if apply_attempted:
            try:
                destroyed = selected.destroy()
                result["terraform"]["destroy"] = destroyed
                _check_command("destroy", destroyed)
            except Exception as exc:
                result["errors"].append(f"Terraform destroy failed: {exc}")
            try:
                state = selected.state_list()
                result["terraform"]["state_list"] = state
                _check_command("state list", state)
                stdout = state.get("stdout")
                residual = [line.strip() for line in str(stdout or "").splitlines() if line.strip()]
                result["residual_resources"] = residual
                if residual:
                    result["errors"].append(
                        "Terraform state is not empty after destroy: " + ", ".join(residual)
                    )
            except Exception as exc:
                result["errors"].append(f"Terraform state verification failed: {exc}")
            if getattr(selected, "name", None) == "floci":
                try:
                    resources = _list_floci_fixture_resources(endpoint)
                    result["floci_fixture_residual_resources"] = resources
                    if resources:
                        result["errors"].append(
                            "Floci fixture resources remain after destroy: " + ", ".join(resources)
                        )
                except Exception as exc:
                    result["errors"].append(f"Floci fixture resource verification failed: {exc}")

    result["status"] = "failed" if result["errors"] else "passed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:4566")
    parser.add_argument("--backend", choices=("floci", "localstack"), default="floci")
    parser.add_argument("--command-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--workspace", default=".ronin/cloud-studio/qualification/floci")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--terraform",
        action="store_true",
        help="run plan/apply/refresh/destroy and verify empty state",
    )
    args = parser.parse_args()
    result = qualify(
        args.endpoint,
        args.workspace,
        args.terraform,
        backend_kind=args.backend,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    if args.evidence:
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
