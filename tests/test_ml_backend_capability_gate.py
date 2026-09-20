from dataclasses import replace

import pytest
from studio_ml.backends import BackendCapabilities, LocalScikitLearnBackend
from studio_ml.domain import FeatureSpec, Lab
from studio_ml.runner import LocalExperimentRunner


def test_runner_rejects_task_not_advertised_by_backend() -> None:
    backend = LocalScikitLearnBackend()
    backend.capabilities = BackendCapabilities(
        tasks=("regression",), algorithms=("linear_regression",)
    )
    lab = Lab(
        id="lab-capability",
        project_id="project-capability",
        name="Capability gate",
        task="classification",
        features=(FeatureSpec("value"),),
        target="label",
        dataset="dataset://capability",
        backend_id=backend.backend_id,
    )
    with pytest.raises(ValueError, match="does not support task"):
        LocalExperimentRunner((backend,)).run(
            replace(lab),
            [{"value": 0, "label": "a"}, {"value": 1, "label": "b"}] * 4,
        )
