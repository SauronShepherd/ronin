"""Vendor-neutral backend contract for Machine Learning Studio."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .runtime import TrainedTabularModel, TrainingSpec, train_tabular


@dataclass(frozen=True, slots=True)
class ExperimentRequest:
    dataset_ref: str
    spec: TrainingSpec


@dataclass(frozen=True, slots=True)
class BackendCapabilities:
    """Machine-readable feature negotiation for a backend adapter."""

    tasks: tuple[str, ...]
    algorithms: tuple[str, ...]
    supports_prediction: bool = True
    supports_artifacts: bool = True
    supports_explainability: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "tasks": list(self.tasks),
            "algorithms": list(self.algorithms),
            "supports_prediction": self.supports_prediction,
            "supports_artifacts": self.supports_artifacts,
            "supports_explainability": self.supports_explainability,
        }


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
        if self.lab_version < 1 or self.timeout_seconds < 1 or self.max_trials < 1:
            raise ValueError("remote training limits must be positive")
        if not self.dataset_ref.strip() or not self.lab_id.strip() or not self.algorithm.strip():
            raise ValueError("remote training identity fields must be non-empty")
        if not self.idempotency_key.strip():
            raise ValueError("remote training requires an idempotency key")


@dataclass(frozen=True, slots=True)
class RemoteTrainingResult:
    run_id: str
    artifact_ref: str
    artifact_digest: str
    status: str
    metrics: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError("unsupported remote training status")
        if not self.run_id.strip():
            raise ValueError("remote result requires run_id")


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
