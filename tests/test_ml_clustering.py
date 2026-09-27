from studio_ml.clustering import fit_kmeans, inertia


def test_kmeans_is_deterministic_and_emits_declarative_artifact() -> None:
    rows = [{"x": value} for value in (0.0, 0.2, 9.8, 10.0)]
    model = fit_kmeans(rows, ("x",), 2)
    assert model == fit_kmeans(rows, ("x",), 2)
    assert model.to_artifact()["schema"] == "ronin.ml-kmeans/v1"
    assert len(set(model.predict(rows, ("x",)))) == 2
    assert inertia(model, rows, ("x",)) < 1.0
