"""Reproducible local experiment execution boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from .backends import BackendRegistry, ExperimentRequest, MLBackend, default_backends
from .clustering import KMeansModel, fit_kmeans
from .domain import Lab, NodeKind, PipelineIR
from .quality import QualityReport, profile_and_validate
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
        result = self.execute_pipeline(lab, rows, parameters=parameters)
        if not isinstance(result, ExperimentResult):
            raise ValueError("classification/regression pipeline returned a clustering result")
        return result

    def execute_pipeline(
        self,
        lab: Lab,
        rows: Sequence[Mapping[str, object]],
        pipeline: PipelineIR | None = None,
        *,
        parameters: tuple[tuple[str, float | int], ...] = (),
        clusters: int = 2,
        max_iterations: int = 100,
    ) -> ExperimentResult | ClusteringResult:
        """Execute the pinned ML stages in stable dependency order.

        The initial runtime supports the six-node local pipeline contract. Nodes are
        interpreted from PipelineIR, and malformed or unsupported graphs fail before
        training so a stored-but-ignored graph cannot silently change execution.
        """

        backend = self._backends.get(lab.backend_id)
        if backend is None:
            raise BackendNotFound(lab.backend_id)
        capabilities = getattr(backend, "capabilities", None)
        if capabilities is not None and lab.task not in capabilities.tasks:
            raise ValueError(f"backend {backend.backend_id!r} does not support task {lab.task!r}")

        if pipeline is None:
            from .services import compile_lab_pipeline

            pipeline = compile_lab_pipeline(lab)
        if dict(pipeline.parameters).get("lab_digest") != lab.digest:
            raise ValueError("compiled ML pipeline is not bound to the submitted Lab")

        required_kinds: tuple[NodeKind, ...] = (
            "profile",
            "quality_gate",
            "prepare",
            "train",
            "evaluate",
            "select",
        )
        by_kind = {node.kind: node for node in pipeline.nodes}
        if len(by_kind) != len(pipeline.nodes) or set(by_kind) != set(required_kinds):
            raise ValueError("local ML pipeline must contain exactly one supported node per stage")
        for previous, current in zip(required_kinds[:-1], required_kinds[1:], strict=True):
            if by_kind[previous].id not in by_kind[current].depends_on:
                raise ValueError(f"ML pipeline stage {current!r} must depend on {previous!r}")

        values: dict[str, object] = {}
        result: ExperimentResult | ClusteringResult | None = None
        selected_features = tuple(
            feature.column for feature in lab.features if feature.role != "ignored"
        )
        for node in pipeline.execution_order():
            dependencies = [values[dependency] for dependency in node.depends_on]
            if node.kind == "profile":
                values[node.id] = profile_and_validate(lab, [dict(row) for row in rows])
            elif node.kind == "quality_gate":
                profile = next(
                    (item for item in dependencies if isinstance(item, QualityReport)), None
                )
                if profile is None:
                    raise ValueError("quality gate requires the profile stage output")
                if not profile.passed:
                    raise ValueError("quality gate failed: " + "; ".join(profile.failures))
                values[node.id] = profile
            elif node.kind == "prepare":
                if lab.task == "clustering":
                    values[node.id] = selected_features
                else:
                    values[node.id] = TrainingSpec(
                        task=lab.task,
                        algorithm=cast(
                            Algorithm,
                            "logistic_regression"
                            if lab.task == "classification"
                            else "linear_regression",
                        ),
                        features=selected_features,
                        target=lab.target or "",
                        test_fraction=lab.test_fraction,
                        random_seed=lab.seed,
                        parameters=parameters,
                    )
            elif node.kind == "train":
                prepared = next(
                    (item for item in dependencies if isinstance(item, (TrainingSpec, tuple))),
                    None,
                )
                if prepared is None:
                    raise ValueError("train stage requires prepared inputs")
                if lab.task == "clustering":
                    values[node.id] = fit_kmeans(
                        rows,
                        cast(tuple[str, ...], prepared),
                        clusters,
                        max_iterations=max_iterations,
                    )
                else:
                    spec = cast(TrainingSpec, prepared)
                    if capabilities is not None and spec.algorithm not in capabilities.algorithms:
                        raise ValueError(
                            f"backend {backend.backend_id!r} does not support algorithm "
                            f"{spec.algorithm!r}"
                        )
                    values[node.id] = backend.train(ExperimentRequest(str(lab.dataset), spec), rows)
            elif node.kind == "evaluate":
                if lab.task == "clustering":
                    model = next(
                        (item for item in dependencies if isinstance(item, KMeansModel)), None
                    )
                    if model is None:
                        raise ValueError("evaluate stage requires a trained clustering model")
                    from .clustering import inertia

                    values[node.id] = inertia(model, rows, selected_features)
                else:
                    trained = next(
                        (item for item in dependencies if isinstance(item, TrainedTabularModel)),
                        None,
                    )
                    if trained is None:
                        raise ValueError("evaluate stage requires a trained model")
                    values[node.id] = trained.metrics
            elif node.kind == "select":
                training_output = values[by_kind["train"].id]
                if lab.task == "clustering":
                    model = training_output if isinstance(training_output, KMeansModel) else None
                    score = next(
                        (item for item in dependencies if isinstance(item, (int, float))), None
                    )
                    if model is None or score is None:
                        raise ValueError("select stage requires evaluated clustering output")
                    artifact = json.dumps(
                        model.to_artifact(), sort_keys=True, separators=(",", ":")
                    ).encode()
                    digest = hashlib.sha256(artifact).hexdigest()
                    result = ClusteringResult(
                        lab.id,
                        backend.backend_id,
                        len(rows),
                        selected_features,
                        model,
                        f"sha256:{digest}",
                        float(score),
                    )
                else:
                    trained = (
                        training_output
                        if isinstance(training_output, TrainedTabularModel)
                        else None
                    )
                    if trained is None:
                        raise ValueError("select stage requires an evaluated model")
                    digest = hashlib.sha256(trained.artifact_bytes).hexdigest()
                    result = ExperimentResult(
                        lab.id, backend.backend_id, len(rows), trained, f"sha256:{digest}"
                    )
                values[node.id] = result
            else:  # pragma: no cover - PipelineNode validates kinds
                raise ValueError(f"unsupported local ML pipeline node: {node.kind}")

        if result is None:
            raise ValueError("local ML pipeline did not select a result")
        return result

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
        result = self.execute_pipeline(
            lab,
            rows,
            clusters=clusters,
            max_iterations=max_iterations,
        )
        if not isinstance(result, ClusteringResult):
            raise ValueError("clustering pipeline returned a supervised result")
        return result


__all__ = ["BackendNotFound", "ClusteringResult", "ExperimentResult", "LocalExperimentRunner"]
