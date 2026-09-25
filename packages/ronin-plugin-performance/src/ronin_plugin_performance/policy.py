"""Versioned, serializable thresholds for Performance Studio findings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PerformancePolicy:
    schema: str = "ronin.performance-policy/v1"
    skew_ratio: float = 1.75
    min_skew_task_ms: float = 1000.0
    shuffle_bytes_per_second: float = 10_000_000.0
    small_file_count: int = 100
    small_file_average_bytes: int = 128 * 1024 * 1024
    gc_ratio: float = 0.20
    min_tasks_per_stage: int = 2

    def __post_init__(self) -> None:
        if self.schema != "ronin.performance-policy/v1":
            raise ValueError("unsupported performance policy schema")
        if (
            self.skew_ratio <= 1
            or self.min_skew_task_ms < 0
            or self.shuffle_bytes_per_second <= 0
            or self.small_file_count < 1
            or self.small_file_average_bytes < 1
            or not 0 < self.gc_ratio < 1
            or self.min_tasks_per_stage < 1
        ):
            raise ValueError("performance policy thresholds are invalid")

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> PerformancePolicy:
        return (
            cls(**{key: value[key] for key in cls.__dataclass_fields__ if value and key in value})
            if value
            else cls()
        )

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)
