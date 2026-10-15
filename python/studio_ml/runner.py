"""Reproducible local experiment execution boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from .backends import BackendRegistry, ExperimentRequest, MLBackend, default_backends
from .clustering import KMeansModel, fit_kmeans
from .domain import Lab
from .quality import profile_and_validate
from .runtime import Algorithm, TrainedTabularModel, TrainingSpec


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    lab_id: str
    backend_id: str
    row_count: int
    model: TrainedTabularModel
    artifact_digest: str

    def to_payload(self) -> dict[str, object]:
        return {
            "lab_id": self.lab_id,
            "backend_id": self.backend_id,
            "row_count": self.row_count,
            "metrics": dict(self.model.metrics),
            "artifact_digest": self.artifact_digest,
            "task": self.model.task,
            "algorithm": self.model.algorithm,
        }


@dataclass(frozen=True, slots=True)
class ClusteringResult:
    lab_id: str
    backend_id: str
    row_count: int
    features: tuple[str, ...]
    model: KMeansModel
    artifact_digest: str
    inertia: float

    def to_payload(self) -> dict[str, object]:
        return {
            "lab_id": self.lab_id,
            "backend_id": self.backend_id,
            "row_count": self.row_count,
            "task": "clustering",
            "algorithm": "kmeans",
            "features": list(self.features),
            "centroids": [list(item) for item in self.model.centroids],
            "iterations": self.model.iterations,
            "inertia": self.inertia,
            "artifact_digest": self.artifact_digest,
        }


class BackendNotFound(LookupError):
    """Raised when a Lab requests an unavailable execution backend."""


class LocalExperimentRunner:
    def __init__(self, backends: Sequence[MLBackend] | None = None) -> None:
        selected = tuple(backends or default_backends())
        self._backends = BackendRegistry(selected)

    def run(
        self,
        lab: Lab,
        rows: Sequence[Mapping[str, object]],
        parameters: tuple[tuple[str, float | int], ...] = (),
    ) -> ExperimentResult:
        backend = self._backends.get(lab.backend_id)
        if backend is None:
            raise BackendNotFound(lab.backend_id)
        if lab.task == "clustering":
            raise ValueError("local tabular runner does not support clustering yet")
        capabilities = getattr(backend, "capabilities", None)
        if capabilities is not None and lab.task not in capabilities.tasks:
            raise ValueError(f"backend {backend.backend_id!r} does not support task {lab.task!r}")
        quality = profile_and_validate(lab, [dict(row) for row in rows])
        if not quality.passed:
            raise ValueError("quality gate failed: " + "; ".join(quality.failures))
        algorithm = cast(
            Algorithm,
            "logistic_regression" if lab.task == "classification" else "linear_regression",
        )
        spec = TrainingSpec(
            task=lab.task,
            algorithm=algorithm,
            features=tuple(feature.column for feature in lab.features if feature.role != "ignored"),
            target=lab.target or "",
            test_fraction=lab.test_fraction,
            random_seed=lab.seed,
            parameters=parameters,
        )
        if capabilities is not None and spec.algorithm not in capabilities.algorithms:
            raise ValueError(
                f"backend {backend.backend_id!r} does not support algorithm {spec.algorithm!r}"
            )
        trained = backend.train(ExperimentRequest(str(lab.dataset), spec), rows)
        digest = hashlib.sha256(trained.artifact_bytes).hexdigest()
        return ExperimentResult(lab.id, backend.backend_id, len(rows), trained, f"sha256:{digest}")

    def run_clustering(
        self,
        lab: Lab,
        rows: Sequence[Mapping[str, object]],
        *,
        clusters: int = 2,
        max_iterations: int = 100,
    ) -> KMeansModel:
        if lab.task != "clustering":
            raise ValueError("run_clustering requires a clustering lab")
        backend = self._backends.get(lab.backend_id)
        if backend is None:
            raise BackendNotFound(lab.backend_id)
        capabilities = getattr(backend, "capabilities", None)
        if capabilities is not None and "clustering" not in capabilities.tasks:
            raise ValueError(f"backend {backend.backend_id!r} does not support clustering")
        quality = profile_and_validate(lab, [dict(row) for row in rows])
        if not quality.passed:
            raise ValueError("quality gate failed: " + "; ".join(quality.failures))
        return fit_kmeans(
            rows,
            tuple(feature.column for feature in lab.features if feature.role != "ignored"),
            clusters,
            max_iterations=max_iterations,
        )

    def run_clustering_result(
        self,
        lab: Lab,
        rows: Sequence[Mapping[str, object]],
        *,
        clusters: int = 2,
        max_iterations: int = 100,
    ) -> ClusteringResult:
        features = tuple(feature.column for feature in lab.features if feature.role != "ignored")
        model = self.run_clustering(lab, rows, clusters=clusters, max_iterations=max_iterations)
        artifact = json.dumps(model.to_artifact(), sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(artifact).hexdigest()
        from .clustering import inertia

        return ClusteringResult(
            lab.id,
            lab.backend_id,
            len(rows),
            features,
            model,
            f"sha256:{digest}",
            inertia(model, rows, features),
        )


__all__ = ["BackendNotFound", "ClusteringResult", "ExperimentResult", "LocalExperimentRunner"]
