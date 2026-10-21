from pathlib import Path

import pytest

from tools.openapi_snapshot import check


def test_public_openapi_snapshot_is_current() -> None:
    root = Path(__file__).parents[1]
    assert len(check(root / "api/openapi-v1.json", root / "api/openapi-v1.sha256")) == 64


def test_ml_lab_openapi_schema_matches_v1_contract() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    lab = document["components"]["schemas"]["MLLab"]
    assert lab["properties"]["task"]["enum"] == [
        "classification",
        "regression",
        "clustering",
    ]
    assert lab["properties"]["target"]["type"] == ["string", "null"]
    assert lab["properties"]["test_fraction"]["exclusiveMaximum"] == 1
    assert lab["additionalProperties"] is True
    post = document["paths"]["/v1/ml-studio/labs"]["post"]
    assert (
        post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/MLLab"
    )


def test_ml_execution_openapi_requires_workspace_scope_and_idempotent_shape() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    get_operation = document["paths"]["/v1/ml-studio/executions/{run_id}"]["get"]
    cancel_operation = document["paths"]["/v1/ml-studio/executions/{run_id}/cancel"]["post"]
    retry_operation = document["paths"]["/v1/ml-studio/executions/{run_id}/retry"]["post"]
    for operation in (get_operation, cancel_operation, retry_operation):
        workspace = next(
            parameter
            for parameter in operation["parameters"]
            if parameter["name"] == "workspace_id"
        )
        assert workspace["in"] == "query"
        assert workspace["required"] is True
        assert workspace["schema"]["minLength"] == 1
    retry_schema = retry_operation["requestBody"]["content"]["application/json"]["schema"]
    assert retry_schema["additionalProperties"] is False
    assert retry_schema["required"] == ["run_id", "from_stage"]
    assert retry_schema["properties"]["from_stage"]["enum"] == [
        "profile",
        "quality_gate",
        "prepare",
        "train",
        "evaluate",
        "select",
    ]
    submit = document["paths"]["/v1/ml-studio/labs/{lab_id}/executions"]["post"]
    request_schema = submit["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["additionalProperties"] is False
    assert "required" not in request_schema
    assert request_schema["properties"]["run_id"]["minLength"] == 1
    assert request_schema["properties"]["rows"]["type"] == "array"
    assert request_schema["properties"]["algorithm"]["enum"] == [
        "logistic_regression",
        "linear_regression",
        "decision_tree_classifier",
        "decision_tree_regressor",
        "random_forest_classifier",
        "random_forest_regressor",
        "gradient_boosting_classifier",
        "gradient_boosting_regressor",
    ]
    assert request_schema["properties"]["preprocessor"]["enum"] == [
        "identity",
        "standard_scale",
        "one_hot",
        "median_impute",
        "one_hot_median_impute",
    ]
    assert request_schema["properties"]["candidate_algorithms"]["minItems"] == 2
    assert request_schema["properties"]["candidate_algorithms"]["maxItems"] == 8
    assert request_schema["properties"]["selection_direction"]["enum"] == [
        "maximize",
        "minimize",
    ]
    assert "409" in submit["responses"]
    quality = document["paths"]["/v1/ml-studio/labs/{lab_id}/quality"]["post"]
    quality_schema = quality["requestBody"]["content"]["application/json"]["schema"]
    assert "required" not in quality_schema
    assert quality_schema["properties"]["rows"]["type"] == "array"


def test_openapi_snapshot_rejects_drift(tmp_path: Path) -> None:
    document = tmp_path / "openapi.json"
    snapshot = tmp_path / "openapi.sha256"
    document.write_text('{"openapi":"3.1.0"}', encoding="utf-8")
    snapshot.write_text("0" * 64, encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        check(document, snapshot)
