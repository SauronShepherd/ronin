"""Backend-neutral deterministic trial search and comparison primitives."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from itertools import product
from math import erf, exp, pi, sqrt
from typing import Literal

SearchMode = Literal["single", "grid", "random", "bayesian"]


@dataclass(frozen=True, slots=True)
class BayesianStopPolicy:
    max_trials: int = 100
    patience: int = 10
    min_improvement: float = 0.0

    def __post_init__(self) -> None:
        if self.max_trials < 1 or self.patience < 1 or self.min_improvement < 0:
            raise ValueError("invalid Bayesian stopping policy")

    def should_stop(self, spec: SearchSpec, trials: tuple[Trial, ...]) -> bool:
        if len(trials) >= min(self.max_trials, spec.max_trials):
            return True
        if len(trials) < self.patience + 1:
            return False
        ordered = rank_trials(spec, trials)
        best = ordered[0].metric(spec.metric)
        prior = ordered[self.patience].metric(spec.metric)
        return (
            (best - prior) < self.min_improvement
            if spec.direction == "maximize"
            else (prior - best) < self.min_improvement
        )


@dataclass(frozen=True, slots=True)
class SearchSpec:
    mode: SearchMode = "single"
    parameters: tuple[tuple[str, tuple[object, ...]], ...] = ()
    metric: str = "score"
    direction: Literal["maximize", "minimize"] = "maximize"
    max_trials: int = 100
    random_seed: int = 17

    def __post_init__(self) -> None:
        if self.mode not in {"single", "grid", "random", "bayesian"}:
            raise ValueError("unsupported search mode")
        if self.direction not in {"maximize", "minimize"} or not self.metric.strip():
            raise ValueError("invalid search objective")
        if self.max_trials < 1 or len({name for name, _ in self.parameters}) != len(
            self.parameters
        ):
            raise ValueError("invalid search limits or duplicate parameter")
        if any(not name.strip() or not values for name, values in self.parameters):
            raise ValueError("search parameters require a name and values")
        if self.random_seed < 0:
            raise ValueError("random seed must be non-negative")

    def trials(self) -> tuple[dict[str, object], ...]:
        if self.mode == "single":
            return ({name: values[0] for name, values in self.parameters},)
        names = tuple(name for name, _ in self.parameters)
        values = tuple(values for _, values in self.parameters)
        combinations = list(product(*values))
        if self.mode in {"random", "bayesian"}:
            random.Random(self.random_seed).shuffle(combinations)  # noqa: S311
        return tuple(
            dict(zip(names, combination, strict=True))
            for combination in combinations[: self.max_trials]
        )


@dataclass(frozen=True, slots=True)
class Trial:
    trial_id: str
    parameters: tuple[tuple[str, object], ...]
    metrics: tuple[tuple[str, float], ...]

    @classmethod
    def create(cls, parameters: dict[str, object], metrics: dict[str, float]) -> Trial:
        encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        return cls(
            f"trial-{digest}", tuple(sorted(parameters.items())), tuple(sorted(metrics.items()))
        )

    def metric(self, name: str) -> float:
        for metric_name, value in self.metrics:
            if metric_name == name:
                return value
        raise KeyError(name)

    def to_payload(self) -> dict[str, object]:
        return {
            "trial_id": self.trial_id,
            "parameters": dict(self.parameters),
            "metrics": dict(self.metrics),
        }


def rank_trials(spec: SearchSpec, trials: tuple[Trial, ...]) -> tuple[Trial, ...]:
    """Return deterministic ranking, using trial id as the tie-breaker."""
    return tuple(
        sorted(
            trials,
            key=lambda trial: (trial.metric(spec.metric), trial.trial_id),
            reverse=spec.direction == "maximize",
        )
    )


def propose_bayesian_candidates(
    spec: SearchSpec,
    observations: tuple[Trial, ...],
) -> tuple[dict[str, object], ...]:
    """Propose deterministic discrete candidates from observed trial outcomes.

    This is intentionally dependency-free: numeric dimensions are normalized,
    the nearest observed outcomes form a bounded inverse-distance surrogate,
    and a seeded jitter gives deterministic exploration. Categorical values are
    supported through their ordinal position. The function never repeats an
    observed parameter set.
    """
    if spec.mode != "bayesian":
        raise ValueError("bayesian candidate proposals require mode='bayesian'")
    candidates = [
        dict(item)
        for item in SearchSpec(
            mode="grid",
            parameters=spec.parameters,
            max_trials=spec.max_trials,
            metric=spec.metric,
            direction=spec.direction,
            random_seed=spec.random_seed,
        ).trials()
    ]
    observed = {tuple(sorted(trial.parameters)) for trial in observations}
    candidates = [item for item in candidates if tuple(sorted(item.items())) not in observed]
    if not candidates:
        return ()
    if not observations:
        random.Random(spec.random_seed).shuffle(candidates)  # noqa: S311
        return tuple(candidates[: spec.max_trials])

    best = rank_trials(spec, observations)[0]
    best_values = dict(best.parameters)
    rng = random.Random(spec.random_seed)  # noqa: S311

    def distance(candidate: dict[str, object], params: dict[str, object]) -> float:
        total = 0.0
        for name, values in spec.parameters:
            if len(values) <= 1:
                continue
            try:
                left = values.index(candidate[name])
                right = values.index(params[name])
            except ValueError:
                total += 1.0
            else:
                total += abs(left - right) / (len(values) - 1)
        return total / max(len(spec.parameters), 1)

    scored = []
    for candidate in candidates:
        exploitation = 1.0 - distance(candidate, best_values)
        exploration = min(
            (distance(candidate, dict(t.parameters)) for t in observations), default=1.0
        )
        scored.append((0.7 * exploitation + 0.3 * exploration + rng.random() * 1e-9, candidate))
    scored.sort(key=lambda item: (-item[0], json.dumps(item[1], sort_keys=True)))
    return tuple(candidate for _, candidate in scored[: spec.max_trials])


def expected_improvement(
    spec: SearchSpec,
    candidate: dict[str, object],
    observations: tuple[Trial, ...],
) -> float:
    """Return a dependency-free EI score for a discrete candidate.

    The surrogate uses inverse-distance weighting for the mean and distance
    from observed points for uncertainty. This is deliberately conservative:
    no value is extrapolated outside the configured parameter domain.
    """
    if spec.mode != "bayesian":
        raise ValueError("expected improvement requires mode='bayesian'")
    if not observations:
        return 1.0
    values = tuple(trial.metric(spec.metric) for trial in observations)
    best = max(values) if spec.direction == "maximize" else min(values)
    distances = []
    for trial in observations:
        distance = 0.0
        params = dict(trial.parameters)
        for name, choices in spec.parameters:
            if len(choices) > 1:
                distance += abs(choices.index(candidate[name]) - choices.index(params[name])) / (
                    len(choices) - 1
                )
        distances.append(distance / max(len(spec.parameters), 1))
    if min(distances) <= 1e-12:
        return 0.0
    weights = tuple(1.0 / max(distance, 1e-9) for distance in distances)
    mean = sum(weight * value for weight, value in zip(weights, values, strict=True)) / sum(weights)
    uncertainty = min(1.0, sum(distances) / max(len(distances), 1))
    improvement = (mean - best) if spec.direction == "maximize" else (best - mean)
    if uncertainty <= 1e-12:
        return max(0.0, improvement)
    z = improvement / uncertainty
    cdf = 0.5 * (1.0 + erf(z / sqrt(2.0)))
    pdf = exp(-0.5 * z * z) / sqrt(2.0 * pi)
    return max(0.0, improvement * cdf + uncertainty * pdf)


__all__ = [
    "BayesianStopPolicy",
    "SearchMode",
    "SearchSpec",
    "Trial",
    "expected_improvement",
    "propose_bayesian_candidates",
    "rank_trials",
]
