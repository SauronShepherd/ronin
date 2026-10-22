"""Provider-neutral remote execution lifecycle."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .backends import (
    BackendCapabilities,
    RemoteConfigurationError,
    RemoteMLBackend,
    RemoteRetryPolicy,
    RemoteTrainingRequest,
    RemoteTrainingResult,
    RemoteTransientError,
    RemoteValidationError,
)

MAX_REMOTE_PREDICTION_ROWS = 100_000
MAX_REMOTE_PREDICTION_BYTES = 8 * 1024 * 1024
MAX_REMOTE_ID_LENGTH = 256


class RemoteExecutionController:
    def __init__(
        self,
        backend: RemoteMLBackend,
        policy: RemoteRetryPolicy | None = None,
        *,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.backend = backend
        self.policy = policy or RemoteRetryPolicy()
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic

    def submit(self, request: RemoteTrainingRequest) -> RemoteTrainingResult:
        deadline = self._clock() + request.timeout_seconds
        for attempt in range(1, self.policy.max_attempts + 1):
            if self._clock() >= deadline:
                raise RemoteTransientError("remote training wall-clock budget expired")
            try:
                return self.backend.submit(request)
            except RemoteTransientError:
                if attempt == self.policy.max_attempts:
                    raise
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise RemoteTransientError(
                        "remote training wall-clock budget expired"
                    ) from None
                self._sleep(min(self.policy.delay_for(attempt), remaining))
        raise AssertionError("unreachable")

    def poll(self, run_id: str) -> RemoteTrainingResult:
        if (
            not isinstance(run_id, str)
            or not run_id
            or run_id != run_id.strip()
            or len(run_id) > MAX_REMOTE_ID_LENGTH
            or any(char in run_id for char in "\r\n\x00")
        ):
            raise ValueError("remote poll run_id must be a bounded identifier")
        return self.backend.poll(run_id)

    def cancel(self, run_id: str) -> RemoteTrainingResult:
        if (
            not isinstance(run_id, str)
            or not run_id
            or run_id != run_id.strip()
            or len(run_id) > MAX_REMOTE_ID_LENGTH
            or any(char in run_id for char in "\r\n\x00")
        ):
            raise ValueError("remote cancel run_id must be a bounded identifier")
        return self.backend.cancel(run_id)


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        raise RemoteConfigurationError("remote redirects are disabled")


class JsonRemoteBackend:
    """HTTP-agnostic JSON adapter; transport is injected for security/testing."""

    def __init__(
        self,
        backend_id: str,
        display_name: str,
        capabilities: BackendCapabilities,
        transport: Callable[[str, Mapping[str, object]], Mapping[str, object]],
    ) -> None:
        self.backend_id = backend_id
        self.display_name = display_name
        self.capabilities = capabilities
        self._transport = transport

    def _result(self, payload: Mapping[str, object]) -> RemoteTrainingResult:
        run_id = payload.get("run_id")
        status = payload.get("status")
        artifact_ref = payload.get("artifact_ref", "")
        artifact_digest = payload.get("artifact_digest", "")
        if not all(
            isinstance(value, str) for value in (run_id, status, artifact_ref, artifact_digest)
        ):
            raise ValueError("remote result identity fields must be text")
        raw_metrics = payload.get("metrics", {})
        if not isinstance(raw_metrics, Mapping):
            raise ValueError("remote metrics must be an object")
        metrics: list[tuple[str, float]] = []
        for key, value in raw_metrics.items():
            if (
                not isinstance(key, str)
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
            ):
                raise ValueError("remote metrics must contain numeric values")
            metric = float(value)
            if not math.isfinite(metric):
                raise ValueError("remote metrics must contain finite values")
            metrics.append((key, metric))
        return RemoteTrainingResult(
            cast(str, run_id),
            cast(str, artifact_ref),
            cast(str, artifact_digest),
            cast(str, status),
            tuple(metrics),
        )

    def submit(self, request: RemoteTrainingRequest) -> RemoteTrainingResult:
        return self._result(self._transport("submit", {"request": asdict(request)}))

    def poll(self, run_id: str) -> RemoteTrainingResult:
        return self._result(self._transport("poll", {"run_id": run_id}))

    def cancel(self, run_id: str) -> RemoteTrainingResult:
        return self._result(self._transport("cancel", {"run_id": run_id}))

    def predict(self, model_ref: str, rows: Sequence[Mapping[str, object]]) -> Sequence[object]:
        if (
            not isinstance(model_ref, str)
            or not model_ref
            or model_ref != model_ref.strip()
            or len(model_ref) > MAX_REMOTE_ID_LENGTH
            or any(char in model_ref for char in "\r\n\x00")
            or len(rows) > MAX_REMOTE_PREDICTION_ROWS
        ):
            raise ValueError("remote prediction request exceeds its row limit")
        materialized = list(rows)
        if not all(isinstance(row, Mapping) for row in materialized):
            raise ValueError("remote prediction rows must be objects")
        try:
            encoded = json.dumps(
                {"model_ref": model_ref, "rows": materialized},
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("remote prediction payload is not canonical JSON") from exc
        if len(encoded) > MAX_REMOTE_PREDICTION_BYTES:
            raise ValueError("remote prediction request exceeds its byte limit")
        payload = self._transport("predict", {"model_ref": model_ref, "rows": materialized})
        predictions = payload.get("predictions", [])
        if not isinstance(predictions, list) or len(predictions) > MAX_REMOTE_PREDICTION_ROWS:
            raise ValueError("remote predictions must be an array")
        return predictions


def urllib_json_transport(
    base_url: str,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = 30.0,
    max_response_bytes: int = 8 * 1024 * 1024,
    *,
    allow_http: bool = False,
    allowed_hosts: Sequence[str] | None = None,
) -> Callable[[str, Mapping[str, object]], Mapping[str, object]]:
    """Create a minimal POST JSON transport for provider deployment wiring."""
    normalized = base_url.rstrip("/")
    parsed_base = urlparse(normalized)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.hostname:
        raise ValueError("remote base_url must use http or https")
    if parsed_base.scheme == "http" and not allow_http:
        raise ValueError("remote base_url must use https unless allow_http is enabled")
    normalized_hosts = (
        None if allowed_hosts is None else frozenset(str(host).casefold() for host in allowed_hosts)
    )
    if normalized_hosts is not None and parsed_base.hostname.casefold() not in normalized_hosts:
        raise ValueError("remote base_url host is not allowed")
    normalized_headers = {str(key): str(value) for key, value in dict(headers or {}).items()}
    if parsed_base.scheme == "http" and any(
        key.casefold() == "authorization" for key in normalized_headers
    ):
        raise ValueError("authorization headers are not allowed over plaintext HTTP")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or timeout_seconds <= 0
        or isinstance(max_response_bytes, bool)
        or not isinstance(max_response_bytes, int)
        or max_response_bytes < 1
    ):
        raise ValueError("remote transport limits must be positive")
    opener = build_opener(_NoRedirectHandler())

    def transport(operation: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        request_payload = payload.get("request")
        request_timeout = (
            request_payload.get("timeout_seconds") if isinstance(request_payload, Mapping) else None
        )
        effective_timeout = timeout_seconds
        if isinstance(request_timeout, (int, float)) and not isinstance(request_timeout, bool):
            request_timeout = float(request_timeout)
            if not math.isfinite(request_timeout) or request_timeout <= 0:
                raise ValueError("remote request timeout must be positive and finite")
            effective_timeout = min(timeout_seconds, request_timeout)
        request = Request(  # noqa: S310
            f"{normalized}/{operation}",
            data=json.dumps(dict(payload), separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", **normalized_headers},
            method="POST",
        )
        try:
            with opener.open(request, timeout=effective_timeout) as response:
                raw = response.read(max_response_bytes + 1)
        except HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code < 600:
                raise RemoteTransientError(f"remote service returned HTTP {exc.code}") from exc
            raise RemoteValidationError(f"remote service returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RemoteTransientError("remote transport failed") from exc
        if len(raw) > max_response_bytes:
            raise ValueError("remote JSON response exceeds the configured byte limit")
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("remote JSON response must be an object")
        return decoded

    return transport


class MLflowBackend(JsonRemoteBackend):
    def __init__(
        self, transport: Callable[[str, Mapping[str, object]], Mapping[str, object]]
    ) -> None:
        super().__init__(
            "remote.mlflow",
            "Remote · MLflow",
            BackendCapabilities(
                tasks=("classification", "regression"),
                algorithms=(
                    "logistic_regression",
                    "linear_regression",
                    "random_forest_classifier",
                    "random_forest_regressor",
                ),
                hyperparameters=("timeout_seconds", "max_trials"),
                artifact_formats=("application/vnd.ronin.ml-remote+json",),
                resource_profiles=("remote.provider",),
            ),
            transport,
        )


class SparkBackend(JsonRemoteBackend):
    def __init__(
        self, transport: Callable[[str, Mapping[str, object]], Mapping[str, object]]
    ) -> None:
        super().__init__(
            "remote.spark",
            "Remote · Spark ML",
            BackendCapabilities(
                tasks=("classification", "regression", "clustering"),
                algorithms=("spark.gbt", "spark.rf", "spark.kmeans"),
                hyperparameters=("timeout_seconds", "max_trials"),
                artifact_formats=("application/vnd.ronin.ml-remote+json",),
                resource_profiles=("remote.spark-connect",),
            ),
            transport,
        )


__all__ = [
    "MAX_REMOTE_ID_LENGTH",
    "MAX_REMOTE_PREDICTION_BYTES",
    "MAX_REMOTE_PREDICTION_ROWS",
    "JsonRemoteBackend",
    "MLflowBackend",
    "RemoteExecutionController",
    "SparkBackend",
    "urllib_json_transport",
]
