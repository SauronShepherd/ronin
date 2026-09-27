"""Provider-neutral remote execution lifecycle."""

from __future__ import annotations

import json
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
    def __init__(self, backend: RemoteMLBackend, policy: RemoteRetryPolicy | None = None) -> None:
        self.backend = backend
        self.policy = policy or RemoteRetryPolicy()

    def submit(self, request: RemoteTrainingRequest) -> RemoteTrainingResult:
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                return self.backend.submit(request)
            except RemoteTransientError:
                if attempt == self.policy.max_attempts:
                    raise
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
            metrics.append((key, float(value)))
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
    base_url: str, headers: Mapping[str, str] | None = None, timeout_seconds: float = 30.0
) -> Callable[[str, Mapping[str, object]], Mapping[str, object]]:
    """Create a minimal POST JSON transport for provider deployment wiring."""
    normalized = base_url.rstrip("/")
    if not normalized.startswith(("http://", "https://")):
        raise ValueError("remote base_url must use http or https")

    def transport(operation: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        request = Request(  # noqa: S310
            f"{normalized}/{operation}",
            data=json.dumps(dict(payload), separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", **dict(headers or {})},
            method="POST",
        )
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            decoded = json.loads(response.read().decode("utf-8"))
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
