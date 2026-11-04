from pathlib import Path

import pytest

from tools.openapi_snapshot import check


def test_public_openapi_snapshot_is_current() -> None:
    root = Path(__file__).parents[1]
    assert len(check(root / "api/openapi-v1.json", root / "api/openapi-v1.sha256")) == 64


def test_ml_evaluation_review_contract_exposes_promotion_gate_and_card_evidence() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    route = document["paths"]["/v1/ml-studio/models/{model_id}/{version}/evaluations"]["post"]
    request = document["components"]["schemas"]["MLModelEvaluationReviewRequest"]
    card = document["components"]["schemas"]["MLModelCard"]

    assert route["operationId"] == "recordMlStudioModelEvaluation"
    assert route["requestBody"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/MLModelEvaluationReviewRequest"
    )
    assert "409" in route["responses"]
    assert request["required"] == ["status", "review_ref"]
    assert request["properties"]["status"]["enum"] == ["passed", "failed", "unknown"]
    assert "evaluations" in card["required"]
    assert card["properties"]["evaluations"]["items"]["$ref"] == (
        "#/components/schemas/MLModelEvaluation"
    )
    assert card["properties"]["evaluations"]["maxItems"] == 100


def test_catalog_lineage_openapi_documents_direction_and_fail_closed_limit() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    operation = document["paths"][
        "/v1/workspaces/{workspace_id}/catalog/lineage/{asset_id}/{version}"
    ]["get"]
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert parameters["direction"]["schema"]["enum"] == ["upstream", "downstream"]
    assert parameters["limit"]["schema"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 100,
        "default": 100,
    }
    assert "413" in operation["responses"]


def test_semantic_dashboard_execution_documents_global_fanout_time_and_byte_budgets() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    operation = document["paths"][
        "/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/dashboards/{dashboard_id}/execute"
    ]["post"]
    description = operation["description"]
    assert "12 tiles" in description
    assert "100000 requested rows" in description
    assert "8 MiB response" in description
    assert "15000 ms total SQL execution time" in description
    assert "without returning partial results" in description
    assert {"400", "408", "413"}.issubset(operation["responses"])


def test_queryflux_execution_route_and_result_budgets_are_documented() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    operation = document["paths"][
        "/v1/workspaces/{workspace_id}/projects/{project_id}/data-engineering/queryflux/execute"
    ]["post"]
    request = document["components"]["schemas"]["QueryFluxExecuteRequest"]

    assert operation["operationId"] == "executeQueryFlux"
    assert operation["description"].find("data-engineering:execute") >= 0
    assert [item["name"] for item in operation["parameters"]] == [
        "workspace_id",
        "project_id",
    ]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/QueryFluxExecuteRequest"
    )
    assert request["properties"]["max_result_bytes"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 10485760,
        "default": 1048576,
    }
    assert request["properties"]["max_rows"]["maximum"] == 1000000
    assert "project_id" not in request["properties"]
    sql_request = document["components"]["schemas"]["SqlRequest"]
    capability_schema = document["components"]["schemas"]["QueryFluxCapabilities"]
    capability_operation = document["paths"]["/v1/data-engineering/queryflux/capabilities"]["get"]
    assert capability_operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ] == ("#/components/schemas/QueryFluxCapabilities")
    assert capability_schema["properties"]["allowed_engines"]["type"] == "array"
    assert capability_schema["properties"]["capabilities"]["additionalProperties"]["type"] == [
        "boolean",
        "null",
    ]
    assert request["properties"]["profile"]["const"] == "queryflux"
    assert sql_request["properties"]["timeout_ms"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 60000,
        "default": 5000,
    }
    assert sql_request["properties"]["max_result_bytes"]["maximum"] == 10485760
    assert sql_request["properties"]["profile"]["enum"] == ["local"]
    sql_operation = document["paths"]["/v1/sql"]["post"]
    assert "413" in sql_operation["responses"]
    sql_result = document["components"]["schemas"]["SqlResult"]
    assert sql_result["additionalProperties"] is False
    assert sql_result["properties"]["query_evidence"]["$ref"] == (
        "#/components/schemas/SqlQueryEvidence"
    )
    assert "routing_trace" in document["components"]["schemas"]["SqlQueryEvidence"]["required"]
    project_sql = document["paths"][
        "/v1/workspaces/{workspace_id}/projects/{project_id}/sql/query"
    ]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert project_sql["additionalProperties"] is False
    explain_sql = document["paths"][
        "/v1/workspaces/{workspace_id}/projects/{project_id}/sql/explain"
    ]["post"]
    assert explain_sql["operationId"] == "explainProjectSql"
    assert explain_sql["x-ronin-required-project-actions"] == ["read"]
    explain_request = explain_sql["requestBody"]["content"]["application/json"]["schema"]
    assert explain_request["additionalProperties"] is False
    assert explain_request["properties"]["max_bytes"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 1048576,
        "default": 262144,
    }
    assert explain_request["properties"]["timeout_ms"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 60000,
        "default": 5000,
    }
    assert "501" in explain_sql["responses"]


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
    builtin_v3_nodes = [node for node in v3_node_variants if "const" in node["properties"]["kind"]]
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


def test_stream_micro_batch_openapi_is_bounded_and_write_scoped() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    operation = document["paths"]["/v1/workspaces/{workspace_id}/streams/{stream_id}/run"]["post"]
    request = operation["requestBody"]["content"]["application/json"]["schema"]

    assert operation["operationId"] == "runStreamingMicroBatch"
    assert request["additionalProperties"] is False
    assert request["properties"]["limit"]["maximum"] == 100000
    assert request["properties"]["timeout_seconds"]["maximum"] == 300
    assert {"200", "400", "401", "403", "404", "422", "503"} <= set(operation["responses"])


def test_stream_lifecycle_openapi_documents_explicit_checkpoint_policy() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    list_operation = document["paths"]["/v1/workspaces/{workspace_id}/streams"]["get"]
    put_operation = document["paths"]["/v1/workspaces/{workspace_id}/streams/{stream_id}"]["put"]
    definition = document["components"]["schemas"]["StreamDefinition"]
    request = put_operation["requestBody"]["content"]["application/json"]["schema"]

    assert list_operation["operationId"] == "listStreamingDefinitions"
    assert put_operation["operationId"] == "putStreamingDefinition"
    assert request["additionalProperties"] is False
    assert request["properties"]["checkpoint_policy"]["enum"] == ["reset", "resume"]
    assert definition["properties"]["runtime"]["properties"]["batch_limit"]["maximum"] == 100000
    assert definition["properties"]["sink"]["properties"]["kind"]["enum"] == [
        "parquet",
        "table",
    ]
    assert "409" in put_operation["responses"]


def test_stream_bundle_openapi_requires_reviewed_digest_bindings_and_offset_policy() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    paths = document["paths"]
    export = paths["/v1/workspaces/{workspace_id}/streams/bundle"]["get"]
    plan = paths["/v1/workspaces/{workspace_id}/streams/bundle/plan"]["post"]
    imported = paths["/v1/workspaces/{workspace_id}/streams/bundle/import"]["post"]

    assert export["operationId"] == "exportStreamingBundle"
    assert export["responses"]["200"]["description"].endswith("700 KiB")
    assert plan["operationId"] == "planStreamingBundleImport"
    assert set(plan["requestBody"]["content"]["application/json"]["schema"]["required"]) == {
        "content_base64"
    }
    schema = imported["requestBody"]["content"]["application/json"]["schema"]
    assert set(schema["required"]) == {
        "content_base64",
        "binding_remaps",
        "checkpoint_policies",
        "expected_digest",
    }
    assert schema["properties"]["expected_digest"]["pattern"] == "^[0-9a-f]{64}$"
    assert schema["properties"]["checkpoint_policies"]["additionalProperties"]["enum"] == [
        "reset",
        "resume",
    ]
    assert "409" in imported["responses"]


def test_semantic_bundle_openapi_requires_reviewed_digest_and_project_scopes() -> None:
    import json

    root = Path(__file__).parents[1]
    document = json.loads((root / "api/openapi-v1.json").read_text(encoding="utf-8"))
    paths = document["paths"]
    export = paths["/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/bundle"]["get"]
    plan = paths["/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/bundle/plan"]["post"]
    imported = paths["/v1/workspaces/{workspace_id}/projects/{project_id}/semantic/bundle/import"][
        "post"
    ]

    assert export["operationId"] == "exportSemanticBundle"
    assert (
        export["responses"]["200"]["content"]["application/json"]["schema"]["properties"][
            "size_bytes"
        ]["maximum"]
        == 700 * 1024
    )
    assert plan["operationId"] == "planSemanticBundleImport"
    assert plan["x-ronin-required-project-actions"] == ["read"]
    assert set(plan["requestBody"]["content"]["application/json"]["schema"]["required"]) == {
        "content_base64"
    }
    assert imported["operationId"] == "importSemanticBundle"
    schema = imported["requestBody"]["content"]["application/json"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"content_base64", "expected_digest"}
    assert schema["properties"]["expected_digest"]["pattern"] == "^[0-9a-f]{64}$"
    assert imported["x-ronin-required-project-actions"] == ["write"]
    assert "409" in imported["responses"]
