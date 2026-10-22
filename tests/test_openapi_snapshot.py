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
    backends = document["paths"]["/v1/ml-studio/backends"]["get"]
    backend_schema = document["components"]["schemas"]["MLBackend"]
    assert backends["operationId"] == "listMlStudioBackends"
    assert backend_schema["properties"]["status"]["enum"] == ["available", "unavailable"]
    assert backend_schema["properties"]["install_extra"]["type"] == "string"
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
    assert retry_schema["properties"]["from_stage"]["maxLength"] == 261
    stage_schema = document["components"]["schemas"]["MLExecutionSnapshot"]["properties"][
        "pipeline_stages"
    ]
    assert stage_schema["type"] == "array"
    assert stage_schema["items"]["required"] == ["id", "kind"]
    assert stage_schema["items"]["properties"]["id"]["maxLength"] == 256
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
    assert request_schema["properties"]["candidate_cluster_counts"]["minItems"] == 2
    assert request_schema["properties"]["candidate_cluster_counts"]["maxItems"] == 8
    assert request_schema["properties"]["candidate_cluster_counts"]["items"]["maximum"] == 32
    assert request_schema["properties"]["candidate_preprocessors"]["minItems"] == 2
    assert request_schema["properties"]["candidate_preprocessors"]["maxItems"] == 5
    assert request_schema["properties"]["candidate_preprocessors"]["uniqueItems"] is True
    assert request_schema["properties"]["candidate_preprocessors"]["items"]["enum"] == [
        "identity",
        "standard_scale",
        "one_hot",
        "median_impute",
        "one_hot_median_impute",
    ]
    assert "calinski_harabasz" in request_schema["properties"]["selection_metric"]["enum"]
    assert request_schema["properties"]["selection_direction"]["enum"] == [
        "maximize",
        "minimize",
    ]
    assert request_schema["properties"]["register"]["required"] == ["model_id", "version"]
    pipeline_variants = request_schema["properties"]["pipeline"]["oneOf"]
    pipeline_schema = pipeline_variants[0]
    assert pipeline_schema["properties"]["schema"]["const"] == "ronin.ml-pipeline-ir/v2"
    assert pipeline_schema["properties"]["nodes"]["maxItems"] == 24
    assert (
        "one_hot_median_impute"
        in pipeline_schema["properties"]["nodes"]["items"]["properties"]["config"]["properties"][
            "preprocessor"
        ]["enum"]
    )
    assert (
        "register" in pipeline_schema["properties"]["nodes"]["items"]["properties"]["kind"]["enum"]
    )
    v3_schema = pipeline_variants[1]
    assert v3_schema["properties"]["schema"]["const"] == "ronin.ml-pipeline-ir/v3"
    assert v3_schema["properties"]["nodes"]["maxItems"] == 24
    v3_node_variants = v3_schema["properties"]["nodes"]["items"]["oneOf"]
    builtin_v3_nodes = [
        node for node in v3_node_variants if "const" in node["properties"]["kind"]
    ]
    v3_kinds = {node["properties"]["kind"]["const"] for node in builtin_v3_nodes}
    assert v3_kinds == {
        "profile",
        "quality_gate",
        "prepare",
        "train",
        "evaluate",
        "select",
        "register",
    }
    select_variant = next(
        node for node in builtin_v3_nodes if node["properties"]["kind"]["const"] == "select"
    )
    assert select_variant["properties"]["inputs"]["properties"]["candidates"]["maxItems"] == 23
    plugin_variant = next(
        node for node in v3_node_variants if "pattern" in node["properties"]["kind"]
    )
    assert plugin_variant["properties"]["stage_version"]["minimum"] == 1
    assert plugin_variant["properties"]["config"]["maxProperties"] == 32
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
