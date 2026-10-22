"""Dependency-free, deterministic K-Means primitives for ML Studio."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("clustering feature values must be numeric")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("clustering feature values must be finite") from exc
    if not isfinite(number):
        raise ValueError("clustering feature values must be finite")
    return number


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


def calinski_harabasz(
    model: KMeansModel, rows: Sequence[Mapping[str, object]], features: tuple[str, ...]
) -> float:
    """Return the deterministic Calinski-Harabasz clustering score."""

    if len(rows) <= len(model.centroids):
        raise ValueError("Calinski-Harabasz requires more rows than clusters")
    matrix = [[_number(row[name]) for name in features] for row in rows]
    assignments = model.predict(rows, features)
    global_mean = tuple(
        sum(vector[column] for vector in matrix) / len(matrix) for column in range(len(features))
    )
    counts = [0] * len(model.centroids)
    within = 0.0
    for vector, cluster in zip(matrix, assignments, strict=True):
        counts[cluster] += 1
        within += _distance(vector, model.centroids[cluster])
    between = sum(
        count * _distance(centroid, global_mean)
        for count, centroid in zip(counts, model.centroids, strict=True)
    )
    if within == 0.0:
        return 1e300 if between > 0.0 else 0.0
    return (between / (len(model.centroids) - 1)) / (within / (len(rows) - len(model.centroids)))


__all__ = ["KMeansModel", "calinski_harabasz", "fit_kmeans", "inertia"]
