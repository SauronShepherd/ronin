"""Backend-neutral deterministic trial search and comparison primitives."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from itertools import islice, product
from math import erf, exp, isfinite, pi, prod, sqrt
from typing import Literal

SearchMode = Literal["single", "grid", "random", "bayesian"]
MAX_TIE_BREAKERS = 8


@dataclass(frozen=True, slots=True)
class BayesianStopPolicy:
    max_trials: int = 100
    patience: int = 10
    min_improvement: float = 0.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_trials, int)
            or isinstance(self.max_trials, bool)
            or self.max_trials < 1
            or not isinstance(self.patience, int)
            or isinstance(self.patience, bool)
            or self.patience < 1
            or isinstance(self.min_improvement, bool)
            or not isinstance(self.min_improvement, (int, float))
            or not isfinite(self.min_improvement)
            or self.min_improvement < 0
        ):
            raise ValueError("invalid Bayesian stopping policy")

    def should_stop(self, spec: SearchSpec, trials: tuple[Trial, ...]) -> bool:
        if len(trials) >= min(self.max_trials, spec.max_trials):
            return True
        if len(trials) < self.patience + 1:
            return False
        previous_trials = trials[: -self.patience]
        best = rank_trials(spec, trials)[0].metric(spec.metric)
        prior = rank_trials(spec, previous_trials)[0].metric(spec.metric)
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
    tie_breakers: tuple[tuple[str, Literal["maximize", "minimize"]], ...] = ()
    max_trials: int = 100
    random_seed: int = 17

    def __post_init__(self) -> None:
        if not isinstance(self.mode, str) or self.mode not in {
            "single",
            "grid",
            "random",
            "bayesian",
        }:
            raise ValueError("unsupported search mode")
        if (
            not isinstance(self.direction, str)
            or self.direction not in {"maximize", "minimize"}
            or not isinstance(self.metric, str)
            or not self.metric.strip()
            or not isinstance(self.tie_breakers, tuple)
            or len(self.tie_breakers) > MAX_TIE_BREAKERS
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0].strip()
                or not isinstance(item[1], str)
                or item[1] not in {"maximize", "minimize"}
                for item in self.tie_breakers
            )
            or self.metric in {name for name, _ in self.tie_breakers}
            or len({name for name, _ in self.tie_breakers}) != len(self.tie_breakers)
        ):
            raise ValueError("invalid search objective")
        if (
            not isinstance(self.max_trials, int)
            or isinstance(self.max_trials, bool)
            or not 1 <= self.max_trials <= 1000
            or not isinstance(self.parameters, tuple)
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0].strip()
                or not isinstance(item[1], tuple)
                or not item[1]
                for item in self.parameters
            )
            or len({name for name, _ in self.parameters}) != len(self.parameters)
        ):
            raise ValueError("invalid search limits or duplicate parameter")
        if (
            not isinstance(self.random_seed, int)
            or isinstance(self.random_seed, bool)
            or self.random_seed < 0
        ):
            raise ValueError("random seed must be non-negative")

    def trials(self) -> tuple[dict[str, object], ...]:
        if self.mode == "single":
            return ({name: values[0] for name, values in self.parameters},)
        names = tuple(name for name, _ in self.parameters)
        dimensions = tuple(values for _, values in self.parameters)
        total = prod(len(values) for values in dimensions)
        if self.mode == "grid":
            combinations = islice(product(*dimensions), self.max_trials)
            return tuple(dict(zip(names, combination, strict=True)) for combination in combinations)

        count = min(total, self.max_trials)
        rng = random.Random(self.random_seed)  # noqa: S311
        indices: set[int] = set()
        while len(indices) < count:
            indices.add(rng.randrange(total))
        trials: list[dict[str, object]] = []
        for index in sorted(indices):
            positions: list[int] = []
            for dimension in reversed(dimensions):
                index, position = divmod(index, len(dimension))
                positions.append(position)
            positions.reverse()
            trials.append(
                {
                    name: choices[choice]
                    for name, choices, choice in zip(names, dimensions, positions, strict=True)
                }
            )
        rng.shuffle(trials)
        return tuple(trials)


@dataclass(frozen=True, slots=True)
class Trial:
    trial_id: str
    parameters: tuple[tuple[str, object], ...]
    metrics: tuple[tuple[str, float], ...]

    @classmethod
    def create(
        cls,
        parameters: dict[str, object],
        metrics: dict[str, float],
        *,
        random_seed: int = 17,
    ) -> Trial:
        if not isinstance(random_seed, int) or isinstance(random_seed, bool) or random_seed < 0:
            raise ValueError("trial random seed must be a non-negative integer")
        normalized_metrics: dict[str, float] = {}
        for name, raw_value in metrics.items():
            if not isinstance(name, str) or not name or name != name.strip():
                raise ValueError("trial metric names must be non-empty and trimmed")
            value = _finite_metric(raw_value)
            if value is None:
                raise ValueError(f"trial metric {name!r} must be a finite number")
            normalized_metrics[name] = value
        encoded = json.dumps(
            {"parameters": parameters, "random_seed": random_seed},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
        return cls(
            f"trial-{digest}",
            tuple(sorted(parameters.items())),
            tuple(sorted(normalized_metrics.items())),
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


def _finite_metric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        normalized = float(value)
    except OverflowError:
        return None
    return normalized if isfinite(normalized) else None


def derive_trial_seed(random_seed: int, trial_id: str) -> int:
    """Derive a stable scikit-learn-compatible seed for one search trial."""
    if (
        not isinstance(random_seed, int)
        or isinstance(random_seed, bool)
        or random_seed < 0
        or not isinstance(trial_id, str)
        or not trial_id
    ):
        raise ValueError("trial seed requires a non-negative seed and trial id")
    encoded = f"ronin-ml-trial-seed-v1:{random_seed}:{trial_id}"
    return int.from_bytes(hashlib.sha256(encoded.encode("utf-8")).digest()[:4], "big")


def rank_trials(spec: SearchSpec, trials: tuple[Trial, ...]) -> tuple[Trial, ...]:
    """Rank by the primary metric, configured tie-breakers, then stable ID."""
    metric_names = (spec.metric, *(name for name, _ in spec.tie_breakers))
    for trial in trials:
        for name in metric_names:
            try:
                value = trial.metric(name)
            except KeyError as exc:
                raise ValueError(f"trial is missing ranking metric {name!r}") from exc
            if _finite_metric(value) is None:
                raise ValueError(f"trial ranking metric {name!r} must be finite")

    ranked = sorted(trials, key=lambda trial: trial.trial_id)
    for name, direction in reversed(spec.tie_breakers):
        ranked.sort(key=lambda trial: trial.metric(name), reverse=direction == "maximize")
    ranked.sort(key=lambda trial: trial.metric(spec.metric), reverse=spec.direction == "maximize")
    return tuple(ranked)


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
    pool_size = min(max(spec.max_trials * 10, 100), 1000)
    candidates = list(
        SearchSpec(
            mode="random",
            parameters=spec.parameters,
            max_trials=pool_size,
            metric=spec.metric,
            direction=spec.direction,
            random_seed=spec.random_seed,
        ).trials()
    )
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
