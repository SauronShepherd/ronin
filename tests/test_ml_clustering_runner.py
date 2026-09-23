from studio_core.catalog import AssetRef, AssetVersion
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.runner import LocalExperimentRunner


def test_runner_executes_clustering_lab() -> None:
    lab = Lab(
        id="clusters",
        name="Clusters",
        project_id="project",
        dataset=AssetRef("asset", AssetVersion("v1")),
        target=None,
        task="clustering",
        features=(FeatureSpec("x"),),
    )
    model = LocalExperimentRunner().run_clustering(
        lab, [{"x": value} for value in (0.0, 0.1, 9.9, 10.0)], clusters=2
    )
    assert model.to_artifact()["schema"] == "ronin.ml-kmeans/v1"


def test_runner_returns_a_content_addressed_clustering_result() -> None:
    lab = Lab(
        id="clusters",
        name="Clusters",
        project_id="project",
        dataset=AssetRef("asset", AssetVersion("v1")),
        target=None,
        task="clustering",
        features=(FeatureSpec("x"),),
    )
    result = LocalExperimentRunner().run_clustering_result(
        lab, [{"x": value} for value in (0.0, 0.1, 9.9, 10.0)], clusters=2
    )
    payload = result.to_payload()
    assert payload["task"] == "clustering"
    assert payload["algorithm"] == "kmeans"
    assert str(payload["artifact_digest"]).startswith("sha256:")
    assert float(payload["inertia"]) >= 0
