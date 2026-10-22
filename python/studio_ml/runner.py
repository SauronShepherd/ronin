"""Reproducible local experiment execution boundary."""

from __future__ import annotations

import base64
import hashlib
import inspect
import json
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from .backends import BackendRegistry, ExperimentRequest, MLBackend, default_backends
from .clustering import KMeansModel, fit_kmeans
from .domain import (
    PIPELINE_SCHEMA_V2,
    PIPELINE_SCHEMA_V3,
    Lab,
    NodeKind,
    PipelineIR,
    PipelineNode,
)
from .quality import (
    ColumnProfile,
    QualityExpectationResult,
    QualityReport,
    QualitySuite,
    profile_and_validate,
    validate_quality_suite,
)
from .runtime import Algorithm, MLDependencyError, Preprocessor, TrainedTabularModel, TrainingSpec
from studio_kernel import CancellationSignal

_CHECKPOINT_RUNTIME_DISTRIBUTIONS = ("joblib", "numpy", "scikit-learn", "scipy")
_MAX_PLUGIN_MODEL_INPUT_BYTES = 512 * 1024


class MLExecutionCancelled(RuntimeError):
    """Raised at a stage boundary after the owning execution is cancelled."""


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
    pipeline_digest: str = "",
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
        "pipeline_stage_registry": _file_digest(
            Path(__file__).with_name("pipeline_stages.py")
        ),
        "plugin_stage_runtime": _file_digest(
            Path(__file__).with_name("plugin_stage_runtime.py")
        ),
        "plugin_contribution_contract": _file_digest(
            Path(__file__).parents[1] / "studio_core" / "plugins.py"
        ),
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
            "pipeline_digest": pipeline_digest,
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
    selection_metric: str | None = None
    selection_score: float | None = None

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
        if self.selection_metric is not None and self.selection_score is not None:
            payload["selection_metric"] = self.selection_metric
            payload["selection_score"] = self.selection_score
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
                    "preprocessor": value.preprocessor,
                    "categorical_features": list(value.categorical_features),
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
                "selection_metric": value.selection_metric,
                "selection_score": value.selection_score,
            },
        }
    if "/" in kind and isinstance(value, Mapping):
        # Plugin stage values are restricted to the canonical JSON response from
        # the isolated executor; no Python object or executable state is persisted.
        return {"kind": kind, "value": dict(value)}
    raise ValueError(f"cannot checkpoint output for ML pipeline stage {kind!r}")


def _dependency_fingerprint(
    node: PipelineNode,
    nodes_by_id: Mapping[str, PipelineNode],
    values: Mapping[str, object],
    dependency_ids: Sequence[str] | None = None,
) -> str:
    dependencies: list[list[str]] = []
    for dependency_id in sorted(dependency_ids if dependency_ids is not None else node.depends_on):
        dependency = nodes_by_id[dependency_id]
        output = values[dependency_id]
        if isinstance(output, TrainedTabularModel):
            payload: object = {
                "schema": "ronin.ml-stage-output-fingerprint/v1",
                "kind": dependency.kind,
                "type": "tabular-model",
                "task": output.task,
                "algorithm": output.algorithm,
                "features": list(output.features),
                "target": output.target,
                "artifact_digest": hashlib.sha256(output.artifact_bytes).hexdigest(),
                "metrics": [[name, score] for name, score in output.metrics],
            }
        elif isinstance(output, ExperimentResult):
            model = output.model
            payload = {
                "schema": "ronin.ml-stage-output-fingerprint/v1",
                "kind": dependency.kind,
                "type": "experiment-result",
                "lab_id": output.lab_id,
                "backend_id": output.backend_id,
                "row_count": output.row_count,
                "runtime_fingerprint": output.runtime_fingerprint,
                "model": {
                    "task": model.task,
                    "algorithm": model.algorithm,
                    "features": list(model.features),
                    "target": model.target,
                    "artifact_digest": hashlib.sha256(model.artifact_bytes).hexdigest(),
                    "metrics": [[name, score] for name, score in model.metrics],
                },
            }
        else:
            payload = _checkpoint_payload(dependency.kind, output)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        dependencies.append([dependency_id, hashlib.sha256(encoded.encode("utf-8")).hexdigest()])
    encoded_dependencies = json.dumps(
        dependencies, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded_dependencies.encode("utf-8")).hexdigest()


def _candidate_score_map(value: object) -> dict[str, float] | None:
    if isinstance(value, tuple):
        entries = value
    elif isinstance(value, Mapping) and isinstance(value.get("scores"), Mapping):
        entries = tuple(value["scores"].items())
    else:
        return None
    result: dict[str, float] = {}
    for name, score in entries:
        if (
            not isinstance(name, str)
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
        ):
            return None
        try:
            finite_score = float(score)
        except OverflowError:
            return None
        if not math.isfinite(finite_score):
            return None
        result[name] = finite_score
    return result


def _restore_checkpoint(kind: NodeKind, value: object) -> object:
    if not isinstance(value, Mapping) or value.get("kind") != kind:
        raise ValueError("stored ML node checkpoint does not match its pipeline stage")
    payload = value.get("value")
    if "/" in kind:
        if not isinstance(payload, Mapping):
            raise ValueError("stored plugin stage checkpoint is invalid")
        return dict(payload)
    if kind in {"profile", "quality_gate"}:
        if not isinstance(payload, Mapping):
            raise ValueError("stored ML profile checkpoint is invalid")
        profiles = payload.get("profiles")
        if (
            not isinstance(profiles, list)
            or any(
                not isinstance(item, Mapping)
                or set(item)
                != {"name", "dtype", "row_count", "null_count", "distinct_count", "constant"}
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("dtype"), str)
                or not isinstance(item.get("row_count"), int)
                or isinstance(item.get("row_count"), bool)
                or item["row_count"] < 0
                or not isinstance(item.get("null_count"), int)
                or isinstance(item.get("null_count"), bool)
                or item["null_count"] < 0
                or item["null_count"] > item["row_count"]
                or not isinstance(item.get("distinct_count"), int)
                or isinstance(item.get("distinct_count"), bool)
                or item["distinct_count"] < 0
                or not isinstance(item.get("constant"), bool)
                for item in profiles
            )
        ):
            raise ValueError("stored ML profile checkpoint is invalid")
        restored = tuple(
            ColumnProfile(
                cast(str, item["name"]),
                cast(str, item["dtype"]),
                cast(int, item["row_count"]),
                cast(int, item["null_count"]),
                cast(int, item["distinct_count"]),
                cast(bool, item["constant"]),
            )
            for item in profiles
        )
        suite_payload = payload.get("suite")
        if suite_payload is not None and (
            not isinstance(suite_payload, Mapping)
            or set(suite_payload) != {"id", "version"}
            or not isinstance(suite_payload.get("id"), str)
            or not isinstance(suite_payload.get("version"), int)
            or isinstance(suite_payload.get("version"), bool)
            or cast(int, suite_payload["version"]) < 1
        ):
            raise ValueError("stored ML quality suite identity is invalid")
        warnings = payload.get("warnings")
        failures = payload.get("failures")
        row_count = payload.get("row_count")
        if (
            not isinstance(row_count, int)
            or isinstance(row_count, bool)
            or row_count < 0
            or not isinstance(warnings, list)
            or not all(isinstance(item, str) for item in warnings)
            or not isinstance(failures, list)
            or not all(isinstance(item, str) for item in failures)
        ):
            raise ValueError("stored ML quality report fields are invalid")
        raw_expectations = payload.get("expectations", [])
        if not isinstance(raw_expectations, list) or any(
            not isinstance(item, Mapping)
            or set(item)
            != {"id", "column", "rule", "severity", "passed", "message"}
            or not all(
                isinstance(item.get(key), str)
                for key in ("id", "column", "rule", "severity", "message")
            )
            or not isinstance(item.get("passed"), bool)
            for item in raw_expectations
        ):
            raise ValueError("stored ML quality expectations are invalid")
        return QualityReport(
            row_count,
            restored,
            tuple(cast(list[str], warnings)),
            tuple(cast(list[str], failures)),
            cast(str | None, suite_payload.get("id") if suite_payload is not None else None),
            cast(int | None, suite_payload.get("version") if suite_payload is not None else None),
            tuple(
                QualityExpectationResult(
                    cast(str, item["id"]),
                    cast(str, item["column"]),
                    cast(str, item["rule"]),
                    cast(str, item["severity"]),
                    cast(bool, item["passed"]),
                    cast(str, item["message"]),
                )
                for item in raw_expectations
            ),
        )
    if kind == "prepare":
        if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
            return tuple(payload)
        if not isinstance(payload, Mapping):
            raise ValueError("stored ML prepare checkpoint is invalid")
        categorical_features = payload.get("categorical_features", [])
        if not isinstance(categorical_features, list) or not all(
            isinstance(item, str) for item in categorical_features
        ):
            raise ValueError("stored ML prepare checkpoint has invalid categorical features")
        return TrainingSpec(
            task=cast(Any, payload["task"]),
            algorithm=cast(Any, payload["algorithm"]),
            features=tuple(str(item) for item in payload["features"]),
            target=str(payload["target"]),
            test_fraction=float(payload["test_fraction"]),
            random_seed=int(payload["random_seed"]),
            parameters=tuple((str(item[0]), cast(Any, item[1])) for item in payload["parameters"]),
            preprocessor=cast(Preprocessor, payload.get("preprocessor", "identity")),
            categorical_features=tuple(categorical_features),
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
                cast(str | None, payload.get("selection_metric")),
                cast(float | None, payload.get("selection_score")),
            )
    raise ValueError(f"stored ML checkpoint for stage {kind!r} has invalid data")


class BackendNotFound(LookupError):
    """Raised when a Lab requests an unavailable execution backend."""


class LocalExperimentRunner:
    def __init__(self, backends: Sequence[MLBackend] | None = None) -> None:
        selected = tuple(backends or default_backends())
        self._backends = BackendRegistry(selected)
        self._plugin_stage_registry: object | None = None
        self._plugin_artifact_capabilities_available = False

    @staticmethod
    def _ensure_backend_available(backend: MLBackend) -> None:
        if getattr(backend, "available", True) is False:
            reason = getattr(backend, "unavailable_reason", None)
            raise MLDependencyError(
                reason
                if isinstance(reason, str) and reason
                else f"ML backend {backend.backend_id!r} is unavailable"
            )

    def configure_plugin_stage_registry(self, registry: object) -> None:
        """Attach the host-frozen plugin stage declarations used by durable Jobs."""
        digest = getattr(registry, "digest", None)
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("plugin pipeline stage registry must expose a SHA-256 digest")
        self._plugin_stage_registry = registry

    def configure_plugin_artifact_capabilities(self, *, available: bool) -> None:
        """Declare whether durable artifact reads and leased writes are wired."""
        self._plugin_artifact_capabilities_available = bool(available)

    @property
    def stage_registry_digest(self) -> str:
        from .pipeline_stages import pipeline_stage_registry_digest

        if self._plugin_stage_registry is not None and getattr(
            self._plugin_stage_registry, "frozen", False
        ) is not True:
            raise ValueError("PipelineIR v3 plugin stage registry must be frozen before use")
        return pipeline_stage_registry_digest(self._plugin_stage_registry)

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

    def validate_pipeline(self, lab: Lab, pipeline: PipelineIR) -> None:
        """Validate a client supplied pipeline before it is persisted as a Job."""
        backend = self._backends.get(lab.backend_id)
        if backend is None:
            raise BackendNotFound(lab.backend_id)
        self._ensure_backend_available(backend)
        capabilities = getattr(backend, "capabilities", None)
        if capabilities is not None and lab.task not in capabilities.tasks:
            raise ValueError(f"backend {backend.backend_id!r} does not support task {lab.task!r}")
        parameters = dict(pipeline.parameters)
        if (
            parameters.get("lab_digest") != lab.digest
            or parameters.get("backend_id") != lab.backend_id
            or parameters.get("task") != lab.task
            or parameters.get("seed") != str(lab.seed)
        ):
            raise ValueError("custom ML pipeline is not bound to the submitted Lab")
        if pipeline.schema == PIPELINE_SCHEMA_V3:
            if parameters.get("stage_registry_digest") != self.stage_registry_digest:
                raise ValueError("PipelineIR v3 stage registry identity does not match executor")
        if pipeline.schema == PIPELINE_SCHEMA_V2:
            self._validate_v2_graph(pipeline, lab)
        elif pipeline.schema == PIPELINE_SCHEMA_V3:
            self._validate_v3_graph(pipeline, lab)
        if pipeline.schema in {PIPELINE_SCHEMA_V2, PIPELINE_SCHEMA_V3}:
            if lab.task != "clustering":
                from .runtime import ALGORITHM_CAPABILITIES

                default_algorithm = (
                    "logistic_regression" if lab.task == "classification" else "linear_regression"
                )
                for node in pipeline.nodes:
                    if node.kind != "train":
                        continue
                    algorithm = node.config.get("algorithm", parameters.get("algorithm"))
                    if algorithm is None:
                        algorithm = default_algorithm
                    if not isinstance(algorithm, str):
                        raise ValueError("train node algorithm must be a string")
                    if capabilities is not None and algorithm not in capabilities.algorithms:
                        raise ValueError(
                            f"backend {backend.backend_id!r} does not support algorithm "
                            f"{algorithm!r}"
                        )
                    if lab.task not in ALGORITHM_CAPABILITIES.get(algorithm, frozenset()):
                        raise ValueError("train node algorithm is not supported for this Lab task")
            return
        required_kinds: tuple[NodeKind, ...] = (
            "profile",
            "quality_gate",
            "prepare",
            "train",
            "evaluate",
            "select",
        )
        by_kind: dict[NodeKind, list[PipelineNode]] = {}
        for node in pipeline.nodes:
            by_kind.setdefault(node.kind, []).append(node)
        singular = {kind: items[0] for kind, items in by_kind.items() if len(items) == 1}
        if len(singular) != len(pipeline.nodes) or set(singular) != set(required_kinds):
            raise ValueError("custom ML pipeline contains unsupported or duplicate stages")
        for previous, current in zip(required_kinds[:-1], required_kinds[1:], strict=True):
            if singular[previous].id not in singular[current].depends_on:
                raise ValueError(f"ML pipeline stage {current!r} must depend on {previous!r}")

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
        cancellation: CancellationSignal | None = None,
        plugin_artifact_load: Callable[[Mapping[str, object]], bytes] | None = None,
        plugin_artifact_persist: Callable[
            [str, dict[str, object], Mapping[str, tuple[str, bytes]]],
            Mapping[str, Mapping[str, object]],
        ]
        | None = None,
    ) -> ExperimentResult | ClusteringResult:
        """Execute the pinned ML stages in stable dependency order.

        V1 retains the six-stage contract. V2 supports a validated multi-candidate
        classification/regression DAG with deterministic metric-based selection.
        """

        backend = self._backends.get(lab.backend_id)
        if backend is None:
            raise BackendNotFound(lab.backend_id)
        self._ensure_backend_available(backend)
        capabilities = getattr(backend, "capabilities", None)
        if capabilities is not None and lab.task not in capabilities.tasks:
            raise ValueError(f"backend {backend.backend_id!r} does not support task {lab.task!r}")

        if pipeline is None:
            from .services import compile_lab_pipeline

            pipeline = compile_lab_pipeline(lab)
        if dict(pipeline.parameters).get("lab_digest") != lab.digest:
            raise ValueError("compiled ML pipeline is not bound to the submitted Lab")
        if pipeline.schema == PIPELINE_SCHEMA_V3:
            if (
                dict(pipeline.parameters).get("stage_registry_digest")
                != self.stage_registry_digest
            ):
                raise ValueError("PipelineIR v3 stage registry identity does not match executor")

        required_kinds: tuple[NodeKind, ...] = (
            "profile",
            "quality_gate",
            "prepare",
            "train",
            "evaluate",
            "select",
        )
        nodes_by_id = {node.id: node for node in pipeline.nodes}
        by_kind: dict[NodeKind, list[PipelineNode]] = {}
        for node in pipeline.nodes:
            by_kind.setdefault(node.kind, []).append(node)
        if pipeline.schema == PIPELINE_SCHEMA_V2:
            self._validate_v2_graph(pipeline, lab)
        elif pipeline.schema == PIPELINE_SCHEMA_V3:
            self._validate_v3_graph(pipeline, lab)
        if pipeline.schema in {PIPELINE_SCHEMA_V2, PIPELINE_SCHEMA_V3}:
            if lab.task == "clustering" and any(
                cast(int, node.config["clusters"]) >= len(rows) for node in by_kind["train"]
            ):
                raise ValueError("K-Means candidate clusters must be less than row count")
            if capabilities is not None and lab.task != "clustering":
                from .runtime import ALGORITHM_CAPABILITIES

                default_algorithm = (
                    "logistic_regression" if lab.task == "classification" else "linear_regression"
                )
                for node in by_kind["train"]:
                    algorithm = node.config.get("algorithm", default_algorithm)
                    if not isinstance(algorithm, str):
                        raise ValueError("train node algorithm must be a string")
                    if algorithm not in capabilities.algorithms:
                        raise ValueError(
                            f"backend {backend.backend_id!r} does not support algorithm "
                            f"{algorithm!r}"
                        )
                    if lab.task not in ALGORITHM_CAPABILITIES.get(algorithm, frozenset()):
                        raise ValueError("train node algorithm is not supported for this Lab task")
        elif pipeline.schema != PIPELINE_SCHEMA_V3:
            singular = {kind: items[0] for kind, items in by_kind.items() if len(items) == 1}
            if len(singular) != len(pipeline.nodes) or set(singular) != set(required_kinds):
                raise ValueError(
                    "local ML pipeline must contain exactly one supported node per stage"
                )
            for previous, current in zip(required_kinds[:-1], required_kinds[1:], strict=True):
                if singular[previous].id not in singular[current].depends_on:
                    raise ValueError(f"ML pipeline stage {current!r} must depend on {previous!r}")
            by_kind = {kind: [node] for kind, node in singular.items()}

        values: dict[str, object] = {}
        result: ExperimentResult | ClusteringResult | None = None
        runtime_fingerprint = _checkpoint_runtime_fingerprint(
            backend,
            parameters=parameters,
            clusters=clusters,
            max_iterations=max_iterations,
            pipeline_digest=PipelineIR(
                tuple(sorted(pipeline.nodes, key=lambda node: node.id)),
                pipeline.parameters,
                pipeline.schema,
            ).digest,
        )
        selected_features = tuple(
            feature.column for feature in lab.features if feature.role != "ignored"
        )
        for node in pipeline.execution_order():
            if cancellation is not None and cancellation.is_cancelled:
                raise MLExecutionCancelled("ML pipeline execution was cancelled")
            plugin_checkpoint_saved = False
            checkpoint_codec: str | None = None
            executor_kind = node.kind
            if pipeline.schema == PIPELINE_SCHEMA_V3:
                from .pipeline_stages import BUILTIN_STAGE_REGISTRY
                stage = BUILTIN_STAGE_REGISTRY.get(node.kind)
                if stage is None:
                    contribution = next(
                        (
                            item
                            for item in getattr(self._plugin_stage_registry, "items", ())
                            if item.stage_id == node.kind
                        ),
                        None,
                    )
                    if contribution is None or contribution.version != node.stage_version:
                        raise ValueError(f"PipelineIR v3 plugin stage is unavailable: {node.kind}")
                    checkpoint_codec = (
                        f"ronin.ml.plugin-checkpoint/v1:{contribution.stage_id}:"
                        f"{contribution.version}:{contribution.distribution_digest}:"
                        f"{contribution.executor_image}"
                    )
                    executor_kind = node.kind
                else:
                    executor_parts = stage.executor.split(":")
                    if (
                        len(executor_parts) != 3
                        or executor_parts[0] != "studio_ml.runner"
                        or executor_parts[2] != f"v{stage.version}"
                        or executor_parts[1] != node.kind
                    ):
                        raise ValueError("PipelineIR v3 stage executor identity is unsupported")
                    checkpoint_codec = stage.checkpoint_codec
                    executor_kind = executor_parts[1]
            dependency_ids = pipeline.dependency_ids(node)
            dependencies = [values[dependency] for dependency in dependency_ids]
            dependency_fingerprint = _dependency_fingerprint(
                node, nodes_by_id, values, dependency_ids
            )
            cached = checkpoint_load(node.id) if checkpoint_load is not None else None
            if (
                runtime_fingerprint is not None
                and isinstance(cached, Mapping)
                and cached.get("runtime_fingerprint") == runtime_fingerprint
                and cached.get("dependency_fingerprint") == dependency_fingerprint
                and (checkpoint_codec is None or cached.get("checkpoint_codec") == checkpoint_codec)
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
            if executor_kind == node.kind and "/" in node.kind:
                from .plugin_stage_runtime import execute_plugin_stage

                if contribution.effect == "artifact_write" and plugin_artifact_persist is None:
                    raise ValueError("plugin artifact-writing stage requires the durable artifact API")
                port_inputs: dict[str, object] = {}
                node_inputs = dict(node.inputs)
                for port, references in node_inputs.items():
                    port_values: list[object] = []
                    for reference in references:
                        dependency_id, _ = reference.rsplit(".", 1)
                        dependency_node = nodes_by_id[dependency_id]
                        dependency_value = values[dependency_id]
                        model = (
                            dependency_value.model
                            if isinstance(dependency_value, (ExperimentResult, ClusteringResult))
                            else dependency_value
                        )
                        if isinstance(model, TrainedTabularModel):
                            model_bytes = model.artifact_bytes
                        elif isinstance(model, KMeansModel):
                            model_bytes = encode_canonical_json(model.to_artifact())
                        else:
                            model_bytes = None
                        if model_bytes is not None and len(model_bytes) > _MAX_PLUGIN_MODEL_INPUT_BYTES:
                            raise ValueError(
                                "plugin stage model input exceeds the bounded JSON payload limit"
                            )
                        encoded_value = _checkpoint_payload(
                            dependency_node.kind, dependency_value
                        )
                        dependency_value = encoded_value["value"]
                        if isinstance(dependency_value, Mapping):
                            dependency_value = {
                                key: value
                                for key, value in dependency_value.items()
                                if key != "__ronin_artifacts__"
                            }
                        port_values.append(dependency_value)
                    port_inputs[port] = port_values[0] if len(port_values) == 1 else port_values
                response = execute_plugin_stage(
                    contribution,
                    config=node.config,
                    inputs=port_inputs,
                    artifacts=self._plugin_input_artifacts(
                        node,
                        values,
                        plugin_artifact_load,
                        require_permission="artifact:read" in contribution.permissions,
                    ),
                    cancellation=cancellation,
                )
                if contribution.output_type == "ml.metrics":
                    score_values = response.value.get("scores")
                    try:
                        invalid_scores = not isinstance(score_values, Mapping) or not score_values
                        if not invalid_scores:
                            for name, score in score_values.items():
                                if (
                                    not isinstance(name, str)
                                    or not name
                                    or name != name.strip()
                                    or not isinstance(score, (int, float))
                                    or isinstance(score, bool)
                                    or not math.isfinite(float(score))
                                ):
                                    invalid_scores = True
                                    break
                    except OverflowError:
                        invalid_scores = True
                    if invalid_scores:
                        raise ValueError(
                            "plugin ml.metrics output requires a non-empty finite scores object"
                        )
                if "__ronin_artifacts__" in response.value:
                    raise ValueError("plugin output uses a reserved host field")
                values[node.id] = dict(response.value)
                if response.artifacts:
                    if (
                        checkpoint_save is None
                        or runtime_fingerprint is None
                        or plugin_artifact_persist is None
                    ):
                        raise ValueError("plugin artifact output requires durable checkpoint storage")
                    plugin_checkpoint = {
                        "runtime_fingerprint": runtime_fingerprint,
                        "dependency_fingerprint": dependency_fingerprint,
                        "checkpoint_codec": checkpoint_codec,
                        "checkpoint": _checkpoint_payload(node.kind, values[node.id]),
                    }
                    artifact_refs = plugin_artifact_persist(
                        node.id,
                        plugin_checkpoint,
                        {
                            artifact.name: (artifact.media_type, artifact.data)
                            for artifact in response.artifacts
                        },
                    )
                    values[node.id] = {
                        **dict(response.value),
                        "__ronin_artifacts__": dict(artifact_refs),
                    }
                    plugin_checkpoint_saved = True
            elif executor_kind == "profile":
                values[node.id] = profile_and_validate(lab, [dict(row) for row in rows])
            elif executor_kind == "quality_gate":
                profile = next(
                    (item for item in dependencies if isinstance(item, QualityReport)), None
                )
                if profile is None:
                    raise ValueError("quality gate requires the profile stage output")
                suite_payload = node.config.get("suite")
                if suite_payload is not None:
                    suite = QualitySuite.from_payload(suite_payload)
                    profile = profile_and_validate(
                        lab, [dict(row) for row in rows], suite=suite
                    )
                if not profile.passed:
                    raise ValueError("quality gate failed: " + "; ".join(profile.failures))
                values[node.id] = profile
            elif executor_kind == "prepare":
                if lab.task == "clustering":
                    values[node.id] = selected_features
                else:
                    selected_algorithm = dict(pipeline.parameters).get(
                        "algorithm",
                        "logistic_regression"
                        if lab.task == "classification"
                        else "linear_regression",
                    )
                    preprocessor = node.config.get(
                        "preprocessor", dict(pipeline.parameters).get("preprocessor", "identity")
                    )
                    values[node.id] = TrainingSpec(
                        task=lab.task,
                        algorithm=cast(Algorithm, selected_algorithm),
                        features=selected_features,
                        target=lab.target or "",
                        test_fraction=lab.test_fraction,
                        random_seed=lab.seed,
                        parameters=parameters,
                        preprocessor=cast(Preprocessor, preprocessor),
                        categorical_features=tuple(
                            feature.column
                            for feature in lab.features
                            if feature.role == "categorical"
                        ),
                    )
            elif executor_kind == "train":
                prepared = next(
                    (item for item in dependencies if isinstance(item, (TrainingSpec, tuple))),
                    None,
                )
                if prepared is None:
                    raise ValueError("train stage requires prepared inputs")
                if lab.task == "clustering":
                    candidate_clusters = node.config.get("clusters", clusters)
                    if (
                        not isinstance(candidate_clusters, int)
                        or isinstance(candidate_clusters, bool)
                        or candidate_clusters < 2
                        or candidate_clusters > len(rows)
                    ):
                        raise ValueError(
                            "K-Means candidate clusters must be between 2 and row count"
                        )
                    values[node.id] = fit_kmeans(
                        rows,
                        cast(tuple[str, ...], prepared),
                        candidate_clusters,
                        max_iterations=max_iterations,
                    )
                else:
                    spec = cast(TrainingSpec, prepared)
                    algorithm = node.config.get("algorithm")
                    if algorithm is not None:
                        from .runtime import ALGORITHM_CAPABILITIES

                        if not isinstance(
                            algorithm, str
                        ) or lab.task not in ALGORITHM_CAPABILITIES.get(algorithm, frozenset()):
                            raise ValueError(
                                "train node algorithm is not supported for this Lab task"
                            )
                        spec = replace(spec, algorithm=cast(Any, algorithm))
                    if capabilities is not None and spec.algorithm not in capabilities.algorithms:
                        raise ValueError(
                            f"backend {backend.backend_id!r} does not support algorithm "
                            f"{spec.algorithm!r}"
                        )
                    values[node.id] = backend.train(ExperimentRequest(str(lab.dataset), spec), rows)
            elif executor_kind == "evaluate":
                if lab.task == "clustering":
                    model = next(
                        (item for item in dependencies if isinstance(item, KMeansModel)), None
                    )
                    if model is None:
                        raise ValueError("evaluate stage requires a trained clustering model")
                    from .clustering import calinski_harabasz, inertia

                    if pipeline.schema in {PIPELINE_SCHEMA_V2, PIPELINE_SCHEMA_V3}:
                        values[node.id] = (
                            (
                                "calinski_harabasz",
                                calinski_harabasz(model, rows, selected_features),
                            ),
                            ("inertia", inertia(model, rows, selected_features)),
                        )
                    else:
                        values[node.id] = inertia(model, rows, selected_features)
                else:
                    trained = next(
                        (item for item in dependencies if isinstance(item, TrainedTabularModel)),
                        None,
                    )
                    if trained is None:
                        raise ValueError("evaluate stage requires a trained model")
                    values[node.id] = trained.metrics
            elif executor_kind == "select":
                if pipeline.schema in {PIPELINE_SCHEMA_V2, PIPELINE_SCHEMA_V3}:
                    result = self._select_v2_candidate(
                        node,
                        values,
                        nodes_by_id,
                        lab,
                        backend,
                        rows,
                        runtime_fingerprint or "",
                        pipeline,
                    )
                    values[node.id] = result
                    if checkpoint_save is not None and runtime_fingerprint is not None:
                        checkpoint_save(
                            node.id,
                            {
                                "runtime_fingerprint": runtime_fingerprint,
                                "dependency_fingerprint": dependency_fingerprint,
                                **(
                                    {"checkpoint_codec": checkpoint_codec}
                                    if checkpoint_codec is not None
                                    else {}
                                ),
                                "checkpoint": _checkpoint_payload(node.kind, values[node.id]),
                            },
                        )
                    continue
                training_output = values[by_kind["train"][0].id]
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
            elif executor_kind == "register":
                # Registration is an external side effect. The durable coordinator runs it
                # after materializing the selected artifact and before completing the Job.
                selected = next(
                    (
                        item
                        for item in dependencies
                        if isinstance(item, (ExperimentResult, ClusteringResult))
                    ),
                    None,
                )
                if selected is None:
                    raise ValueError("register stage requires a selected model result")
                values[node.id] = selected
                continue
            else:  # pragma: no cover - PipelineNode validates kinds
                raise ValueError(f"unsupported local ML pipeline node: {node.kind}")
            if (
                checkpoint_save is not None
                and runtime_fingerprint is not None
                and not plugin_checkpoint_saved
            ):
                checkpoint_save(
                    node.id,
                    {
                        "runtime_fingerprint": runtime_fingerprint,
                        "dependency_fingerprint": dependency_fingerprint,
                        **(
                            {"checkpoint_codec": checkpoint_codec}
                            if checkpoint_codec is not None
                            else {}
                        ),
                        "checkpoint": _checkpoint_payload(node.kind, values[node.id]),
                    },
                )

        if cancellation is not None and cancellation.is_cancelled:
            raise MLExecutionCancelled("ML pipeline execution was cancelled")
        if result is None:
            raise ValueError("local ML pipeline did not select a result")
        return result

    @staticmethod
    def _validate_v2_graph(pipeline: PipelineIR, lab: Lab) -> None:
        """Validate bounded candidate branches and per-branch preparation semantics."""
        task = lab.task
        if task not in {"classification", "regression", "clustering"}:
            raise ValueError("PipelineIR v2 candidate selection does not support this Lab task")
        nodes = {
            kind: [node for node in pipeline.nodes if node.kind == kind]
            for kind in (
                "profile",
                "quality_gate",
                "prepare",
                "train",
                "evaluate",
                "select",
                "register",
            )
        }
        if (
            len(nodes["profile"]) != 1
            or len(nodes["quality_gate"]) != 1
            or not 1 <= len(nodes["prepare"]) <= 8
            or len(nodes["train"]) < 1
            or len(nodes["evaluate"]) != len(nodes["train"])
            or len(nodes["select"]) != 1
            or len(nodes["register"]) > 1
            or len(pipeline.nodes) > 24
            or len(pipeline.nodes)
            != 3 + len(nodes["prepare"]) + 2 * len(nodes["train"]) + len(nodes["register"])
        ):
            raise ValueError(
                "PipelineIR v2 requires shared stages, paired candidates, and one select"
            )
        profile, gate, select = (nodes[kind][0] for kind in ("profile", "quality_gate", "select"))
        prepare_ids = {node.id for node in nodes["prepare"]}
        if profile.depends_on or gate.depends_on != (profile.id,):
            raise ValueError("PipelineIR v2 requires profile -> quality_gate")
        if any(prepare.depends_on != (gate.id,) for prepare in nodes["prepare"]):
            raise ValueError("PipelineIR v2 prepare nodes must depend on quality_gate")
        from .services import compile_lab_pipeline

        for prepare in nodes["prepare"]:
            if set(prepare.config) - {"preprocessor"}:
                raise ValueError("PipelineIR v2 prepare node has unsupported configuration")
            preprocessor = prepare.config.get(
                "preprocessor", dict(pipeline.parameters).get("preprocessor", "identity")
            )
            if not isinstance(preprocessor, str):
                raise ValueError("prepare node preprocessor must be a string")
            compile_lab_pipeline(lab, preprocessor=preprocessor)
        train_ids = {node.id for node in nodes["train"]}
        eval_by_train: dict[str, PipelineNode] = {}
        train_config = {"clusters"} if task == "clustering" else {"algorithm"}
        used_prepares: set[str] = set()
        for train in nodes["train"]:
            if (
                len(train.depends_on) != 1
                or train.depends_on[0] not in prepare_ids
                or set(train.config) - train_config
            ):
                raise ValueError(
                    "PipelineIR v2 train nodes must depend on one prepare node and use supported "
                    "task configuration"
                )
            used_prepares.add(train.depends_on[0])
            if task == "clustering":
                cluster_count = train.config.get("clusters")
                if (
                    not isinstance(cluster_count, int)
                    or isinstance(cluster_count, bool)
                    or not 2 <= cluster_count <= 32
                ):
                    raise ValueError("clustering train nodes require 2 to 32 clusters")
        for evaluate in nodes["evaluate"]:
            if len(evaluate.depends_on) != 1 or evaluate.depends_on[0] not in train_ids:
                raise ValueError(
                    "PipelineIR v2 evaluate nodes must depend on one candidate train node"
                )
            if evaluate.depends_on[0] in eval_by_train:
                raise ValueError("PipelineIR v2 requires one evaluate node per candidate")
            eval_by_train[evaluate.depends_on[0]] = evaluate
        if used_prepares != prepare_ids:
            raise ValueError("PipelineIR v2 cannot contain unused prepare nodes")
        if set(eval_by_train) != train_ids or set(select.depends_on) != {
            node.id for node in nodes["evaluate"]
        }:
            raise ValueError("PipelineIR v2 select must depend on every evaluated candidate")
        if nodes["register"]:
            register = nodes["register"][0]
            registration_values = (
                register.config.get("model_id"),
                register.config.get("version"),
            )
            if (
                register.depends_on != (select.id,)
                or set(register.config) != {"model_id", "version"}
                or not all(
                    isinstance(value, str) and bool(value) and value == value.strip()
                    for value in registration_values
                )
            ):
                raise ValueError(
                    "PipelineIR v2 register must depend on select and specify model_id and version"
                )
        if set(select.config) - {"metric", "direction"}:
            raise ValueError("PipelineIR v2 select has unsupported configuration")
        metric = select.config.get(
            "metric",
            "accuracy"
            if task == "classification"
            else "calinski_harabasz"
            if task == "clustering"
            else "r2",
        )
        direction = select.config.get("direction", "maximize")
        expected_metrics = (
            {"accuracy"}
            if task == "classification"
            else {"calinski_harabasz"}
            if task == "clustering"
            else {"r2", "mean_squared_error"}
        )
        if (
            not isinstance(metric, str)
            or metric not in expected_metrics
            or not isinstance(direction, str)
            or direction not in {"maximize", "minimize"}
        ):
            raise ValueError(
                "PipelineIR v2 select metric/direction is unsupported for this Lab task"
            )
        if task == "clustering" and direction != "maximize":
            raise ValueError("clustering candidate selection requires maximize direction")
        for train in nodes["train"]:
            if task == "clustering":
                continue
            algorithm = train.config.get("algorithm")
            if algorithm is not None:
                from .runtime import ALGORITHM_CAPABILITIES

                if not isinstance(algorithm, str) or task not in ALGORITHM_CAPABILITIES.get(
                    algorithm, frozenset()
                ):
                    raise ValueError("train node algorithm is not supported for this Lab task")

    def _validate_v3_graph(self, pipeline: PipelineIR, lab: Lab) -> None:
        """Validate task semantics after the static typed DAG contract passes."""
        from .pipeline_stages import BUILTIN_STAGE_REGISTRY
        from .services import compile_lab_pipeline

        # Plugin declarations are part of the pinned executor identity. Validate
        # graph edges here, where the frozen host contribution registry is available.
        # PipelineIR parsing itself stays independent of installed plugins.
        plugin_stages = {
            item.stage_id: item
            for item in getattr(self._plugin_stage_registry, "items", ())
        }
        nodes_by_id = {node.id: node for node in pipeline.nodes}
        for node in pipeline.nodes:
            definition = BUILTIN_STAGE_REGISTRY.get(node.kind)
            contribution = plugin_stages.get(node.kind)
            if node.kind == "quality_gate" and "suite" in node.config:
                validate_quality_suite(lab, QualitySuite.from_payload(node.config["suite"]))
            if definition is None:
                if contribution is None or contribution.version != node.stage_version:
                    raise ValueError(f"PipelineIR v3 plugin stage is unavailable: {node.kind}")
                if set(node.config) - set(contribution.config_fields):
                    raise ValueError("plugin stage config contains undeclared fields")
                if contribution.effect != "pure":
                    if contribution.effect != "artifact_write":
                        raise ValueError("plugin stage effect is unsupported")
                if contribution.permissions and not self._plugin_artifact_capabilities_available:
                    raise ValueError(
                        "plugin artifact permissions require the durable artifact capability API"
                    )
                contracts = contribution.input_ports
            else:
                if node.stage_version != definition.version:
                    raise ValueError(f"unsupported PipelineIR v3 stage version: {node.kind}")
                contracts = {
                    name: (port.value_type, port.minimum, port.maximum)
                    for name, port in definition.inputs.items()
                }
            supplied = dict(node.inputs)
            if set(supplied) != set(contracts):
                raise ValueError(f"PipelineIR v3 {node.kind} inputs do not match its contract")
            required_builtin_sources = {
                "quality_gate": {"profile": "profile"},
                "prepare": {"quality": "quality_gate"},
                "train": {"prepared": "prepare"},
                "evaluate": {"model": "train"},
                "register": {"selected": "select"},
            }.get(node.kind, {})
            for port, references in supplied.items():
                value_type, minimum, maximum = contracts[port]
                if not minimum <= len(references) <= maximum:
                    raise ValueError(f"PipelineIR v3 {node.kind}.{port} input count is invalid")
                for reference in references:
                    source_id, output_name = reference.rsplit(".", 1)
                    source = nodes_by_id[source_id]
                    if port in required_builtin_sources and source.kind != required_builtin_sources[port]:
                        raise ValueError(
                            f"PipelineIR v3 {node.kind}.{port} requires a built-in "
                            f"{required_builtin_sources[port]} stage"
                        )
                    source_definition = BUILTIN_STAGE_REGISTRY.get(source.kind)
                    source_contribution = plugin_stages.get(source.kind)
                    source_type = (
                        source_definition.output_type
                        if source_definition is not None
                        else source_contribution.output_type
                        if source_contribution is not None
                        else None
                    )
                    if output_name != "out" or source_type != value_type:
                        raise ValueError("PipelineIR v3 has an incompatible typed stage edge")

        selector = next(node for node in pipeline.nodes if node.kind == "select")
        for candidate_id in pipeline.dependency_ids(selector):
            candidate = nodes_by_id[candidate_id]
            if candidate.kind == "evaluate":
                continue
            contribution = plugin_stages.get(candidate.kind)
            if contribution is None or contribution.output_type != "ml.metrics":
                raise ValueError("PipelineIR v3 select candidates must provide ml.metrics")
            candidate_dependencies = pipeline.dependency_ids(candidate)
            if not any(
                nodes_by_id[dependency_id].kind == "train"
                and BUILTIN_STAGE_REGISTRY["train"].output_type == "ml.model"
                for dependency_id in candidate_dependencies
            ):
                raise ValueError("plugin ml.metrics candidates must depend directly on train")

        train_nodes = [node for node in pipeline.nodes if node.kind == "train"]
        prepare_nodes = [node for node in pipeline.nodes if node.kind == "prepare"]
        selectors = [node for node in pipeline.nodes if node.kind == "select"]
        for prepare in prepare_nodes:
            preprocessor = prepare.config.get("preprocessor", "identity")
            if not isinstance(preprocessor, str):
                raise ValueError("PipelineIR v3 preprocessor must be text")
            if lab.task == "clustering" and preprocessor != "identity":
                raise ValueError("PipelineIR v3 does not support clustering preprocessors")
            compile_lab_pipeline(lab, preprocessor=preprocessor)
        for train in train_nodes:
            algorithm = train.config.get("algorithm")
            clusters = train.config.get("clusters")
            if lab.task == "clustering":
                if algorithm is not None or clusters is None:
                    raise ValueError("PipelineIR v3 clustering train nodes require clusters only")
            elif clusters is not None:
                raise ValueError("PipelineIR v3 supervised train nodes cannot set clusters")
            if algorithm is not None:
                from .runtime import ALGORITHM_CAPABILITIES

                if not isinstance(algorithm, str) or lab.task not in ALGORITHM_CAPABILITIES.get(
                    algorithm, frozenset()
                ):
                    raise ValueError("PipelineIR v3 train algorithm is not supported for this Lab")
        selector = selectors[0]
        metric = selector.config.get(
            "metric",
            "calinski_harabasz"
            if lab.task == "clustering"
            else "accuracy"
            if lab.task == "classification"
            else "r2",
        )
        direction = selector.config.get(
            "direction", "minimize" if metric == "mean_squared_error" else "maximize"
        )
        allowed_metrics = (
            {"calinski_harabasz"}
            if lab.task == "clustering"
            else {"accuracy"}
            if lab.task == "classification"
            else {"r2", "mean_squared_error"}
        )
        if metric not in allowed_metrics or direction not in {"maximize", "minimize"}:
            raise ValueError("PipelineIR v3 selection metric/direction is unsupported for this Lab")
        if lab.task == "clustering" and direction != "maximize":
            raise ValueError("PipelineIR v3 clustering selection must maximize Calinski-Harabasz")
        if metric == "mean_squared_error" and direction != "minimize":
            raise ValueError("PipelineIR v3 mean_squared_error selection must minimize")

    @staticmethod
    def _plugin_input_artifacts(
        node: PipelineNode,
        values: Mapping[str, object],
        loader: Callable[[Mapping[str, object]], bytes] | None,
        *,
        require_permission: bool,
    ) -> dict[str, bytes]:
        artifacts: dict[str, bytes] = {}
        for dependency_id in sorted(
            {
                reference.rsplit(".", 1)[0]
                for _, references in node.inputs
                for reference in references
            }
        ):
            value = values.get(dependency_id)
            if not isinstance(value, Mapping):
                continue
            references = value.get("__ronin_artifacts__")
            if not isinstance(references, Mapping):
                continue
            if not require_permission:
                continue
            if loader is None:
                raise ValueError("plugin stage artifact:read requires the durable artifact API")
            for name, reference in sorted(references.items()):
                if not isinstance(name, str) or not isinstance(reference, Mapping):
                    raise ValueError("plugin dependency artifact reference is invalid")
                artifact_name = f"{dependency_id}/{name}"
                if artifact_name in artifacts:
                    raise ValueError("plugin dependency artifact names collide")
                artifacts[artifact_name] = loader(reference)
                if sum(len(data) for data in artifacts.values()) > 512 * 1024:
                    raise ValueError("plugin dependency artifacts exceed the host byte limit")
        return artifacts

    @staticmethod
    def _select_v2_candidate(
        node: PipelineNode,
        values: Mapping[str, object],
        nodes_by_id: Mapping[str, PipelineNode],
        lab: Lab,
        backend: MLBackend,
        rows: Sequence[Mapping[str, object]],
        runtime_fingerprint: str,
        pipeline: PipelineIR | None = None,
    ) -> ExperimentResult | ClusteringResult:
        metric = cast(
            str,
            node.config.get(
                "metric",
                "accuracy"
                if lab.task == "classification"
                else "calinski_harabasz"
                if lab.task == "clustering"
                else "r2",
            ),
        )
        direction = cast(
            str,
            node.config.get("direction", "maximize"),
        )
        if lab.task == "clustering":
            cluster_candidates: list[tuple[float, str, KMeansModel]] = []
            selected_dependencies = pipeline.dependency_ids(node) if pipeline else node.depends_on
            for candidate_id in sorted(selected_dependencies):
                candidate = nodes_by_id[candidate_id]
                candidate_dependencies = (
                    pipeline.dependency_ids(candidate) if pipeline else candidate.depends_on
                )
                train_id = next(
                    (
                        dependency_id
                        for dependency_id in candidate_dependencies
                        if isinstance(values.get(dependency_id), KMeansModel)
                    ),
                    None,
                )
                model = values.get(train_id) if train_id is not None else None
                score = values.get(candidate_id)
                score_map = _candidate_score_map(score)
                if train_id is None or not isinstance(model, KMeansModel) or score_map is None:
                    raise ValueError("select stage requires evaluated K-Means candidates")
                score_value = score_map.get(metric)
                if not isinstance(score_value, (int, float)):
                    raise ValueError(f"candidate does not provide selection metric {metric!r}")
                cluster_candidates.append((float(score_value), train_id, model))
            if not cluster_candidates:
                raise ValueError("select stage requires at least one evaluated candidate")
            cluster_candidates.sort(key=lambda item: (-item[0], item[1]))
            score, _, model = cluster_candidates[0]
            artifact = json.dumps(
                model.to_artifact(), sort_keys=True, separators=(",", ":")
            ).encode()
            digest = hashlib.sha256(artifact).hexdigest()
            from .clustering import inertia

            model_inertia = inertia(
                model,
                rows,
                tuple(feature.column for feature in lab.features if feature.role != "ignored"),
            )
            return ClusteringResult(
                lab.id,
                backend.backend_id,
                len(rows),
                tuple(feature.column for feature in lab.features if feature.role != "ignored"),
                model,
                f"sha256:{digest}",
                model_inertia,
                runtime_fingerprint,
                metric,
                score,
            )
        tabular_candidates: list[tuple[float, str, TrainedTabularModel]] = []
        selected_dependencies = pipeline.dependency_ids(node) if pipeline else node.depends_on
        for candidate_id in sorted(selected_dependencies):
            candidate = nodes_by_id[candidate_id]
            candidate_dependencies = (
                pipeline.dependency_ids(candidate) if pipeline else candidate.depends_on
            )
            train_id = next(
                (
                    dependency_id
                    for dependency_id in candidate_dependencies
                    if isinstance(values.get(dependency_id), TrainedTabularModel)
                ),
                None,
            )
            trained = values.get(train_id) if train_id is not None else None
            scores = values.get(candidate_id)
            score_map = _candidate_score_map(scores)
            if train_id is None or not isinstance(trained, TrainedTabularModel) or score_map is None:
                raise ValueError("select stage requires evaluated tabular candidates")
            score = score_map.get(metric)
            if score is None or not isinstance(score, (int, float)):
                raise ValueError(f"candidate does not provide selection metric {metric!r}")
            tabular_candidates.append((float(score), train_id, trained))
        if not tabular_candidates:
            raise ValueError("select stage requires at least one evaluated candidate")
        tabular_candidates.sort(
            key=lambda item: ((-item[0] if direction == "maximize" else item[0]), item[1])
        )
        model = tabular_candidates[0][2]
        digest = hashlib.sha256(model.artifact_bytes).hexdigest()
        return ExperimentResult(
            lab.id, backend.backend_id, len(rows), model, f"sha256:{digest}", runtime_fingerprint
        )

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
        self._ensure_backend_available(backend)
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


__all__ = [
    "BackendNotFound",
    "ClusteringResult",
    "ExperimentResult",
    "LocalExperimentRunner",
    "MLExecutionCancelled",
]
