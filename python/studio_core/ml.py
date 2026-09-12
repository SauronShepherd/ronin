"""Provider-neutral experiment tracking and model-registry contracts for Public v1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .canonical_json import decode as decode_canonical_json
from .canonical_json import encode as encode_canonical_json
from .catalog import AssetRef

ModelStage: TypeAlias = Literal["candidate", "champion", "archived"]
EvaluationStatus: TypeAlias = Literal["passed", "failed", "unknown"]


def _text(value: str, name: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _pairs(values: tuple[tuple[str, str], ...], name: str) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value in values:
        key = _text(key, f"{name} key")
        value = _text(value, f"{name} value")
        if any(term in key.casefold() for term in ("password", "secret", "token", "credential", "api_key")):
            raise ValueError(f"{name} must not contain credential-bearing keys")
        if key in seen:
            raise ValueError(f"{name} keys must be unique")
        seen.add(key)
        result.append((key, value))
    return tuple(sorted(result))


@dataclass(frozen=True, order=True, slots=True)
class ExperimentId:
    value: str
    def __post_init__(self) -> None: _text(self.value, "experiment id")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, order=True, slots=True)
class MLRunId:
    value: str
    def __post_init__(self) -> None: _text(self.value, "ML run id")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, order=True, slots=True)
class ModelId:
    value: str
    def __post_init__(self) -> None: _text(self.value, "model id")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, order=True, slots=True)
class ModelVersion:
    value: str
    def __post_init__(self) -> None: _text(self.value, "model version")
    def __str__(self) -> str: return self.value


@dataclass(frozen=True, slots=True)
class Experiment:
    id: ExperimentId
    name: str
    description: str | None = None

    def __post_init__(self) -> None:
        _text(self.name, "experiment name")
        if self.description is not None: _text(self.description, "experiment description")

    def to_payload(self) -> dict[str, object]:
        return {"id": self.id.value, "name": self.name, "description": self.description}

    def to_json(self) -> str:
        return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> Experiment:
        if not isinstance(payload, Mapping) or set(payload) != {"id", "name", "description"}:
            raise ValueError("experiment has invalid shape")
        identifier, name, description = payload["id"], payload["name"], payload["description"]
        if not isinstance(identifier, str) or not isinstance(name, str) or (description is not None and not isinstance(description, str)):
            raise ValueError("experiment fields have invalid types")
        return cls(ExperimentId(identifier), name, cast(str | None, description))

    @classmethod
    def from_json(cls, payload: str) -> Experiment:
        return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, order=True, slots=True)
class MetricValue:
    name: str
    value: float
    step: int = 0

    def __post_init__(self) -> None:
        _text(self.name, "metric name")
        if self.step < 0: raise ValueError("metric step must be non-negative")
        if self.value != self.value or self.value in (float("inf"), float("-inf")):
            raise ValueError("metric value must be finite")

    def to_payload(self) -> dict[str, object]:
        return {"name": self.name, "value": self.value, "step": self.step}


@dataclass(frozen=True, slots=True)
class MLRunRecord:
    id: MLRunId
    experiment_id: ExperimentId
    execution_ref: str
    source_revision: str
    datasets: tuple[AssetRef, ...]
    parameters: tuple[tuple[str, str], ...] = ()
    metrics: tuple[MetricValue, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    runtime_snapshot_ref: str | None = None

    def __post_init__(self) -> None:
        _text(self.execution_ref, "ML execution ref")
        _text(self.source_revision, "ML source revision")
        datasets = tuple(sorted(set(self.datasets)))
        if not datasets: raise ValueError("ML run requires at least one governed dataset revision")
        metrics = tuple(sorted(self.metrics, key=lambda item: (item.name, item.step)))
        if len(metrics) != len(set((item.name, item.step) for item in metrics)):
            raise ValueError("ML metric name/step pairs must be unique")
        artifacts = tuple(sorted(_text(value, "ML artifact ref") for value in self.artifact_refs))
        if len(artifacts) != len(set(artifacts)): raise ValueError("ML artifact refs must be unique")
        if self.runtime_snapshot_ref is not None: _text(self.runtime_snapshot_ref, "runtime snapshot ref")
        object.__setattr__(self, "datasets", datasets)
        object.__setattr__(self, "parameters", _pairs(self.parameters, "ML parameters"))
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "artifact_refs", artifacts)

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id.value,
            "experiment_id": self.experiment_id.value,
            "execution_ref": self.execution_ref,
            "source_revision": self.source_revision,
            "datasets": [ref.to_payload() for ref in self.datasets],
            "parameters": dict(self.parameters),
            "metrics": [metric.to_payload() for metric in self.metrics],
            "artifact_refs": list(self.artifact_refs),
            "runtime_snapshot_ref": self.runtime_snapshot_ref,
        }

    def to_json(self) -> str: return encode_canonical_json(self.to_payload()).decode("utf-8")

    @classmethod
    def from_payload(cls, payload: object) -> MLRunRecord:
        expected = {"id","experiment_id","execution_ref","source_revision","datasets","parameters","metrics","artifact_refs","runtime_snapshot_ref"}
        if not isinstance(payload, Mapping) or set(payload) != expected: raise ValueError("ML run has invalid shape")
        if not all(isinstance(payload[k], str) for k in ("id","experiment_id","execution_ref","source_revision")): raise ValueError("ML run identity fields must be strings")
        datasets, parameters, metrics, artifacts, runtime = payload["datasets"], payload["parameters"], payload["metrics"], payload["artifact_refs"], payload["runtime_snapshot_ref"]
        if not isinstance(datasets, list) or not isinstance(metrics, list) or not isinstance(artifacts, list): raise ValueError("ML run collections have invalid types")
        if not isinstance(parameters, Mapping) or not all(isinstance(k,str) and isinstance(v,str) for k,v in parameters.items()): raise ValueError("ML parameters must be string object")
        if not all(isinstance(v,str) for v in artifacts): raise ValueError("ML artifact refs must be strings")
        if runtime is not None and not isinstance(runtime, str): raise ValueError("runtime snapshot ref must be string or null")
        parsed_metrics: list[MetricValue] = []
        for item in metrics:
            if not isinstance(item, Mapping) or set(item) != {"name","value","step"}: raise ValueError("metric has invalid shape")
            name, value, step = item["name"], item["value"], item["step"]
            if not isinstance(name,str) or not isinstance(value,(int,float)) or isinstance(value,bool) or not isinstance(step,int) or isinstance(step,bool): raise ValueError("metric has invalid types")
            parsed_metrics.append(MetricValue(name, float(value), step))
        return cls(MLRunId(cast(str,payload["id"])), ExperimentId(cast(str,payload["experiment_id"])), cast(str,payload["execution_ref"]), cast(str,payload["source_revision"]), tuple(AssetRef.from_payload(item) for item in datasets), tuple(sorted(cast(Mapping[str,str],parameters).items())), tuple(parsed_metrics), tuple(cast(list[str], artifacts)), cast(str|None,runtime))

    @classmethod
    def from_json(cls, payload: str) -> MLRunRecord: return cls.from_payload(decode_canonical_json(payload))


@dataclass(frozen=True, slots=True)
class ModelSignature:
    inputs: tuple[tuple[str, str], ...]
    outputs: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", _pairs(self.inputs, "model inputs"))
        object.__setattr__(self, "outputs", _pairs(self.outputs, "model outputs"))
        if not self.inputs or not self.outputs: raise ValueError("model signature requires inputs and outputs")

    def to_payload(self) -> dict[str, object]: return {"inputs": dict(self.inputs), "outputs": dict(self.outputs)}


@dataclass(frozen=True, slots=True)
class RegisteredModelVersion:
    model_id: ModelId
    version: ModelVersion
    source_run_id: MLRunId
    artifact_ref: str
    artifact_digest: str
    framework: str
    signature: ModelSignature
    stage: ModelStage = "candidate"

    def __post_init__(self) -> None:
        _text(self.artifact_ref, "model artifact ref"); _text(self.artifact_digest, "model artifact digest"); _text(self.framework, "model framework")
        if self.stage not in {"candidate","champion","archived"}: raise ValueError("unsupported model stage")

    def to_payload(self) -> dict[str, object]:
        return {"model_id":self.model_id.value,"version":self.version.value,"source_run_id":self.source_run_id.value,"artifact_ref":self.artifact_ref,"artifact_digest":self.artifact_digest,"framework":self.framework,"signature":self.signature.to_payload(),"stage":self.stage}

    def to_json(self) -> str: return encode_canonical_json(self.to_payload()).decode("utf-8")


@dataclass(frozen=True, slots=True)
class ModelEvaluation:
    model_id: ModelId
    version: ModelVersion
    dataset: AssetRef
    status: EvaluationStatus
    metrics: tuple[MetricValue, ...]
    execution_ref: str

    def __post_init__(self) -> None:
        if self.status not in {"passed","failed","unknown"}: raise ValueError("unsupported evaluation status")
        _text(self.execution_ref, "evaluation execution ref")
        metrics = tuple(sorted(self.metrics, key=lambda item: (item.name,item.step)))
        if not metrics: raise ValueError("model evaluation requires at least one metric")
        object.__setattr__(self,"metrics",metrics)

    def to_payload(self) -> dict[str, object]:
        return {"model_id":self.model_id.value,"version":self.version.value,"dataset":self.dataset.to_payload(),"status":self.status,"metrics":[item.to_payload() for item in self.metrics],"execution_ref":self.execution_ref}

    def to_json(self) -> str: return encode_canonical_json(self.to_payload()).decode("utf-8")
