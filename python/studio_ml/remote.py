"""Provider-neutral remote execution lifecycle."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from urllib.request import Request, urlopen

from .backends import (
    BackendCapabilities,
    RemoteMLBackend,
    RemoteRetryPolicy,
    RemoteTrainingRequest,
    RemoteTrainingResult,
    RemoteTransientError,
)


class RemoteExecutionController:
    def __init__(
        self,
        backend: RemoteMLBackend,
        policy: RemoteRetryPolicy | None = None,
        *,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.backend = backend
        self.policy = policy or RemoteRetryPolicy()
        self._sleep = sleep or time.sleep

    def submit(self, request: RemoteTrainingRequest) -> RemoteTrainingResult:
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                return self.backend.submit(request)
            except RemoteTransientError:
                if attempt == self.policy.max_attempts:
                    raise
                self._sleep(self.policy.delay_for(attempt))
        raise AssertionError("unreachable")

    def poll(self, run_id: str) -> RemoteTrainingResult:
        return self.backend.poll(run_id)

    def cancel(self, run_id: str) -> RemoteTrainingResult:
        return self.backend.cancel(run_id)


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
            str(payload["run_id"]),
            str(payload.get("artifact_ref", "")),
            str(payload.get("artifact_digest", "")),
            str(payload["status"]),
            tuple(metrics),
        )

    def submit(self, request: RemoteTrainingRequest) -> RemoteTrainingResult:
        return self._result(self._transport("submit", {"request": asdict(request)}))

    def poll(self, run_id: str) -> RemoteTrainingResult:
        return self._result(self._transport("poll", {"run_id": run_id}))

    def cancel(self, run_id: str) -> RemoteTrainingResult:
        return self._result(self._transport("cancel", {"run_id": run_id}))

    def predict(self, model_ref: str, rows: Sequence[Mapping[str, object]]) -> Sequence[object]:
        payload = self._transport("predict", {"model_ref": model_ref, "rows": list(rows)})
        predictions = payload.get("predictions", [])
        if not isinstance(predictions, list):
            raise ValueError("remote predictions must be an array")
        return predictions


def urllib_json_transport(
    base_url: str,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = 30.0,
    max_response_bytes: int = 8 * 1024 * 1024,
) -> Callable[[str, Mapping[str, object]], Mapping[str, object]]:
    """Create a minimal POST JSON transport for provider deployment wiring."""
    normalized = base_url.rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("remote base_url must use http or https")
    if timeout_seconds <= 0 or max_response_bytes < 1:
        raise ValueError("remote transport limits must be positive")

    def transport(operation: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        request_payload = payload.get("request")
        request_timeout = (
            request_payload.get("timeout_seconds")
            if isinstance(request_payload, Mapping)
            else None
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
            headers={"Content-Type": "application/json", **dict(headers or {})},
            method="POST",
        )
        with urlopen(request, timeout=effective_timeout) as response:  # noqa: S310
            raw = response.read(max_response_bytes + 1)
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
            ),
            transport,
        )


__all__ = [
    "JsonRemoteBackend",
    "MLflowBackend",
    "RemoteExecutionController",
    "SparkBackend",
    "urllib_json_transport",
]
