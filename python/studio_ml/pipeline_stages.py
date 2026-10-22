"""Static, versioned built-in PipelineIR stage contracts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import inspect
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class InputPort:
    value_type: str
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class StageDefinition:
    kind: str
    version: int
    inputs: Mapping[str, InputPort]
    config_fields: tuple[str, ...]
    output_type: str
    effect: str
    checkpoint_codec: str
    executor: str
    terminal: bool = False


def _stage(
    kind: str,
    inputs: Mapping[str, InputPort],
    output_type: str,
    *,
    effect: str = "pure",
    terminal: bool = False,
) -> StageDefinition:
    config_fields = {
        "profile": (),
        "quality_gate": ("suite",),
        "prepare": ("preprocessor",),
        "train": ("algorithm", "clusters"),
        "evaluate": (),
        "select": ("direction", "metric"),
        "register": ("model_id", "version"),
    }[kind]
    return StageDefinition(
        kind,
        1,
        MappingProxyType(dict(inputs)),
        config_fields,
        output_type,
        effect,
        f"ronin.ml.checkpoint/{kind}/v1",
        f"studio_ml.runner:{kind}:v1",
        terminal,
    )


BUILTIN_STAGE_REGISTRY: Mapping[str, StageDefinition] = MappingProxyType(
    {
        "profile": _stage("profile", {}, "quality.profile"),
        "quality_gate": _stage(
            "quality_gate", {"profile": InputPort("quality.profile", 1, 1)}, "quality.passed"
        ),
        "prepare": _stage("prepare", {"quality": InputPort("quality.passed", 1, 1)}, "ml.prepared"),
        "train": _stage("train", {"prepared": InputPort("ml.prepared", 1, 1)}, "ml.model"),
        "evaluate": _stage("evaluate", {"model": InputPort("ml.model", 1, 1)}, "ml.metrics"),
        "select": _stage("select", {"candidates": InputPort("ml.metrics", 1, 23)}, "ml.selected"),
        "register": _stage(
            "register",
            {"selected": InputPort("ml.selected", 1, 1)},
            "ml.selected",
            effect="registry_write",
            terminal=True,
        ),
    }
)

_PREPROCESSORS = {
    "identity",
    "standard_scale",
    "one_hot",
    "median_impute",
    "one_hot_median_impute",
}
_ALGORITHMS = {
    "logistic_regression",
    "linear_regression",
    "decision_tree_classifier",
    "decision_tree_regressor",
    "random_forest_classifier",
    "random_forest_regressor",
    "gradient_boosting_classifier",
    "gradient_boosting_regressor",
}
_METRICS = {"accuracy", "r2", "mean_squared_error", "calinski_harabasz"}


def builtin_stage_registry_digest() -> str:
    """Hash stage declarations and the exact host code/runtime that executes them."""
    payload = [
        {
            "kind": stage.kind,
            "version": stage.version,
            "inputs": {
                name: {
                    "type": port.value_type,
                    "minimum": port.minimum,
                    "maximum": port.maximum,
                }
                for name, port in sorted(stage.inputs.items())
            },
            "output_type": stage.output_type,
            "config_fields": list(stage.config_fields),
            "effect": stage.effect,
            "checkpoint_codec": stage.checkpoint_codec,
            "executor": stage.executor,
            "terminal": stage.terminal,
        }
        for stage in sorted(BUILTIN_STAGE_REGISTRY.values(), key=lambda item: item.kind)
    ]
    package_root = Path(__file__).resolve().parents[1]
    source_paths = {
        "domain": package_root / "studio_ml" / "domain.py",
        "backends": package_root / "studio_ml" / "backends.py",
        "runner": package_root / "studio_ml" / "runner.py",
        "plugin_stage_runtime": package_root / "studio_ml" / "plugin_stage_runtime.py",
        "runtime": package_root / "studio_ml" / "runtime.py",
        "clustering": package_root / "studio_ml" / "clustering.py",
        "quality": package_root / "studio_ml" / "quality.py",
        "services": package_root / "studio_ml" / "services.py",
        "orchestration": package_root / "studio_ml" / "orchestration.py",
        "plugin_contract": package_root / "studio_core" / "plugins.py",
        "canonical_json": package_root / "studio_core" / "canonical_json.py",
        "cancellation": package_root / "studio_kernel" / "session.py",
        "oci_command_runner": package_root / "studio_runners" / "container.py",
        "artifact_ports": package_root / "studio_storage" / "ports.py",
        "artifact_store": package_root / "studio_storage" / "artifacts.py",
        "s3_artifact_store": package_root / "studio_storage" / "s3_artifacts.py",
    }
    source_digests: dict[str, str] = {}
    for name, path in source_paths.items():
        try:
            source_digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError(f"PipelineIR v3 executor source is unavailable: {name}") from exc
    dependencies: dict[str, str | None] = {}
    for distribution in ("joblib", "numpy", "scikit-learn", "scipy"):
        try:
            dependencies[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            dependencies[distribution] = None
    identity = {
        "stages": payload,
        "validation_policy": {
            "preprocessors": sorted(_PREPROCESSORS),
            "algorithms": sorted(_ALGORITHMS),
            "metrics": sorted(_METRICS),
            "source_digest": hashlib.sha256(
                "\n".join(
                    inspect.getsource(item)
                    for item in (
                        InputPort,
                        StageDefinition,
                        _stage,
                        validate_stage_configuration,
                    )
                ).encode("utf-8")
            ).hexdigest(),
        },
        "executor": {
            "python": [sys.implementation.name, *sys.version_info[:3]],
            "sources": source_digests,
            "dependencies": dependencies,
        },
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def pipeline_stage_registry_digest(plugin_registry: object | None = None) -> str:
    """Bind built-in definitions and installed plugin declarations into one Job identity."""
    plugin_digest = getattr(plugin_registry, "digest", None)
    if plugin_digest is None:
        plugin_digest = hashlib.sha256(b"[]").hexdigest()
    if (
        not isinstance(plugin_digest, str)
        or len(plugin_digest) != 64
        or any(character not in "0123456789abcdef" for character in plugin_digest)
    ):
        raise ValueError("plugin pipeline stage registry has an invalid digest")
    return hashlib.sha256(
        f"ronin.ml-stage-registry/v1:{builtin_stage_registry_digest()}:{plugin_digest}".encode(
            "ascii"
        )
    ).hexdigest()


def validate_stage_configuration(kind: str, version: int, config: Mapping[str, object]) -> None:
    definition = BUILTIN_STAGE_REGISTRY.get(kind)
    if definition is None or version != definition.version:
        raise ValueError(f"unsupported PipelineIR v3 stage or version: {kind!r} v{version}")
    allowed = set(definition.config_fields)
    if set(config) - allowed:
        raise ValueError(f"PipelineIR v3 {kind} config has unsupported fields")
    if kind == "quality_gate" and "suite" in config:
        from .quality import QualitySuite

        QualitySuite.from_payload(config["suite"])
    if kind == "prepare":
        preprocessor = config.get("preprocessor", "identity")
        if not isinstance(preprocessor, str) or preprocessor not in _PREPROCESSORS:
            raise ValueError("PipelineIR v3 prepare preprocessor is unsupported")
    if kind == "train":
        algorithm = config.get("algorithm")
        clusters = config.get("clusters")
        if algorithm is not None and (
            not isinstance(algorithm, str) or algorithm not in _ALGORITHMS
        ):
            raise ValueError("PipelineIR v3 train algorithm is unsupported")
        if clusters is not None and (
            not isinstance(clusters, int) or isinstance(clusters, bool) or not 2 <= clusters <= 32
        ):
            raise ValueError("PipelineIR v3 train clusters must be between 2 and 32")
        if algorithm is not None and clusters is not None:
            raise ValueError("PipelineIR v3 train config cannot set algorithm and clusters")
    if kind == "select":
        metric = config.get("metric", "accuracy")
        if not isinstance(metric, str) or metric not in _METRICS:
            raise ValueError("PipelineIR v3 select metric is unsupported")
        direction = config.get("direction", "maximize")
        if not isinstance(direction, str) or direction not in {"maximize", "minimize"}:
            raise ValueError("PipelineIR v3 select direction is unsupported")
    if kind == "register":
        values = (config.get("model_id"), config.get("version"))
        if set(config) != {"model_id", "version"} or any(
            not isinstance(value, str) or not value or value != value.strip() or len(value) > 256
            for value in values
        ):
            raise ValueError("PipelineIR v3 register requires model_id and version")
