"""Dependency-free, deterministic K-Means primitives for ML Studio."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("clustering feature values must be numeric")
    return float(value)


@dataclass(frozen=True, slots=True)
class KMeansModel:
    centroids: tuple[tuple[float, ...], ...]
    iterations: int

    def predict(
        self, rows: Sequence[Mapping[str, object]], features: tuple[str, ...]
    ) -> tuple[int, ...]:
        matrix = [[_number(row[name]) for name in features] for row in rows]
        return tuple(_nearest(vector, self.centroids) for vector in matrix)

    def to_artifact(self) -> dict[str, object]:
        return {
            "schema": "ronin.ml-kmeans/v1",
            "algorithm": "kmeans",
            "centroids": [list(item) for item in self.centroids],
            "iterations": self.iterations,
        }


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def _nearest(vector: Sequence[float], centroids: Sequence[Sequence[float]]) -> int:
    return min(
        range(len(centroids)), key=lambda index: (_distance(vector, centroids[index]), index)
    )


def fit_kmeans(
    rows: Sequence[Mapping[str, object]],
    features: tuple[str, ...],
    clusters: int,
    *,
    max_iterations: int = 100,
) -> KMeansModel:
    if clusters < 2 or clusters > len(rows):
        raise ValueError("K-Means clusters must be between 2 and row count")
    if not features:
        raise ValueError("K-Means requires at least one feature")
    matrix = [[_number(row[name]) for name in features] for row in rows]
    centroids = [tuple(vector) for vector in matrix[:clusters]]
    for iteration in range(1, max_iterations + 1):
        assignments = [_nearest(vector, centroids) for vector in matrix]
        updated: list[tuple[float, ...]] = []
        for cluster in range(clusters):
            members = [matrix[index] for index, value in enumerate(assignments) if value == cluster]
            updated.append(
                tuple(
                    sum(vector[column] for vector in members) / len(members)
                    for column in range(len(features))
                )
                if members
                else centroids[cluster]
            )
        if updated == centroids:
            return KMeansModel(tuple(updated), iteration)
        centroids = updated
    return KMeansModel(tuple(centroids), max_iterations)


def inertia(
    model: KMeansModel, rows: Sequence[Mapping[str, object]], features: tuple[str, ...]
) -> float:
    return sum(
        _distance([_number(row[name]) for name in features], model.centroids[cluster])
        for row, cluster in zip(rows, model.predict(rows, features), strict=True)
    )


__all__ = ["KMeansModel", "fit_kmeans", "inertia"]
