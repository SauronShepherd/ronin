"""Optimization contract tests."""
# ruff: noqa: E501

import pytest
from studio_ml.optimization import (
    BayesianStopPolicy,
    SearchSpec,
    Trial,
    expected_improvement,
    propose_bayesian_candidates,
    rank_trials,
)


def test_grid_trials_and_ids_are_deterministic() -> None:
    spec = SearchSpec(mode="grid", parameters=(("C", (0.1, 1.0)), ("max_iter", (100, 200))))
    trials = tuple(
        Trial.create(params, {"score": float(index)}) for index, params in enumerate(spec.trials())
    )
    assert len(trials) == 4
    assert trials[0].trial_id == Trial.create(spec.trials()[0], {"score": 0}).trial_id
    assert rank_trials(spec, trials)[0].metric("score") == 3.0


def test_search_spec_rejects_duplicate_parameters() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        SearchSpec(parameters=(("C", (1,)), ("C", (2,))))


def test_random_trials_are_reproducible_and_bounded() -> None:
    spec = SearchSpec(
        mode="random",
        random_seed=5,
        max_trials=2,
        parameters=(("C", (0.1, 1.0, 10.0)), ("max_iter", (100, 200))),
    )
    assert (
        spec.trials()
        == SearchSpec(
            mode="random",
            random_seed=5,
            max_trials=2,
            parameters=(("C", (0.1, 1.0, 10.0)), ("max_iter", (100, 200))),
        ).trials()
    )
    assert len(spec.trials()) == 2


def test_large_grid_search_is_lazy_and_stops_at_trial_budget() -> None:
    values = tuple(range(1000))
    spec = SearchSpec(
        mode="grid",
        max_trials=4,
        parameters=(("a", values), ("b", values), ("c", values)),
    )
    assert spec.trials() == (
        {"a": 0, "b": 0, "c": 0},
        {"a": 0, "b": 0, "c": 1},
        {"a": 0, "b": 0, "c": 2},
        {"a": 0, "b": 0, "c": 3},
    )


def test_large_random_search_samples_without_materializing_the_product() -> None:
    values = tuple(range(1000))
    spec = SearchSpec(
        mode="random",
        max_trials=8,
        random_seed=5,
        parameters=(("a", values), ("b", values), ("c", values)),
    )
    trials = spec.trials()
    assert len(trials) == 8
    assert len({tuple(sorted(trial.items())) for trial in trials}) == 8
    assert trials == spec.trials()


def test_search_trial_budget_has_a_fixed_upper_bound() -> None:
    with pytest.raises(ValueError, match="search limits"):
        SearchSpec(max_trials=1001)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_trials": True},
        {"random_seed": True},
        {"metric": 1},
        {"direction": []},
        {"parameters": (("C", [1, 2]),)},
    ],
)
def test_search_spec_rejects_wrong_runtime_types(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="search|objective|random seed"):
        SearchSpec(**kwargs)  # type: ignore[arg-type]


def test_bayesian_mode_is_bounded_and_reproducible() -> None:
    spec = SearchSpec(
        mode="bayesian",
        random_seed=41,
        max_trials=3,
        parameters=(("C", (0.1, 1.0, 10.0)), ("max_iter", (100, 300))),
    )
    assert len(spec.trials()) == 3
    assert spec.trials() == spec.trials()


def test_bayesian_candidates_use_observations_without_repeating_them() -> None:
    spec = SearchSpec(
        mode="bayesian",
        max_trials=2,
        random_seed=3,
        parameters=(("C", (0.1, 1.0, 10.0)), ("max_iter", (100, 300))),
    )
    observations = (Trial.create({"C": 1.0, "max_iter": 100}, {"score": 0.95}),)
    proposals = propose_bayesian_candidates(spec, observations)
    assert len(proposals) == 2
    assert {tuple(sorted(item.items())) for item in proposals}.isdisjoint(
        {tuple(sorted(observations[0].parameters))}
    )
    assert proposals == propose_bayesian_candidates(spec, observations)


def test_bayesian_candidate_pool_is_bounded_for_a_large_search_space() -> None:
    values = tuple(range(1000))
    spec = SearchSpec(
        mode="bayesian",
        max_trials=3,
        random_seed=19,
        parameters=(("a", values), ("b", values), ("c", values)),
    )
    observations = (Trial.create({"a": 0, "b": 0, "c": 0}, {"score": 1.0}),)
    proposals = propose_bayesian_candidates(spec, observations)
    assert 0 < len(proposals) <= 3
    assert {tuple(sorted(item.items())) for item in proposals}.isdisjoint(
        {tuple(sorted(observations[0].parameters))}
    )
    assert proposals == propose_bayesian_candidates(spec, observations)


def test_bayesian_stop_policy_honors_budget_and_patience() -> None:
    spec = SearchSpec(mode="bayesian", metric="score", max_trials=10)
    policy = BayesianStopPolicy(max_trials=10, patience=2, min_improvement=0.1)
    trials = tuple(
        Trial.create({"x": value}, {"score": score})
        for value, score in ((1, 0.5), (2, 0.51), (3, 0.52))
    )
    assert policy.should_stop(spec, trials)
    assert BayesianStopPolicy(max_trials=2).should_stop(spec, trials)


def test_expected_improvement_is_zero_at_observed_best_and_positive_for_uncertainty() -> None:
    spec = SearchSpec(mode="bayesian", metric="score", parameters=(("x", (0, 1, 2)),))
    observations = (Trial.create({"x": 0}, {"score": 1.0}), Trial.create({"x": 1}, {"score": 0.5}))
    assert expected_improvement(spec, {"x": 0}, observations) == 0.0
    assert expected_improvement(spec, {"x": 2}, observations) > 0.0
