from studio_ml.optimization import SearchSpec, Trial, propose_bayesian_candidates


def test_bayesian_proposals_are_consumable_as_sequential_search_rounds() -> None:
    spec = SearchSpec(
        mode="bayesian", metric="accuracy", max_trials=3, random_seed=7,
        parameters=(("C", (0.1, 1.0, 10.0)),),
    )
    seen: list[dict[str, object]] = [spec.trials()[0]]
    observations = [Trial.create(seen[0], {"accuracy": 0.5})]
    while len(seen) < spec.max_trials:
        candidates = propose_bayesian_candidates(spec, tuple(observations))
        assert candidates
        candidate = candidates[0]
        seen.append(candidate)
        observations.append(Trial.create(candidate, {"accuracy": 0.5 + len(seen) / 10}))
    assert len({tuple(sorted(item.items())) for item in seen}) == 3
