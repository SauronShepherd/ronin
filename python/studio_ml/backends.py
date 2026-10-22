"""Vendor-neutral backend contract for Machine Learning Studio."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Protocol, runtime_checkable

from .runtime import TrainedTabularModel, TrainingSpec, train_tabular

MAX_REMOTE_TIMEOUT_SECONDS = 86_400
MAX_REMOTE_TRIALS = 10_000
MAX_BACKEND_TEXT = 256
MAX_REMOTE_ARTIFACT_REF = 512


@dataclass(frozen=True, slots=True)
class ExperimentRequest:
    dataset_ref: str
    spec: TrainingSpec


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    """Machine-readable feature negotiation for a backend adapter."""

    tasks: tuple[str, ...]
    algorithms: tuple[str, ...]
    hyperparameters: tuple[str, ...] = ()
    artifact_formats: tuple[str, ...] = ()
    resource_profiles: tuple[str, ...] = ()
    supports_prediction: bool = True
    supports_artifacts: bool = True
    supports_explainability: bool = False

    def __post_init__(self) -> None:
        for values, label in (
            (self.tasks, "tasks"),
            (self.algorithms, "algorithms"),
            (self.hyperparameters, "hyperparameters"),
            (self.artifact_formats, "artifact_formats"),
            (self.resource_profiles, "resource_profiles"),
        ):
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"backend capability {label} entries must be non-empty text")
            if any(
                len(value) > MAX_BACKEND_TEXT or any(char in value for char in "\r\n\x00")
                for value in values
            ):
                raise ValueError(
                    f"backend capability {label} entries are too long or contain controls"
                )
            if len(values) != len(set(values)):
                raise ValueError(f"backend capability {label} entries must be unique")

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "tasks": list(self.tasks),
            "algorithms": list(self.algorithms),
            "supports_prediction": self.supports_prediction,
            "supports_artifacts": self.supports_artifacts,
            "supports_explainability": self.supports_explainability,
        }
        if self.hyperparameters:
            payload["hyperparameters"] = list(self.hyperparameters)
        if self.artifact_formats:
            payload["artifact_formats"] = list(self.artifact_formats)
        if self.resource_profiles:
            payload["resource_profiles"] = list(self.resource_profiles)
        return payload


@dataclass(frozen=True, slots=True)
class TrainingContext:
    dataset_ref: str
    workspace_id: str | None = None
    run_id: str | None = None
    artifact_namespace: str = "ml-studio"


@dataclass(frozen=True, slots=True)
class PredictionContext:
    model_id: str
    model_version: int
    workspace_id: str | None = None
    max_rows: int = 100_000


@dataclass(frozen=True, slots=True)
class ModelInspection:
    signature: tuple[str, ...]
    framework: str
    artifact_schema: str
    limitations: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "signature": list(self.signature),
            "framework": self.framework,
            "artifact_schema": self.artifact_schema,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class RemoteTrainingRequest:
    dataset_ref: str
    lab_id: str
    lab_version: int
    algorithm: str
    timeout_seconds: int = 3600
    max_trials: int = 100
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.lab_version, int)
            or isinstance(self.lab_version, bool)
            or self.lab_version < 1
            or not isinstance(self.timeout_seconds, int)
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds < 1
            or self.timeout_seconds > MAX_REMOTE_TIMEOUT_SECONDS
            or not isinstance(self.max_trials, int)
            or isinstance(self.max_trials, bool)
            or self.max_trials < 1
            or self.max_trials > MAX_REMOTE_TRIALS
        ):
            raise ValueError("remote training limits exceed the bounded policy")
        if any(
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > MAX_BACKEND_TEXT
            or any(char in value for char in "\r\n\x00")
            for value in (self.dataset_ref, self.lab_id, self.algorithm)
        ):
            raise ValueError("remote training identity fields must be non-empty")
        if (
            not isinstance(self.idempotency_key, str)
            or not self.idempotency_key
            or self.idempotency_key != self.idempotency_key.strip()
            or len(self.idempotency_key) > MAX_BACKEND_TEXT
            or any(char in self.idempotency_key for char in "\r\n\x00")
        ):
            raise ValueError("remote training requires a bounded idempotency key")


@dataclass(frozen=True, slots=True)
class RemoteTrainingResult:
    run_id: str
    artifact_ref: str
    artifact_digest: str
    status: str
    metrics: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.run_id, str)
            or not self.run_id
            or self.run_id != self.run_id.strip()
            or len(self.run_id) > MAX_BACKEND_TEXT
            or any(char in self.run_id for char in "\r\n\x00")
        ):
            raise ValueError("remote result requires a bounded run_id")
        if not isinstance(self.status, str) or self.status not in {
            "queued",
            "running",
            "succeeded",
            "failed",
            "cancelled",
        }:
            raise ValueError("unsupported remote training status")
        if (
            not isinstance(self.metrics, tuple)
            or len(self.metrics) > 32
            or len({name for name, _ in self.metrics}) != len(self.metrics)
        ):
            raise ValueError("remote result metrics must be bounded and unique")
        for name, value in self.metrics:
            if (
                not isinstance(name, str)
                or not name
                or name != name.strip()
                or len(name) > MAX_BACKEND_TEXT
                or any(char in name for char in "\r\n\x00")
            ):
                raise ValueError("remote result metric names must be non-empty")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ValueError("remote result metrics must be finite numbers")
        if bool(self.artifact_ref) != bool(self.artifact_digest):
            raise ValueError("remote artifact reference and digest must be supplied together")
        if self.artifact_ref and (
            not isinstance(self.artifact_ref, str)
            or not self.artifact_ref.strip()
            or self.artifact_ref != self.artifact_ref.strip()
            or len(self.artifact_ref) > MAX_REMOTE_ARTIFACT_REF
            or any(char in self.artifact_ref for char in "\r\n\x00")
        ):
            raise ValueError("remote artifact reference must be trimmed single-line text")
        if self.status == "succeeded" and not self.artifact_ref:
            raise ValueError("successful remote results require a durable artifact reference")
        if self.status == "succeeded" and self.artifact_digest:
            if not self.artifact_digest.startswith("sha256:"):
                raise ValueError("remote artifact digest must use the sha256 namespace")
            digest = self.artifact_digest.removeprefix("sha256:")
            if (
                not digest
                or len(digest) > 64
                or any(char not in "0123456789abcdefghijklmnopqrstuvwxyz._-" for char in digest)
            ):
                raise ValueError("remote artifact digest must be a bounded lowercase token")


class RemoteAdapterError(RuntimeError):
    code = "permanent_training_error"

    @property
    def retryable(self) -> bool:
        return self.code == "transient_error"


class RemoteConfigurationError(RemoteAdapterError):
    code = "configuration_error"


class RemoteValidationError(RemoteAdapterError):
    code = "validation_error"


class RemoteCapacityError(RemoteAdapterError):
    code = "capacity_error"


class RemoteTransientError(RemoteAdapterError):
    code = "transient_error"


@dataclass(frozen=True, slots=True)
class RemoteRetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.initial_delay_seconds < 0:
            raise ValueError("remote retry policy values must be valid")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max retry delay must not be below initial delay")

    def delay_for(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("retry attempt must be positive")
        delay: float = self.initial_delay_seconds * (2.0 ** (attempt - 1))
        return min(self.max_delay_seconds, delay)


@runtime_checkable
class RemoteMLBackend(Protocol):
    backend_id: str
    display_name: str
    capabilities: BackendCapabilities

    def submit(self, request: RemoteTrainingRequest) -> RemoteTrainingResult: ...

    def poll(self, run_id: str) -> RemoteTrainingResult: ...

    def cancel(self, run_id: str) -> RemoteTrainingResult: ...

    def predict(self, model_ref: str, rows: Sequence[Mapping[str, object]]) -> Sequence[object]: ...


@runtime_checkable
class MLBackend(Protocol):
    backend_id: str
    display_name: str
    capabilities: BackendCapabilities

    def train(
        self, request: ExperimentRequest, rows: Sequence[Mapping[str, object]]
    ) -> TrainedTabularModel: ...


class LocalScikitLearnBackend:
    backend_id = "local.sklearn"
    display_name = "Local · scikit-learn"
    capabilities = BackendCapabilities(
        tasks=("classification", "regression", "clustering"),
        algorithms=(
            "logistic_regression",
            "linear_regression",
            "decision_tree_classifier",
            "decision_tree_regressor",
            "random_forest_classifier",
            "random_forest_regressor",
            "kmeans",
            "gradient_boosting_regressor",
            "gradient_boosting_classifier",
        ),
    )

    @property
    def available(self) -> bool:
        """Check the optional dependency without importing its ML runtime."""
        try:
            return find_spec("sklearn") is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False

    @property
    def unavailable_reason(self) -> str:
        return "Install the optional ML dependencies with `pip install ronin-studio[ml]`."

    def train(
        self, request: ExperimentRequest, rows: Sequence[Mapping[str, object]]
    ) -> TrainedTabularModel:
        return train_tabular(rows, request.spec)


class BackendRegistry:
    """Explicit adapter registry used by services and capability discovery."""

    def __init__(self, backends: Sequence[MLBackend] = ()) -> None:
        self._backends: dict[str, MLBackend] = {}
        for backend in backends:
            self.register(backend)

    def register(self, backend: MLBackend) -> None:
        if not backend.backend_id.strip():
            raise ValueError("backend_id must be non-empty")
        if backend.backend_id in self._backends:
            raise ValueError(f"backend already registered: {backend.backend_id}")
        self._backends[backend.backend_id] = backend

    def get(self, backend_id: str) -> MLBackend | None:
        return self._backends.get(backend_id)

    def list(self) -> tuple[MLBackend, ...]:
        return tuple(self._backends[key] for key in sorted(self._backends))


def default_backends() -> tuple[MLBackend, ...]:
    return (LocalScikitLearnBackend(),)


__all__ = [
    "MAX_REMOTE_TIMEOUT_SECONDS",
    "MAX_REMOTE_TRIALS",
    "BackendCapabilities",
    "BackendRegistry",
    "TrainingContext",
    "PredictionContext",
    "ModelInspection",
    "RemoteTrainingRequest",
    "RemoteTrainingResult",
    "RemoteAdapterError",
    "RemoteConfigurationError",
    "RemoteValidationError",
    "RemoteCapacityError",
    "RemoteTransientError",
    "RemoteRetryPolicy",
    "RemoteMLBackend",
    "ExperimentRequest",
    "MLBackend",
    "LocalScikitLearnBackend",
    "default_backends",
]
