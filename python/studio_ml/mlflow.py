"""Bounded MLflow-compatible metadata interchange without a server dependency."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from studio_core.canonical_json import decode, encode

MLFLOW_SUBSET_SCHEMA = "ronin.mlflow-subset/v1"


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
        if len(set(name for name, _ in self.inputs)) != len(self.inputs):
            raise ValueError("MLflow input names must be unique")
        if len(set(name for name, _ in self.outputs)) != len(self.outputs):
            raise ValueError("MLflow output names must be unique")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "model_id": self.model_id,
            "version": self.version,
            "framework": self.framework,
            "artifact_digest": self.artifact_digest,
            "inputs": [dict(name=name, type=kind) for name, kind in self.inputs],
            "outputs": [dict(name=name, type=kind) for name, kind in self.outputs],
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


__all__ = ("MLFLOW_SUBSET_SCHEMA", "MLflowSubset")
