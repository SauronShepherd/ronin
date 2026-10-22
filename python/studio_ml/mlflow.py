"""Bounded MLflow-compatible metadata interchange without a server dependency."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

from studio_core.ml import Experiment, MLRunRecord, RegisteredModelVersion
from studio_core.canonical_json import decode, encode

MLFLOW_SUBSET_SCHEMA = "ronin.mlflow-subset/v1"
MLFLOW_METADATA_SCHEMA = "ronin.mlflow-metadata/v1"
SUPPORTED_MLFLOW_FLAVORS = frozenset({"python_function", "sklearn"})


class MLflowFlavorError(ValueError):
    """Raised when an MLflow flavor is outside the safe metadata subset."""


def _safe_reference(value: str, label: str) -> None:
    if (
        not value
        or value != value.strip()
        or any(char in value for char in "\r\n\x00?#")
        or "@" in value.split("://", 1)[-1].split("/", 1)[0]
    ):
        raise ValueError(f"{label} contains unsafe credential-bearing URI syntax")


@dataclass(frozen=True, slots=True)
class MLflowSubset:
    model_id: str
    version: str
    framework: str
    artifact_digest: str
    inputs: tuple[tuple[str, str], ...]
    outputs: tuple[tuple[str, str], ...]
    metrics: tuple[tuple[str, float], ...] = ()
    schema: str = MLFLOW_SUBSET_SCHEMA

    def __post_init__(self) -> None:
        for value, name in (
            (self.model_id, "model_id"),
            (self.version, "version"),
            (self.framework, "framework"),
            (self.artifact_digest, "artifact_digest"),
        ):
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"{name} must be non-empty and trimmed")
        if len(self.artifact_digest) != 64 or any(
            c not in "0123456789abcdef" for c in self.artifact_digest
        ):
            raise ValueError("artifact_digest must be a lowercase sha256 digest")
        if self.schema != MLFLOW_SUBSET_SCHEMA:
            raise ValueError("unsupported MLflow subset schema")
        for values, label in ((self.inputs, "input"), (self.outputs, "output")):
            if any(
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(kind, str)
                or not kind.strip()
                for name, kind in values
            ):
                raise ValueError(f"MLflow {label} names and types must be non-empty text")
            if len({name for name, _ in values}) != len(values):
                raise ValueError(f"MLflow {label} names must be unique")
        if len({name for name, _ in self.metrics}) != len(self.metrics):
            raise ValueError("MLflow metric names must be unique")
        for name, value in self.metrics:
            try:
                finite = isfinite(float(value))
            except (OverflowError, TypeError, ValueError):
                finite = False
            if (
                not isinstance(name, str)
                or not name.strip()
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not finite
            ):
                raise ValueError("MLflow metrics must be finite numbers")
            raise ValueError("MLflow metrics must be finite numbers")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "model_id": self.model_id,
            "version": self.version,
            "framework": self.framework,
            "artifact_digest": self.artifact_digest,
            "inputs": [{"name": name, "type": kind} for name, kind in self.inputs],
            "outputs": [{"name": name, "type": kind} for name, kind in self.outputs],
            "metrics": dict(self.metrics),
        }

    def to_bytes(self) -> bytes:
        return encode(self.to_payload())

    @classmethod
    def from_bytes(cls, payload: bytes) -> MLflowSubset:
        value = decode(payload)
        if not isinstance(value, Mapping) or set(value) != {
            "schema",
            "model_id",
            "version",
            "framework",
            "artifact_digest",
            "inputs",
            "outputs",
            "metrics",
        }:
            raise ValueError("MLflow subset has invalid shape")

        def pairs(raw: object, label: str) -> tuple[tuple[str, str], ...]:
            if not isinstance(raw, list):
                raise ValueError(f"MLflow {label} must be a list")
            result = []
            for item in raw:
                if (
                    not isinstance(item, Mapping)
                    or set(item) != {"name", "type"}
                    or not all(isinstance(item[key], str) for key in ("name", "type"))
                ):
                    raise ValueError(f"MLflow {label} item is invalid")
                result.append((item["name"], item["type"]))
            return tuple(result)

        metrics = value["metrics"]
        if not isinstance(metrics, Mapping) or not all(
            isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
            for k, v in metrics.items()
        ):
            raise ValueError("MLflow metrics are invalid")

        def text_field(name: str) -> str:
            field = value[name]
            if not isinstance(field, str):
                raise ValueError(f"MLflow {name} must be text")
            return field

        def metric_value(raw: object) -> float:
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError("MLflow metrics are invalid")
            return float(raw)

        metric_pairs = tuple(sorted((key, metric_value(metric)) for key, metric in metrics.items()))
        return cls(
            text_field("model_id"),
            text_field("version"),
            text_field("framework"),
            text_field("artifact_digest"),
            pairs(value["inputs"], "inputs"),
            pairs(value["outputs"], "outputs"),
            metric_pairs,
            text_field("schema"),
        )


@dataclass(frozen=True, slots=True)
class MLflowMetadata:
    """Portable MLflow tracking/registry metadata without executable artifacts."""

    experiment: Experiment
    run: MLRunRecord
    model: RegisteredModelVersion | None = None
    flavor: str = "python_function"
    schema: str = MLFLOW_METADATA_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != MLFLOW_METADATA_SCHEMA:
            raise ValueError("unsupported MLflow metadata schema")
        if self.flavor not in SUPPORTED_MLFLOW_FLAVORS:
            raise MLflowFlavorError(f"unsupported MLflow flavor: {self.flavor}")
        if self.run.experiment_id != self.experiment.id:
            raise ValueError("MLflow run does not belong to the exported experiment")
        for reference in self.run.artifact_refs:
            _safe_reference(reference, "MLflow run artifact reference")
        if self.run.runtime_snapshot_ref is not None:
            _safe_reference(self.run.runtime_snapshot_ref, "MLflow runtime snapshot reference")
        if self.model is not None and self.model.source_run_id != self.run.id:
            raise ValueError("MLflow model does not reference the exported run")
        if self.model is not None:
            _safe_reference(self.model.artifact_ref, "MLflow model artifact reference")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "flavor": self.flavor,
            "experiment": self.experiment.to_payload(),
            "run": self.run.to_payload(),
            "model": None if self.model is None else self.model.to_payload(),
        }

    def to_bytes(self) -> bytes:
        return encode(self.to_payload())

    @classmethod
    def from_bytes(cls, payload: bytes) -> "MLflowMetadata":
        value = decode(payload)
        expected = {"schema", "flavor", "experiment", "run", "model"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("MLflow metadata has invalid shape")
        schema, flavor = value["schema"], value["flavor"]
        if not isinstance(schema, str) or not isinstance(flavor, str):
            raise ValueError("MLflow metadata schema and flavor must be text")
        experiment = Experiment.from_payload(value["experiment"])
        run = MLRunRecord.from_payload(value["run"])
        raw_model = value["model"]
        model = None if raw_model is None else RegisteredModelVersion.from_payload(raw_model)
        return cls(experiment, run, model, flavor, schema)


def export_mlflow_metadata(
    experiment: Experiment,
    run: MLRunRecord,
    model: RegisteredModelVersion | None = None,
    *,
    flavor: str = "python_function",
) -> bytes:
    """Export secret-free tracking/registry metadata for a safe MLflow subset."""

    return MLflowMetadata(experiment, run, model, flavor).to_bytes()


def import_mlflow_metadata(payload: bytes) -> MLflowMetadata:
    """Import metadata only; executable MLflow flavors and artifact URIs are not loaded."""

    return MLflowMetadata.from_bytes(payload)


__all__ = (
    "MLFLOW_METADATA_SCHEMA",
    "MLFLOW_SUBSET_SCHEMA",
    "SUPPORTED_MLFLOW_FLAVORS",
    "MLflowFlavorError",
    "MLflowMetadata",
    "MLflowSubset",
    "export_mlflow_metadata",
    "import_mlflow_metadata",
)
