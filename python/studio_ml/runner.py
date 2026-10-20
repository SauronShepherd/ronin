"""Reproducible local experiment execution boundary."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from .backends import BackendRegistry, ExperimentRequest, MLBackend, default_backends
from .clustering import KMeansModel, fit_kmeans
from .domain import Lab, NodeKind, PipelineIR, PipelineNode
from .quality import ColumnProfile, QualityReport, profile_and_validate
from .runtime import Algorithm, TrainedTabularModel, TrainingSpec

_CHECKPOINT_RUNTIME_DISTRIBUTIONS = ("joblib", "numpy", "scikit-learn", "scipy")


def _file_digest(path: str | Path | None) -> str | None:
    if path is None:
        return None
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _checkpoint_runtime_fingerprint(
    backend: MLBackend,
    *,
    parameters: tuple[tuple[str, float | int], ...],
    clusters: int,
    max_iterations: int,
) -> str | None:
    """Bind reusable node outputs to the exact local runtime that produced them."""
    backend_type = type(backend)
    try:
        backend_source = inspect.getsourcefile(backend_type)
        declared_identity = getattr(backend, "checkpoint_fingerprint", None)
    except Exception:
        return None
    backend_source_digest = _file_digest(backend_source)
    if callable(declared_identity):
        try:
            declared_identity = declared_identity()
        except Exception:
            return None
    if declared_identity is not None and (
        not isinstance(declared_identity, str)
        or not declared_identity.strip()
        or len(declared_identity) > 256
    ):
        return None
    if backend_source_digest is None and declared_identity is None:
        return None

    source_digests = {
        "runner": _file_digest(__file__),
        "domain": _file_digest(Path(__file__).with_name("domain.py")),
        "pipeline_compiler": _file_digest(Path(__file__).with_name("services.py")),
        "orchestration": _file_digest(Path(__file__).with_name("orchestration.py")),
        "runtime": _file_digest(inspect.getsourcefile(TrainingSpec)),
        "clustering": _file_digest(inspect.getsourcefile(KMeansModel)),
        "quality": _file_digest(inspect.getsourcefile(profile_and_validate)),
        "backend_registry": _file_digest(inspect.getsourcefile(BackendRegistry)),
    }
    if any(value is None for value in source_digests.values()):
        return None

    distributions: dict[str, str | None] = {}
    for distribution in _CHECKPOINT_RUNTIME_DISTRIBUTIONS:
        try:
            distributions[distribution] = version(distribution)
        except PackageNotFoundError:
            distributions[distribution] = None

    identity = {
        "schema": "ronin.ml-checkpoint-runtime/v1",
        "python": [sys.implementation.name, *sys.version_info[:3]],
        "sources": source_digests,
        "dependencies": distributions,
        "backend": {
            "id": backend.backend_id,
            "type": f"{backend_type.__module__}.{backend_type.__qualname__}",
            "source_digest": backend_source_digest,
            "declared_fingerprint": declared_identity,
        },
        "options": {
            "parameters": [[name, value] for name, value in sorted(parameters)],
            "clusters": clusters,
            "max_iterations": max_iterations,
        },
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    lab_id: str
    backend_id: str
    row_count: int
    model: TrainedTabularModel
    artifact_digest: str
    runtime_fingerprint: str = ""

    def to_payload(self) -> dict[str, object]:
        payload = {
            "lab_id": self.lab_id,
            "backend_id": self.backend_id,
            "row_count": self.row_count,
            "metrics": dict(self.model.metrics),
            "artifact_digest": self.artifact_digest,
            "task": self.model.task,
            "algorithm": self.model.algorithm,
            "features": list(self.model.features),
            "target": self.model.target,
        }
        if self.runtime_fingerprint:
            payload["runtime_fingerprint"] = self.runtime_fingerprint
        return payload


@dataclass(frozen=True, slots=True)
class ClusteringResult:
    lab_id: str
    backend_id: str
    row_count: int
    features: tuple[str, ...]
    model: KMeansModel
    artifact_digest: str
    inertia: float
    runtime_fingerprint: str = ""

    def to_payload(self) -> dict[str, object]:
        payload = {
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
        if self.runtime_fingerprint:
            payload["runtime_fingerprint"] = self.runtime_fingerprint
        return payload


def _trained_payload(model: TrainedTabularModel) -> dict[str, object]:
    return {
        "task": model.task,
        "algorithm": model.algorithm,
        "features": list(model.features),
        "target": model.target,
        "artifact": base64.b64encode(model.artifact_bytes).decode("ascii"),
        "metrics": [[name, value] for name, value in model.metrics],
    }


def _trained_from_payload(value: object) -> TrainedTabularModel:
    if not isinstance(value, Mapping):
        raise ValueError("ML checkpoint model must be an object")
    try:
        artifact = base64.b64decode(str(value["artifact"]), validate=True)
        metrics_value = value["metrics"]
        if not isinstance(metrics_value, list):
            raise ValueError
        metrics = tuple((str(item[0]), float(item[1])) for item in metrics_value)
        features_value = value["features"]
        if not isinstance(features_value, list) or not all(
            isinstance(item, str) for item in features_value
        ):
            raise ValueError
        return TrainedTabularModel(
            cast(Any, value["task"]),
            cast(Any, value["algorithm"]),
            tuple(features_value),
            str(value["target"]),
            artifact,
            metrics,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("ML checkpoint model has invalid data") from exc


def _checkpoint_payload(kind: NodeKind, value: object) -> dict[str, object]:
    """Encode one supported stage output using data-only canonical JSON fields."""
    if kind in {"profile", "quality_gate"} and isinstance(value, QualityReport):
        return {"kind": kind, "value": value.to_payload()}
    if kind == "prepare":
        if isinstance(value, TrainingSpec):
            return {
                "kind": kind,
                "value": {
                    "task": value.task,
                    "algorithm": value.algorithm,
                    "features": list(value.features),
                    "target": value.target,
                    "test_fraction": value.test_fraction,
                    "random_seed": value.random_seed,
                    "parameters": [[name, number] for name, number in value.parameters],
                },
            }
        if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
            return {"kind": kind, "value": list(value)}
    if kind == "train":
        if isinstance(value, TrainedTabularModel):
            return {"kind": kind, "value": {"type": "tabular", **_trained_payload(value)}}
        if isinstance(value, KMeansModel):
            return {"kind": kind, "value": {"type": "kmeans", **value.to_artifact()}}
    if kind == "evaluate":
        if isinstance(value, tuple):
            return {"kind": kind, "value": [[name, score] for name, score in value]}
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return {"kind": kind, "value": float(value)}
    if kind == "select" and isinstance(value, ExperimentResult):
        return {
            "kind": kind,
            "value": {
                "type": "tabular",
                "lab_id": value.lab_id,
                "backend_id": value.backend_id,
                "row_count": value.row_count,
                "model": _trained_payload(value.model),
                "artifact_digest": value.artifact_digest,
                "runtime_fingerprint": value.runtime_fingerprint,
            },
        }
    if kind == "select" and isinstance(value, ClusteringResult):
        return {
            "kind": kind,
            "value": {
                "type": "clustering",
                "lab_id": value.lab_id,
                "backend_id": value.backend_id,
                "row_count": value.row_count,
                "features": list(value.features),
                "model": value.model.to_artifact(),
                "artifact_digest": value.artifact_digest,
                "runtime_fingerprint": value.runtime_fingerprint,
                "inertia": value.inertia,
            },
        }
    raise ValueError(f"cannot checkpoint output for ML pipeline stage {kind!r}")


def _dependency_fingerprint(
    node: PipelineNode,
    nodes_by_id: Mapping[str, PipelineNode],
    values: Mapping[str, object],
) -> str:
    dependencies: list[list[str]] = []
    for dependency_id in sorted(node.depends_on):
        dependency = nodes_by_id[dependency_id]
        payload = _checkpoint_payload(dependency.kind, values[dependency_id])
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        dependencies.append([dependency_id, hashlib.sha256(encoded.encode("utf-8")).hexdigest()])
    encoded_dependencies = json.dumps(
        dependencies, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded_dependencies.encode("utf-8")).hexdigest()


def _restore_checkpoint(kind: NodeKind, value: object) -> object:
    if not isinstance(value, Mapping) or value.get("kind") != kind:
        raise ValueError("stored ML node checkpoint does not match its pipeline stage")
    payload = value.get("value")
    if kind in {"profile", "quality_gate"}:
        if not isinstance(payload, Mapping):
            raise ValueError("stored ML profile checkpoint is invalid")
        profiles = payload.get("profiles")
        if not isinstance(profiles, list):
            raise ValueError("stored ML profile checkpoint is invalid")
        restored = tuple(
            ColumnProfile(
                str(item["name"]),
                str(item["dtype"]),
                int(item["row_count"]),
                int(item["null_count"]),
                int(item["distinct_count"]),
                bool(item["constant"]),
            )
            for item in profiles
            if isinstance(item, Mapping)
        )
        return QualityReport(
            int(payload["row_count"]),
            restored,
            tuple(str(item) for item in payload["warnings"]),
            tuple(str(item) for item in payload["failures"]),
        )
    if kind == "prepare":
        if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
            return tuple(payload)
        if not isinstance(payload, Mapping):
            raise ValueError("stored ML prepare checkpoint is invalid")
        return TrainingSpec(
            task=cast(Any, payload["task"]),
            algorithm=cast(Any, payload["algorithm"]),
            features=tuple(str(item) for item in payload["features"]),
            target=str(payload["target"]),
            test_fraction=float(payload["test_fraction"]),
            random_seed=int(payload["random_seed"]),
            parameters=tuple((str(item[0]), cast(Any, item[1])) for item in payload["parameters"]),
        )
    if kind == "train":
        if not isinstance(payload, Mapping):
            raise ValueError("stored ML train checkpoint is invalid")
        if payload.get("type") == "tabular":
            return _trained_from_payload(payload)
        if payload.get("type") == "kmeans":
            artifact = payload
            if artifact.get("schema") != "ronin.ml-kmeans/v1":
                raise ValueError("stored K-Means checkpoint has unsupported schema")
            centers = artifact.get("centroids")
            if not isinstance(centers, list):
                raise ValueError("stored K-Means checkpoint has invalid centroids")
            return KMeansModel(
                tuple(tuple(float(item) for item in center) for center in centers),
                int(artifact["iterations"]),
            )
    if kind == "evaluate":
        if isinstance(payload, list):
            return tuple((str(item[0]), float(item[1])) for item in payload)
        if isinstance(payload, (int, float)) and not isinstance(payload, bool):
            return float(payload)
    if kind == "select" and isinstance(payload, Mapping):
        if payload.get("type") == "tabular":
            return ExperimentResult(
                str(payload["lab_id"]),
                str(payload["backend_id"]),
                int(payload["row_count"]),
                _trained_from_payload(payload["model"]),
                str(payload["artifact_digest"]),
                str(payload.get("runtime_fingerprint", "")),
            )
        if payload.get("type") == "clustering":
            model = _restore_checkpoint("train", {"kind": "train", "value": payload["model"]})
            if not isinstance(model, KMeansModel):
                raise ValueError("stored clustering result model is invalid")
            return ClusteringResult(
                str(payload["lab_id"]),
                str(payload["backend_id"]),
                int(payload["row_count"]),
                tuple(str(item) for item in payload["features"]),
                model,
                str(payload["artifact_digest"]),
                float(payload["inertia"]),
                str(payload.get("runtime_fingerprint", "")),
            )
    raise ValueError(f"stored ML checkpoint for stage {kind!r} has invalid data")


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
        checkpoint_load: Callable[[str], object | None] | None = None,
        checkpoint_save: Callable[[str, dict[str, object]], object] | None = None,
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
        nodes_by_id = {node.id: node for node in pipeline.nodes}
        for previous, current in zip(required_kinds[:-1], required_kinds[1:], strict=True):
            if by_kind[previous].id not in by_kind[current].depends_on:
                raise ValueError(f"ML pipeline stage {current!r} must depend on {previous!r}")

        values: dict[str, object] = {}
        result: ExperimentResult | ClusteringResult | None = None
        runtime_fingerprint = _checkpoint_runtime_fingerprint(
            backend,
            parameters=parameters,
            clusters=clusters,
            max_iterations=max_iterations,
        )
        selected_features = tuple(
            feature.column for feature in lab.features if feature.role != "ignored"
        )
        for node in pipeline.execution_order():
            dependencies = [values[dependency] for dependency in node.depends_on]
            dependency_fingerprint = _dependency_fingerprint(node, nodes_by_id, values)
            cached = checkpoint_load(node.id) if checkpoint_load is not None else None
            if (
                runtime_fingerprint is not None
                and isinstance(cached, Mapping)
                and cached.get("runtime_fingerprint") == runtime_fingerprint
                and cached.get("dependency_fingerprint") == dependency_fingerprint
                and isinstance(cached.get("checkpoint"), dict)
            ):
                try:
                    restored = _restore_checkpoint(
                        node.kind, cast(dict[str, object], cached["checkpoint"])
                    )
                    if (
                        node.kind == "select"
                        and isinstance(restored, (ExperimentResult, ClusteringResult))
                        and restored.runtime_fingerprint != runtime_fingerprint
                    ):
                        raise ValueError("stored ML result runtime identity is invalid")
                    values[node.id] = restored
                except (KeyError, TypeError, ValueError, OverflowError):
                    pass
                else:
                    if node.kind == "select":
                        selected = values[node.id]
                        if isinstance(selected, (ExperimentResult, ClusteringResult)):
                            result = selected
                    continue
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
                        runtime_fingerprint or "",
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
                        lab.id,
                        backend.backend_id,
                        len(rows),
                        trained,
                        f"sha256:{digest}",
                        runtime_fingerprint or "",
                    )
                values[node.id] = result
            else:  # pragma: no cover - PipelineNode validates kinds
                raise ValueError(f"unsupported local ML pipeline node: {node.kind}")
            if checkpoint_save is not None and runtime_fingerprint is not None:
                checkpoint_save(
                    node.id,
                    {
                        "runtime_fingerprint": runtime_fingerprint,
                        "dependency_fingerprint": dependency_fingerprint,
                        "checkpoint": _checkpoint_payload(node.kind, values[node.id]),
                    },
                )

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
