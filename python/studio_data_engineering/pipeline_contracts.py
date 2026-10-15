"""Provider-neutral pipeline parameter schema and validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from studio_core.canonical_json import decode as decode_canonical_json
from studio_core.canonical_json import encode as encode_canonical_json

ParameterType = Literal["string", "integer", "number", "boolean"]


@dataclass(frozen=True, slots=True)
class PipelineParameter:
    name: str
    type: ParameterType
    required: bool = True
    default: object | None = None

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip():
            raise ValueError("pipeline parameter name must be non-empty and trimmed")
        if self.type not in {"string", "integer", "number", "boolean"}:
            raise ValueError("unsupported pipeline parameter type")
        if not self.required and self.default is None:
            raise ValueError("optional pipeline parameters require a default")
        if self.default is not None:
            _validate_value(self.type, self.default, self.name)

    def to_data(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "default": self.default,
        }


@dataclass(frozen=True, slots=True)
class PipelineParameterSchema:
    parameters: tuple[PipelineParameter, ...] = ()

    def __post_init__(self) -> None:
        names = tuple(parameter.name for parameter in self.parameters)
        if len(names) != len(set(names)):
            raise ValueError("pipeline parameter names must be unique")

    def validate(self, values: dict[str, object]) -> dict[str, object]:
        expected = {parameter.name for parameter in self.parameters}
        unknown = set(values) - expected
        if unknown:
            raise ValueError(f"unknown pipeline parameters: {sorted(unknown)}")
        resolved: dict[str, object] = {}
        for parameter in self.parameters:
            if parameter.name not in values:
                if parameter.required:
                    raise ValueError(f"missing required pipeline parameter: {parameter.name}")
                resolved[parameter.name] = parameter.default
                continue
            _validate_value(parameter.type, values[parameter.name], parameter.name)
            resolved[parameter.name] = values[parameter.name]
        return resolved

    def to_data(self) -> dict[str, object]:
        return {
            "version": 1,
            "parameters": [parameter.to_data() for parameter in self.parameters],
        }

    def canonical_json(self) -> str:
        return encode_canonical_json(self.to_data()).decode()

    @classmethod
    def from_data(cls, value: object) -> PipelineParameterSchema:
        if not isinstance(value, dict) or set(value) != {"version", "parameters"}:
            raise ValueError("pipeline parameter schema has invalid shape")
        if value["version"] != 1 or not isinstance(value["parameters"], list):
            raise ValueError("unsupported pipeline parameter schema version")
        parameters: list[PipelineParameter] = []
        for item in value["parameters"]:
            if not isinstance(item, dict) or set(item) != {"name", "type", "required", "default"}:
                raise ValueError("pipeline parameter has invalid shape")
            if not isinstance(item["name"], str) or not isinstance(item["type"], str):
                raise TypeError("pipeline parameter name/type must be strings")
            if not isinstance(item["required"], bool):
                raise TypeError("pipeline parameter required must be boolean")
            parameters.append(
                PipelineParameter(
                    item["name"],
                    item["type"],  # type: ignore[arg-type]
                    item["required"],
                    item["default"],
                )
            )
        return cls(tuple(parameters))

    @classmethod
    def from_json(cls, payload: str) -> PipelineParameterSchema:
        return cls.from_data(decode_canonical_json(payload))


def _validate_value(kind: ParameterType, value: object, name: str) -> None:
    valid = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }[kind]
    if not valid:
        raise ValueError(f"pipeline parameter {name} must be a {kind}")


__all__ = ("PipelineParameter", "PipelineParameterSchema", "ParameterType")
