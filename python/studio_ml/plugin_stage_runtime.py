"""Isolated OCI execution adapter for declarative ML plugin stages."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json
from studio_core.plugins import PipelineStageContribution
from studio_kernel import CancellationSignal
from studio_runners.container import AsyncioCommandRunner

MAX_PLUGIN_STAGE_REQUEST_BYTES = 1024 * 1024
MAX_PLUGIN_STAGE_RESPONSE_BYTES = 1024 * 1024
MAX_PLUGIN_STAGE_ARTIFACTS = 8
MAX_PLUGIN_STAGE_ARTIFACT_BYTES = 512 * 1024


class PluginStageExecutionError(RuntimeError):
    """An isolated plugin stage failed, exceeded a limit or returned invalid data."""


@dataclass(frozen=True, slots=True)
class PluginStageArtifact:
    name: str
    media_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class PluginStageOutput:
    value: Mapping[str, object]
    artifacts: tuple[PluginStageArtifact, ...] = ()


class _NeverCancelled:
    @property
    def is_cancelled(self) -> bool:
        return False


def _canonical_payload(value: Mapping[str, object]) -> tuple[str, str]:
    encoder = json.JSONEncoder(
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    chunks: list[bytes] = []
    size = 0
    for part in encoder.iterencode(value):
        encoded_part = part.encode("utf-8")
        size += len(encoded_part)
        if size > MAX_PLUGIN_STAGE_REQUEST_BYTES:
            raise PluginStageExecutionError("plugin stage request exceeds the host payload limit")
        chunks.append(encoded_part)
    encoded = b"".join(chunks)
    return encoded.decode("utf-8"), hashlib.sha256(encoded).hexdigest()


def _invoke(
    contribution: PipelineStageContribution,
    payload: Mapping[str, object],
    cancellation: CancellationSignal | None,
) -> Mapping[str, object]:
    contribution.validate()
    request_body, request_digest = _canonical_payload(payload)
    container_name = f"ronin-ml-stage-{uuid4().hex}"
    memory_limit = contribution.memory_limit
    args = (
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull=missing",
        "--name",
        container_name,
        "--network=none",
        "--ipc=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user=65532:65532",
        "--cpus",
        contribution.cpu_limit,
        "--memory",
        memory_limit,
        "--memory-swap",
        memory_limit,
        "--pids-limit",
        str(contribution.pids_limit),
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m",  # noqa: S108 - hardened isolated container tmpfs
        contribution.executor_image,
        "ronin-plugin-stage",
        contribution.operation_id,
        request_digest,
    )
    signal = cancellation or _NeverCancelled()

    async def run_container() -> object:
        return await AsyncioCommandRunner(
            max_output_bytes=MAX_PLUGIN_STAGE_RESPONSE_BYTES,
            discard_stderr=True,
            redact_output=False,
            strict_output_utf8=True,
        ).run(
            args,
            input_text=request_body,
            cancellation=signal,
            timeout_seconds=contribution.timeout_seconds,
            cancellation_args=("docker", "rm", "--force", container_name),
        )

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            outcome = asyncio.run(run_container())
        else:
            result: list[object] = []
            failure: list[BaseException] = []

            def run_on_worker_thread() -> None:
                try:
                    result.append(asyncio.run(run_container()))
                except BaseException as exc:  # propagate worker-thread failures to the caller
                    failure.append(exc)

            worker = threading.Thread(target=run_on_worker_thread, daemon=True)
            worker.start()
            worker.join(contribution.timeout_seconds + 10)
            if worker.is_alive():
                cancel = getattr(signal, "cancel", None)
                if callable(cancel):
                    cancel()
                worker.join(2)
                raise PluginStageExecutionError(
                    "plugin stage runner did not stop after its deadline"
                )
            if failure:
                error = failure[0]
                if isinstance(error, PluginStageExecutionError):
                    raise error
                if isinstance(error, asyncio.CancelledError):
                    raise PluginStageExecutionError(
                        "plugin stage execution was cancelled"
                    ) from error
                if isinstance(error, Exception):
                    raise PluginStageExecutionError(
                        "plugin stage container could not be executed"
                    ) from error
                raise error
            outcome = result[0]
    except PluginStageExecutionError:
        raise
    except asyncio.CancelledError as exc:
        raise PluginStageExecutionError("plugin stage execution was cancelled") from exc
    except Exception as exc:
        raise PluginStageExecutionError("plugin stage container could not be executed") from exc

    if getattr(outcome, "cancelled", False):
        raise PluginStageExecutionError("plugin stage execution was cancelled")
    if getattr(outcome, "timed_out", False):
        raise PluginStageExecutionError("plugin stage exceeded its execution timeout")
    if getattr(outcome, "returncode", 1) != 0:
        raise PluginStageExecutionError("plugin stage container returned a failure status")
    output = getattr(outcome, "output", "")
    if not isinstance(output, str) or len(output.encode("utf-8")) > MAX_PLUGIN_STAGE_RESPONSE_BYTES:
        raise PluginStageExecutionError("plugin stage response exceeds the host payload limit")
    try:
        response = decode_canonical_json(output)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PluginStageExecutionError("plugin stage returned invalid JSON") from exc
    if not isinstance(response, Mapping) or any(not isinstance(key, str) for key in response):
        raise PluginStageExecutionError("plugin stage output must be a JSON object")
    if encode_canonical_json(response).decode("utf-8") != output:
        raise PluginStageExecutionError("plugin stage response must use canonical JSON")
    if not re.fullmatch(r"[0-9a-f]{64}", request_digest):
        raise PluginStageExecutionError("plugin stage request identity is invalid")
    return dict(response)


def execute_plugin_stage(
    contribution: PipelineStageContribution,
    *,
    config: Mapping[str, object],
    inputs: Mapping[str, object],
    artifacts: Mapping[str, bytes] | None = None,
    cancellation: CancellationSignal | None = None,
) -> PluginStageOutput:
    """Run plugin code in a pinned, networkless, resource-limited container.

    The only data plane is bounded canonical JSON on stdin/stdout. Artifact
    reads are limited to declared upstream references; artifact writes return
    bounded base64 data for host verification and persistence under the shared
    reference writer lease. The container receives no host mounts, credentials,
    inherited environment or network.
    """
    contribution.validate()
    if set(config) - set(contribution.config_fields):
        raise PluginStageExecutionError("plugin stage configuration contains undeclared fields")
    if set(inputs) != set(contribution.input_ports):
        raise PluginStageExecutionError("plugin stage inputs do not match the declared ports")
    artifact_payload = artifacts or {}
    if artifact_payload and "artifact:read" not in contribution.permissions:
        raise PluginStageExecutionError("plugin stage has no artifact:read permission")
    if any(
        not isinstance(name, str) or not isinstance(data, bytes)
        for name, data in artifact_payload.items()
    ):
        raise PluginStageExecutionError("plugin stage artifact inputs are invalid")
    if sum(len(data) for data in artifact_payload.values()) > MAX_PLUGIN_STAGE_ARTIFACT_BYTES:
        raise PluginStageExecutionError("plugin stage artifact inputs exceed the host limit")
    request: dict[str, object] = {
        "schema": "ronin.ml-plugin-stage-request/v1",
        "plugin_id": contribution.plugin_id,
        "stage_id": contribution.stage_id,
        "stage_version": contribution.version,
        "plugin_version": contribution.plugin_version,
        "distribution_digest": contribution.distribution_digest,
        "operation_id": contribution.operation_id,
        "config": dict(config),
        "inputs": dict(inputs),
        "artifacts": {
            name: base64.b64encode(data).decode("ascii")
            for name, data in sorted(artifact_payload.items())
        },
    }
    response = _invoke(contribution, request, cancellation)
    if set(response) - {"output", "artifacts"}:
        raise PluginStageExecutionError("plugin stage response has unsupported fields")
    output = response.get("output")
    if not isinstance(output, Mapping):
        raise PluginStageExecutionError("plugin stage output must be a JSON object")
    raw_artifacts = response.get("artifacts", [])
    if not isinstance(raw_artifacts, list) or len(raw_artifacts) > MAX_PLUGIN_STAGE_ARTIFACTS:
        raise PluginStageExecutionError("plugin stage returned an invalid artifact list")
    if raw_artifacts and contribution.effect != "artifact_write":
        raise PluginStageExecutionError("pure plugin stages cannot write artifacts")
    parsed_artifacts: list[PluginStageArtifact] = []
    seen_names: set[str] = set()
    total_artifact_bytes = 0
    for item in raw_artifacts:
        if not isinstance(item, Mapping) or set(item) != {
            "name",
            "media_type",
            "data_base64",
        }:
            raise PluginStageExecutionError("plugin stage artifact has an invalid shape")
        name, media_type, encoded = item["name"], item["media_type"], item["data_base64"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}", name)
            or name in seen_names
            or not isinstance(media_type, str)
            or not re.fullmatch(
                r"[a-zA-Z0-9][a-zA-Z0-9.+-]*/[a-zA-Z0-9][a-zA-Z0-9.+-]*",
                media_type,
            )
            or len(media_type) > 127
            or not isinstance(encoded, str)
        ):
            raise PluginStageExecutionError("plugin stage artifact metadata is invalid")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise PluginStageExecutionError("plugin stage artifact data is invalid base64") from exc
        total_artifact_bytes += len(data)
        if total_artifact_bytes > MAX_PLUGIN_STAGE_ARTIFACT_BYTES:
            raise PluginStageExecutionError("plugin stage artifacts exceed the host byte limit")
        seen_names.add(name)
        parsed_artifacts.append(PluginStageArtifact(name, media_type, data))
    return PluginStageOutput(dict(output), tuple(parsed_artifacts))


__all__ = (
    "PluginStageArtifact",
    "PluginStageExecutionError",
    "PluginStageOutput",
    "execute_plugin_stage",
)
