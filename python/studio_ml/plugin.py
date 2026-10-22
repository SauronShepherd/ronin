"""Machine Learning Studio vertical plugin boundary."""
# ruff: noqa: E501, E701

import base64
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Literal, cast
from urllib.parse import parse_qs, unquote

from studio_core import WorkspaceId
from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution
from studio_orchestrator import Instant
from studio_storage.ports import ArtifactReferenceBarrier, ArtifactStore

from .backends import default_backends
from .catalog import parse_catalog_version
from .datasets import DatasetResolver, resolve_lab_rows
from .domain import PIPELINE_SCHEMA_V2, PIPELINE_SCHEMA_V3, Lab, PipelineIR, PipelineNode
from .drift import DriftPolicy, assess_numeric_drift, compare_numeric_drift
from .optimization import (
    MAX_TIE_BREAKERS,
    BayesianStopPolicy,
    SearchSpec,
    Trial,
    derive_trial_seed,
    propose_bayesian_candidates,
    rank_trials,
)
from .orchestration import ExecutionSnapshot, JobStoreExecutionStore, LocalExecutionCoordinator
from .ports import MLLabStore
from .quality import QualitySuite, profile_and_validate, validate_quality_suite
from .runner import LocalExperimentRunner
from .runtime import TrainingSpec
from .service import (
    MLRegistryStore,
    deploy_registered_model,
    persist_clustering_result,
    persist_experiment_result,
    predict_registered_tabular,
    record_deployment_request,
    register_clustering_model,
    rollback_model_deployment,
    train_register_tabular,
)

from .services import InMemoryMLLabStore, LabService

MAX_PREDICTION_ROWS = 100_000
MAX_PREDICTION_ARTIFACT_BYTES = 64 * 1024 * 1024


def _plugin_now() -> Instant:
    """Return the canonical UTC instant expected by durable ML stores."""
    return Instant(datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"))


def _parse_tie_breakers(raw: object) -> tuple[tuple[str, Literal["maximize", "minimize"]], ...]:
    if not isinstance(raw, list):
        raise ValueError("spec tie_breakers must be an array")
    if len(raw) > MAX_TIE_BREAKERS:
        raise ValueError(f"spec tie_breakers must contain at most {MAX_TIE_BREAKERS} items")
    normalized: list[tuple[str, Literal["maximize", "minimize"]]] = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"metric", "direction"}
            or not isinstance(item.get("metric"), str)
            or not isinstance(item.get("direction"), str)
            or item["direction"] not in {"maximize", "minimize"}
        ):
            raise ValueError("invalid tie breaker")
        normalized.append(
            (item["metric"], cast(Literal["maximize", "minimize"], item["direction"]))
        )
    return tuple(normalized)


def _pipeline_with_quality_suite(
    pipeline: PipelineIR, suite: QualitySuite, stage_registry_digest: str
) -> PipelineIR:
    """Upgrade a compiled built-in graph to v3 and pin a reusable quality suite."""
    parameters = dict(pipeline.parameters)
    algorithm = parameters.pop("algorithm", None)
    preprocessor = parameters.pop("preprocessor", None)
    output_ports = {
        "quality_gate": "profile",
        "prepare": "quality",
        "train": "prepared",
        "evaluate": "model",
        "select": "candidates",
        "register": "selected",
    }
    nodes: list[PipelineNode] = []
    for node in pipeline.nodes:
        if "/" in node.kind:
            raise ValueError("quality_suite cannot be combined with plugin pipeline stages")
        config = dict(node.config)
        if node.kind == "quality_gate":
            config["suite"] = suite.to_payload()
        elif node.kind == "train" and algorithm is not None:
            config.setdefault("algorithm", algorithm)
        elif node.kind == "prepare" and preprocessor is not None:
            config.setdefault("preprocessor", preprocessor)
        port = output_ports.get(node.kind)
        inputs = (
            ((port, tuple(f"{dependency}.out" for dependency in node.depends_on)),)
            if port is not None
            else ()
        )
        nodes.append(
            PipelineNode(
                node.id,
                node.kind,
                config=config,
                inputs=inputs,
                stage_version=1,
            )
        )
    parameters["stage_registry_digest"] = stage_registry_digest
    return PipelineIR(
        tuple(nodes), tuple(sorted(parameters.items())), PIPELINE_SCHEMA_V3
    )


class MachineLearningStudioPlugin:
    manifest = PluginManifest(
        id="com.sauronshepherd.ronin.ml-studio",
        name="Machine Learning Studio",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        capabilities=(
            "ml-studio.labs",
            "ml-studio.experiments",
            "ml-studio.backends",
            "ml-studio.models",
            "ml-studio.deployments",
        ),
        permissions=("ml-studio:read", "ml-studio:write", "ml-studio:execute"),
        job_types=("ml-studio.deployment.v1",),
        ui_entry="ml-studio",
        surface_ids=(
            "ml-studio.backends.v1",
            "ml-studio.labs.v1",
            "ml-studio.run.v1",
            "ml-studio.models.v1",
            "ml-studio.deployments.v1",
        ),
    )

    def __init__(self) -> None:
        self._labs: LabService | None = None
        self._runner = LocalExperimentRunner()
        self._coordinator = LocalExecutionCoordinator(
            self._runner, result_finalizer=self._finalize_pipeline_registration
        )
        self._registry: MLRegistryStore | None = None
        self._artifacts: ArtifactStore | None = None
        self._artifact_reference_barrier: ArtifactReferenceBarrier | None = None
        self._dataset_resolver: DatasetResolver | None = None

    def register(self, context: PluginContext) -> None:
        store = context.services.get("ml_lab_store")
        if store is None:
            store = InMemoryMLLabStore()
        self._labs = LabService(cast(MLLabStore, store))
        coordinator_runner = self._coordinator._runner
        configure_stage_registry = getattr(
            coordinator_runner, "configure_plugin_stage_registry", None
        )
        if callable(configure_stage_registry):
            configure_stage_registry(context.contributions.pipeline_stage_registry)
        self._coordinator.close()
        self._artifacts = cast(ArtifactStore | None, context.services.get("artifact_store"))
        reference_barrier = context.services.get("artifact_reference_barrier")
        self._artifact_reference_barrier = cast(ArtifactReferenceBarrier | None, reference_barrier)
        execution_service = context.services.get("ml_execution_service")
        execution_store = (
            JobStoreExecutionStore(
                cast(Any, execution_service),
                self._artifacts,
                artifact_reference_barrier=cast(Any, reference_barrier),
            )
            if execution_service is not None
            else None
        )
        configure_artifacts = getattr(
            coordinator_runner, "configure_plugin_artifact_capabilities", None
        )
        if callable(configure_artifacts):
            configure_artifacts(
                available=(
                    isinstance(execution_store, JobStoreExecutionStore)
                    and self._artifacts is not None
                    and self._artifact_reference_barrier is not None
                )
            )
        self._coordinator = LocalExecutionCoordinator(
            coordinator_runner,
            store=execution_store,
            autostart=False,
            result_finalizer=self._finalize_pipeline_registration,
        )
        self._registry = cast(MLRegistryStore | None, context.services.get("ml_registry"))
        catalog = context.services.get("catalog_store")
        if catalog is not None and self._artifacts is not None:
            from studio_storage.ports import CatalogStore

            self._dataset_resolver = DatasetResolver(cast(CatalogStore, catalog), self._artifacts)
        context.contributions.add_ui(
            context.plugin_id,
            {
                "plugin_id": context.plugin_id,
                "ui_api": "1.0",
                "navigation": [
                    {"id": "mlstudio", "route": "/mlstudio", "permission": "ml-studio:read"}
                ],
                "widgets": [],
            },
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/labs",
            context.plugin_id,
            self.list_labs,
            permission="ml-studio:read",
        )

        for contribution in (
            SurfaceContribution(
                id="ml-studio.backends.v1",
                plugin_id=context.plugin_id,
                namespace="ml-studio",
                command="backends",
                operation_id="ml-studio.backends.v1",
                capability="ml-studio.backends",
                permission="ml-studio:read",
                path="/v1/ml-studio/backends",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="ml-studio.labs.v1",
                plugin_id=context.plugin_id,
                namespace="ml-studio",
                command="list-labs",
                operation_id="ml-studio.labs.v1",
                capability="ml-studio.labs",
                permission="ml-studio:read",
                path="/v1/ml-studio/labs",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="ml-studio.run.v1",
                plugin_id=context.plugin_id,
                namespace="ml-studio",
                command="run",
                operation_id="ml-studio.run.v1",
                capability="ml-studio.experiments",
                permission="ml-studio:execute",
                path="/v1/ml-studio/labs/{lab_id}/runs",
                method="POST",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="ml-studio.models.v1",
                plugin_id=context.plugin_id,
                namespace="ml-studio",
                command="models",
                operation_id="ml-studio.models.v1",
                capability="ml-studio.models",
                permission="ml-studio:read",
                path="/v1/ml-studio/models",
                method="GET",
                output_schema={"type": "object"},
            ),
            SurfaceContribution(
                id="ml-studio.deployments.v1",
                plugin_id=context.plugin_id,
                namespace="ml-studio",
                command="deployments",
                operation_id="ml-studio.deployments.v1",
                capability="ml-studio.deployments",
                permission="ml-studio:read",
                path="/v1/ml-studio/deployments",
                method="GET",
                output_schema={"type": "object"},
            ),
        ):
            context.contributions.add_surface(contribution)
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/labs",
            context.plugin_id,
            self.create_lab,
            permission="ml-studio:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/labs/{lab_id}",
            context.plugin_id,
            self.get_lab,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/labs/{lab_id}/compile",
            context.plugin_id,
            self.compile_lab,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/labs/{lab_id}/runs",
            context.plugin_id,
            self.run_lab,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/runs/{run_id}",
            context.plugin_id,
            self.get_run,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/labs/{lab_id}/quality",
            context.plugin_id,
            self.quality_check,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "GET", "/v1/ml-studio/labs/{lab_id}/quality-suites", context.plugin_id,
            self.list_quality_suites, permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST", "/v1/ml-studio/labs/{lab_id}/quality-suites", context.plugin_id,
            self.save_quality_suite, permission="ml-studio:write",
        )
        context.contributions.add_route(
            "GET", "/v1/ml-studio/labs/{lab_id}/quality-suites/{suite_id}/{version}", context.plugin_id,
            self.get_quality_suite, permission="ml-studio:read",
        )
        context.contributions.add_route(
            "GET", "/v1/ml-studio/labs/{lab_id}/drift-policies", context.plugin_id,
            self.list_drift_policies, permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST", "/v1/ml-studio/labs/{lab_id}/drift-policies", context.plugin_id,
            self.save_drift_policy, permission="ml-studio:write",
        )
        context.contributions.add_route(
            "GET", "/v1/ml-studio/labs/{lab_id}/drift-policies/{policy_id}/{version}", context.plugin_id,
            self.get_drift_policy, permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/labs/{lab_id}/drift",
            context.plugin_id,
            self.drift_report,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/labs/{lab_id}/executions",
            context.plugin_id,
            self.submit_execution,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/labs/{lab_id}/compare",
            context.plugin_id,
            self.compare_trials,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/labs/{lab_id}/search",
            context.plugin_id,
            self.search_trials,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/executions/{run_id}",
            context.plugin_id,
            self.execution_status,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/executions/{run_id}/register",
            context.plugin_id,
            self.register_execution_model,
            permission="ml-studio:write",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/executions/{run_id}/cancel",
            context.plugin_id,
            self.cancel_execution,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/executions/{run_id}/retry",
            context.plugin_id,
            self.retry_execution,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/backends",
            context.plugin_id,
            self.backends,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/experiments",
            context.plugin_id,
            self.create_experiment,
            permission="ml-studio:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/experiments",
            context.plugin_id,
            self.list_experiments,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/experiments/{experiment_id}",
            context.plugin_id,
            self.get_experiment,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/models",
            context.plugin_id,
            self.list_models,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/models/{model_id}/{version}/promote",
            context.plugin_id,
            self.promote_model,
            permission="ml-studio:write",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/models/{model_id}/{version}/predict",
            context.plugin_id,
            self.predict_model,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/models/{model_id}/{version}/batch-predict",
            context.plugin_id,
            self.batch_predict_model,
            permission="ml-studio:execute",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/models/{model_id}/{version}/card",
            context.plugin_id,
            self.model_card,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/models/{model_id}/{version}/artifact",
            context.plugin_id,
            self.model_artifact,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/deployments",
            context.plugin_id,
            self.create_deployment,
            permission="ml-studio:write",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/deployments",
            context.plugin_id,
            self.list_deployments,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/deployments/{deployment_id}",
            context.plugin_id,
            self.get_deployment,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/ml-studio/deployments/{deployment_id}/health",
            context.plugin_id,
            self.deployment_health,
            permission="ml-studio:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/deployments/{deployment_id}/rollback",
            context.plugin_id,
            self.rollback_deployment,
            permission="ml-studio:write",
        )
        context.contributions.add_route(
            "POST",
            "/v1/ml-studio/deployments/{deployment_id}/predict",
            context.plugin_id,
            self.predict_deployment,
            permission="ml-studio:execute",
        )
        context.contributions.add_job(
            "ml-studio.deployment.v1",
            context.plugin_id,
            self.run_deployment_task,
        )

    def startup(self) -> None:
        self._coordinator.start()

    def shutdown(self) -> None:
        self._coordinator.close()

    def backends(self, *_args: Any, **_kwargs: Any) -> dict[str, object]:
        items = []
        for backend in default_backends():
            capabilities = getattr(backend, "capabilities", None)
            available = getattr(backend, "available", True) is not False
            item: dict[str, object] = {
                "id": backend.backend_id,
                "name": backend.display_name,
                "status": "available" if available else "unavailable",
            }
            if not available:
                item["reason"] = getattr(
                    backend,
                    "unavailable_reason",
                    "The optional machine learning dependency is not installed.",
                )
                item["install_extra"] = "ml"
            if capabilities is not None:
                item["capabilities"] = capabilities.to_payload()
            items.append(item)
        return {
            "schema": "ronin.ml-backends/v1",
            "items": items,
        }

    def list_models(self, workspace_id: str | None = None, **_kwargs: Any) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        from studio_core.ml import ModelId

        model_id = _kwargs.get("model_id")
        items = self._registry.list_models(
            WorkspaceId(workspace_id), ModelId(model_id) if model_id else None
        )
        return {"items": [item.to_payload() for item in items]}

    def promote_model(
        self,
        workspace_id: str | None = None,
        model_id: str | None = None,
        version: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        if (
            not isinstance(model_id, str)
            or not isinstance(version, str)
            or not model_id
            or not version
            or model_id != model_id.strip()
            or version != version.strip()
            or len(model_id) > 256
            or len(version) > 256
            or any(char in model_id for char in "\r\n\x00")
            or any(char in version for char in "\r\n\x00")
        ):
            raise ValueError("model_id and version are bounded identifiers")
        if (
            not isinstance(body, dict)
            or set(body) != {"reason"}
            or not isinstance(body.get("reason"), str)
            or not body["reason"].strip()
            or body["reason"] != body["reason"].strip()
            or len(body["reason"]) > 1024
            or any(char in body["reason"] for char in "\r\n\x00")
        ):
            raise ValueError("promotion reason is required and bounded")
        from studio_core.ml import ModelId, ModelVersion

        model = self._registry.promote_model(
            WorkspaceId(workspace_id), ModelId(model_id), ModelVersion(version), now=_plugin_now()
        )
        return model.to_payload()

    def predict_model(
        self,
        workspace_id: str | None = None,
        model_id: str | None = None,
        version: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        if (
            not isinstance(model_id, str)
            or not isinstance(version, str)
            or not model_id
            or not version
            or model_id != model_id.strip()
            or version != version.strip()
            or len(model_id) > 256
            or len(version) > 256
            or any(char in model_id for char in "\r\n\x00")
            or any(char in version for char in "\r\n\x00")
            or not isinstance(body, dict)
            or set(body) - {"artifact_base64", "rows"}
        ):
            raise ValueError("model, version and body are required")
        encoded = body.get("artifact_base64")
        rows = body.get("rows")
        from studio_core.ml import ModelId, ModelVersion

        if (
            not isinstance(rows, list)
            or len(rows) > MAX_PREDICTION_ROWS
            or not all(isinstance(row, dict) for row in rows)
        ):
            raise ValueError("predict rows must contain at most 100000 objects")
        if encoded is not None and not isinstance(encoded, str):
            raise ValueError("artifact_base64 must be text when provided")
        model = self._registry.get_model(
            WorkspaceId(workspace_id), ModelId(model_id), ModelVersion(version)
        )
        if model is None:
            raise KeyError(f"{model_id}@{version}")
        if isinstance(encoded, str):
            if len(encoded) > ((MAX_PREDICTION_ARTIFACT_BYTES + 2) // 3) * 4:
                raise ValueError("artifact_base64 exceeds the model artifact limit")
            try:
                artifact = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise ValueError("artifact_base64 is invalid") from exc
            if len(artifact) > MAX_PREDICTION_ARTIFACT_BYTES:
                raise ValueError("model artifact exceeds the model artifact limit")
        elif self._artifacts is not None and hasattr(self._artifacts, "get_bytes_by_storage_ref"):
            artifact = self._artifacts.get_bytes_by_storage_ref(
                model.artifact_ref, digest=model.artifact_digest
            )
        else:
            raise ValueError("artifact_base64 is required when artifact store is unavailable")
        if len(artifact) > MAX_PREDICTION_ARTIFACT_BYTES:
            raise ValueError("model artifact exceeds the model artifact limit")

        predictions = predict_registered_tabular(
            self._registry,
            WorkspaceId(workspace_id),
            ModelId(model_id),
            ModelVersion(version),
            artifact,
            rows,
        )
        return {"model_id": model_id, "version": version, "predictions": list(predictions)}

    def batch_predict_model(
        self,
        workspace_id: str | None = None,
        model_id: str | None = None,
        version: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        """Run bounded batch inference with an explicit replay identity."""
        if (
            not isinstance(body, dict)
            or set(body) - {"batch_id", "artifact_base64", "rows"}
            or not isinstance(body.get("batch_id"), str)
        ):
            raise ValueError("batch_id is required for batch prediction")
        batch_id = body["batch_id"]
        if (
            not batch_id
            or batch_id != batch_id.strip()
            or len(batch_id) > 256
            or any(char in batch_id for char in "\r\n\x00")
        ):
            raise ValueError("batch_id must be a bounded single-line identifier")
        rows = body.get("rows")
        if (
            not isinstance(rows, list)
            or not rows
            or len(rows) > 100_000
            or not all(isinstance(row, dict) for row in rows)
        ):
            raise ValueError("batch prediction rows must contain at most 100000 items")
        result = self.predict_model(
            workspace_id,
            model_id,
            version,
            body=body,
            **_kwargs,
        )
        return {
            **result,
            "batch_id": batch_id,
            "row_count": len(rows),
            "evidence": {
                "kind": "batch-inference",
                "replay_key": f"{model_id}@{version}:{batch_id}",
                "input_sha256": hashlib.sha256(
                    json.dumps(
                        rows,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                ).hexdigest(),
            },
        }

    def model_card(
        self,
        workspace_id: str | None = None,
        model_id: str | None = None,
        version: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        if (
            not isinstance(model_id, str)
            or not isinstance(version, str)
            or not model_id
            or not version
            or model_id != model_id.strip()
            or version != version.strip()
            or len(model_id) > 256
            or len(version) > 256
            or any(char in model_id for char in "\r\n\x00")
            or any(char in version for char in "\r\n\x00")
        ):
            raise ValueError("model_id and version are bounded identifiers")
        from studio_core.ml import ModelId, ModelVersion

        model = self._registry.get_model(
            WorkspaceId(workspace_id), ModelId(model_id), ModelVersion(version)
        )
        if model is None:
            raise KeyError(f"{model_id}@{version}")
        source_run = self._registry.get_run(
            WorkspaceId(workspace_id), model.source_run_id
        )
        run_parameters = dict(source_run.parameters) if source_run is not None else {}
        limitations = ["Review dataset quality and evaluation evidence before promotion."]
        if source_run is None:
            limitations.append("Source run evidence is unavailable; dataset and metrics are incomplete.")
        return {
            "schema": "ronin.ml-model-card/v1",
            "identity": {"model_id": model_id, "version": version, "stage": model.stage},
            "provenance": {
                "source_run_id": model.source_run_id.value,
                "artifact_ref": model.artifact_ref,
                "artifact_digest": model.artifact_digest,
                "execution_ref": source_run.execution_ref if source_run is not None else None,
                "source_revision": source_run.source_revision if source_run is not None else None,
            },
            "framework": model.framework,
            "signature": model.signature.to_payload(),
            "intended_use": {
                "task": run_parameters.get("task"),
                "statement": "Use only with the declared input signature and reviewed evaluation evidence; this card does not imply production suitability.",
            },
            "dataset": (
                [dataset.to_payload() for dataset in source_run.datasets]
                if source_run is not None
                else []
            ),
            "features": [name for name, _ in model.signature.inputs],
            "parameters": run_parameters,
            "metrics": (
                [metric.to_payload() for metric in source_run.metrics]
                if source_run is not None
                else []
            ),
            "fairness": {
                "status": "not_assessed",
                "reason": "No protected-group or fairness evaluation evidence is attached to this model version.",
            },
            "owner": None,
            "limitations": limitations,
        }

    def model_artifact(
        self,
        model_id: str,
        version: str,
        workspace_id: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        """Return a digest-verified, bounded chunk of a workspace model artifact."""
        if self._registry is None or self._artifacts is None:
            raise RuntimeError("model artifact retrieval requires registry and artifact store")
        if (
            not isinstance(model_id, str)
            or not isinstance(version, str)
            or not model_id
            or not version
            or model_id != model_id.strip()
            or version != version.strip()
            or len(model_id) > 256
            or len(version) > 256
            or any(char in model_id for char in "\r\n\x00")
            or any(char in version for char in "\r\n\x00")
        ):
            raise ValueError("model_id and version are bounded identifiers")
        workspace_id = self._workspace(workspace_id, _kwargs)
        raw_query = _kwargs.get("query")
        query = parse_qs(raw_query if isinstance(raw_query, str) else "", keep_blank_values=True)
        if set(query) - {"workspace_id", "offset", "length"} or any(
            len(values) != 1 for values in query.values()
        ):
            raise ValueError("artifact query contains unknown or duplicate parameters")

        def query_int(name: str, default: int) -> int:
            value = query.get(name, [str(default)])[0]
            if not value.isascii() or not value.isdecimal() or len(value) > 20:
                raise ValueError(f"artifact {name} must be a non-negative integer")
            return int(value)

        offset = query_int("offset", 0)
        length = query_int("length", 512 * 1024)
        max_chunk = 512 * 1024
        if length < 1 or length > max_chunk:
            raise ValueError(f"artifact length must be between 1 and {max_chunk}")

        from studio_core.ml import ModelId, ModelVersion

        model = self._registry.get_model(
            WorkspaceId(workspace_id), ModelId(model_id), ModelVersion(version)
        )
        if model is None:
            raise KeyError(f"{model_id}@{version}")
        if model.framework == "sklearn":
            media_type = "application/vnd.ronin.sklearn-tabular+json"
        elif model.framework == "ronin-kmeans":
            media_type = "application/vnd.ronin.ml-kmeans+json"
        else:
            raise ValueError(f"unsupported model artifact framework: {model.framework}")
        if len(model.artifact_digest) != 64 or any(
            character not in "0123456789abcdef" for character in model.artifact_digest
        ):
            raise ValueError("registered model artifact digest is invalid")
        getter = getattr(self._artifacts, "get_bytes_by_storage_ref", None)
        if not callable(getter):
            raise ValueError("artifact store does not support verified storage references")
        data = getter(model.artifact_ref, digest=model.artifact_digest)
        if (
            not isinstance(data, bytes)
            or not data
            or len(data) > 64 * 1024 * 1024
            or hashlib.sha256(data).hexdigest() != model.artifact_digest
        ):
            raise ValueError("registered model artifact failed integrity verification")
        if offset > len(data):
            raise ValueError("artifact offset exceeds artifact size")
        end = min(offset + length, len(data))
        return {
            "model_id": model.model_id.value,
            "version": model.version.value,
            "digest": model.artifact_digest,
            "media_type": media_type,
            "size_bytes": len(data),
            "offset": offset,
            "next_offset": end if end < len(data) else None,
            "complete": end == len(data),
            "data_base64": base64.b64encode(data[offset:end]).decode("ascii"),
        }

    def run_deployment_task(
        self, payload: object | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        """Execute one idempotent scheduler deployment task."""
        if self._registry is None or self._artifacts is None:
            raise RuntimeError("model deployment requires registry and artifact store")
        if not isinstance(payload, dict) or set(payload) - {
            "workspace_id",
            "deployment_id",
            "model_id",
            "version",
            "endpoint",
        }:
            raise ValueError("deployment task contains unsupported fields")
        required = ("workspace_id", "deployment_id", "model_id", "version")
        if not all(isinstance(payload.get(name), str) for name in required):
            raise ValueError("deployment task requires workspace and model identity")
        workspace_id = self._bounded_identifier(payload["workspace_id"], "workspace_id")
        deployment_id = self._bounded_identifier(payload["deployment_id"], "deployment_id")
        model_id = self._bounded_identifier(payload["model_id"], "model_id")
        version = self._bounded_identifier(payload["version"], "version")
        endpoint = payload.get("endpoint", "local")
        if (
            not isinstance(endpoint, str)
            or not endpoint
            or endpoint != endpoint.strip()
            or len(endpoint) > 512
        ):
            raise ValueError("deployment endpoint must be bounded text")
        from studio_core.ml import ModelId, ModelVersion

        deployment = deploy_registered_model(
            self._registry,
            self._artifacts,
            WorkspaceId(workspace_id),
            deployment_id,
            ModelId(model_id),
            ModelVersion(version),
            endpoint=endpoint,
            now=_plugin_now(),
        )
        return {
            "schema": "ronin.ml-deployment-task-result/v1",
            "status": "ready",
            "deployment": deployment.to_payload(),
        }

    def create_deployment(
        self,
        workspace_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        """Create an immutable serving deployment pinned to one model digest."""
        if self._registry is None or self._artifacts is None:
            raise RuntimeError("model deployment requires registry and artifact store")
        workspace_id = self._workspace(workspace_id, _kwargs)
        if (
            not isinstance(body, dict)
            or set(body) - {"deployment_id", "model_id", "version", "endpoint"}
            or not all(isinstance(body.get(name), str) for name in ("deployment_id", "model_id", "version"))
        ):
            raise ValueError("deployment requires deployment_id, model_id and version")
        deployment_id = self._bounded_identifier(body["deployment_id"], "deployment_id")
        model_id = self._bounded_identifier(body["model_id"], "model_id")
        version = self._bounded_identifier(body["version"], "version")
        endpoint = body.get("endpoint", "local")
        if not isinstance(endpoint, str) or not endpoint or endpoint != endpoint.strip() or len(endpoint) > 512:
            raise ValueError("deployment endpoint must be bounded text")
        from studio_core.ml import ModelId, ModelVersion

        deployment = deploy_registered_model(
            self._registry,
            self._artifacts,
            WorkspaceId(workspace_id),
            deployment_id,
            ModelId(model_id),
            ModelVersion(version),
            endpoint=endpoint,
            now=_plugin_now(),
        )
        return deployment.to_payload()

    def list_deployments(
        self, workspace_id: str | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        if self._registry is None or not callable(getattr(self._registry, "list_deployments", None)):
            raise RuntimeError("model deployment registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        return {
            "items": [
                item.to_payload()
                for item in self._registry.list_deployments(WorkspaceId(workspace_id))
            ]
        }

    def get_deployment(
        self,
        deployment_id: str,
        workspace_id: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if self._registry is None or not callable(getattr(self._registry, "get_deployment", None)):
            raise RuntimeError("model deployment registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        deployment_id = self._bounded_identifier(deployment_id, "deployment_id")
        deployment = self._registry.get_deployment(WorkspaceId(workspace_id), deployment_id)
        if deployment is None:
            raise KeyError(deployment_id)
        return deployment.to_payload()

    def deployment_health(
        self,
        deployment_id: str,
        workspace_id: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        deployment = self.get_deployment(deployment_id, workspace_id, **_kwargs)
        return {
            "schema": "ronin.ml-deployment-health/v1",
            "deployment_id": deployment["deployment_id"],
            "status": deployment["status"],
            "readiness": deployment["readiness"],
            "healthy": deployment["status"] == "ready" and deployment["readiness"] == "ready",
            "artifact_digest": deployment["artifact_digest"],
            "revision": deployment["revision"],
            "telemetry": deployment["telemetry"],
        }

    def rollback_deployment(
        self,
        deployment_id: str,
        workspace_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("model deployment registry is unavailable")
        if body is not None and (
            not isinstance(body, dict)
            or set(body) - {"reason"}
            or ("reason" in body and (
                not isinstance(body["reason"], str)
                or not body["reason"]
                or body["reason"] != body["reason"].strip()
                or len(body["reason"]) > 1024
            ))
        ):
            raise ValueError("rollback reason must be bounded text")
        workspace_id = self._workspace(workspace_id, _kwargs)
        deployment_id = self._bounded_identifier(deployment_id, "deployment_id")
        deployment = rollback_model_deployment(
            self._registry, WorkspaceId(workspace_id), deployment_id, now=_plugin_now()
        )
        return deployment.to_payload()

    def predict_deployment(
        self,
        deployment_id: str,
        workspace_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if self._registry is None or self._artifacts is None:
            raise RuntimeError("model deployment requires registry and artifact store")
        workspace_id = self._workspace(workspace_id, _kwargs)
        deployment_id = self._bounded_identifier(deployment_id, "deployment_id")
        deployment = self._registry.get_deployment(WorkspaceId(workspace_id), deployment_id)
        if deployment is None:
            raise KeyError(deployment_id)
        if deployment.status != "ready" or deployment.readiness != "ready":
            raise ValueError("deployment is not ready")
        if not isinstance(body, dict) or set(body) - {"rows", "artifact_base64"}:
            raise ValueError("deployment prediction body contains unsupported fields")
        rows = body.get("rows")
        encoded = body.get("artifact_base64")
        if (
            not isinstance(rows, list)
            or len(rows) > MAX_PREDICTION_ROWS
            or not all(isinstance(row, dict) for row in rows)
            or (encoded is not None and not isinstance(encoded, str))
        ):
            raise ValueError("deployment prediction rows or artifact are invalid")
        model = self._registry.get_model(
            WorkspaceId(workspace_id), deployment.model_id, deployment.version
        )
        if model is None or model.artifact_digest != deployment.artifact_digest or model.artifact_ref != deployment.artifact_ref:
            raise ValueError("deployment model pin no longer matches the registry")
        if isinstance(encoded, str):
            if len(encoded) > ((MAX_PREDICTION_ARTIFACT_BYTES + 2) // 3) * 4:
                raise ValueError("artifact_base64 exceeds the model artifact limit")
            try:
                artifact = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise ValueError("artifact_base64 is invalid") from exc
        else:
            getter = getattr(self._artifacts, "get_bytes_by_storage_ref", None)
            if not callable(getter):
                raise ValueError("deployment artifact store cannot verify the pinned artifact")
            artifact = getter(deployment.artifact_ref, digest=deployment.artifact_digest)
        if (
            not isinstance(artifact, bytes)
            or not artifact
            or len(artifact) > MAX_PREDICTION_ARTIFACT_BYTES
            or hashlib.sha256(artifact).hexdigest() != deployment.artifact_digest
        ):
            raise ValueError("deployment artifact failed digest verification")
        try:
            predictions = predict_registered_tabular(
                self._registry,
                WorkspaceId(workspace_id),
                deployment.model_id,
                deployment.version,
                artifact,
                rows,
            )
        except Exception as exc:
            try:
                record_deployment_request(
                    self._registry,
                    WorkspaceId(workspace_id),
                    deployment_id,
                    success=False,
                    error=str(exc)[:1024] or "serving request failed",
                    now=_plugin_now(),
                )
            except Exception:
                pass
            raise
        updated = record_deployment_request(
            self._registry,
            WorkspaceId(workspace_id),
            deployment_id,
            success=True,
            now=_plugin_now(),
        )
        return {
            "deployment_id": deployment_id,
            "model_id": deployment.model_id.value,
            "version": deployment.version.value,
            "predictions": list(predictions),
            "telemetry": updated.to_payload()["telemetry"],
        }

    def list_labs(self, workspace_id: str, **_kwargs: Any) -> dict[str, object]:
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        return {"items": [lab.to_payload() for lab in self._labs.list(WorkspaceId(workspace_id))]}

    @staticmethod
    def _workspace(workspace_id: str | None, kwargs: dict[str, Any]) -> str:
        value = workspace_id
        if not value:
            query = str(kwargs.get("query", ""))
            value = parse_qs(query).get("workspace_id", [None])[0]
        if not value:
            raise ValueError("workspace_id is required")
        return MachineLearningStudioPlugin._bounded_identifier(value, "workspace_id")

    @staticmethod
    def _bounded_identifier(value: object, name: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 256
            or any(char in value for char in "\r\n\x00")
        ):
            raise ValueError(f"{name} must be a bounded single-line identifier")
        return value

    def create_lab(
        self, workspace_id: str | None = None, *, body: object | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        if not isinstance(body, dict):
            raise ValueError("lab body must be an object")
        return self._labs.create(WorkspaceId(workspace_id), Lab.from_payload(body)).to_payload()

    def get_lab(self, workspace_id: str, lab_id: str, **_kwargs: Any) -> dict[str, object]:
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        return self._labs.get(WorkspaceId(workspace_id), lab_id).to_payload()

    def compile_lab(self, workspace_id: str, lab_id: str, **_kwargs: Any) -> dict[str, object]:
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        return self._labs.compile(WorkspaceId(workspace_id), lab_id).to_payload()

    def run_lab(
        self, workspace_id: str, lab_id: str, *, body: object | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        if not isinstance(body, dict) or set(body) - {
            "rows",
            "run_id",
            "execution_ref",
            "source_revision",
            "register",
        }:
            raise ValueError("run body has invalid shape")
        if "rows" in body and body["rows"] is None:
            raise ValueError("run rows must be an array when provided")
        if "rows" in body and (
            not isinstance(body["rows"], list)
            or not all(isinstance(row, dict) for row in body["rows"])
        ):
            raise ValueError("run rows must be an array of objects")
        for field, default in (
            ("run_id", f"run-{lab_id}"),
            ("execution_ref", "ml-studio-local"),
            ("source_revision", "local"),
        ):
            value = body.get(field, default)
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
                or len(value) > 256
                or any(char in value for char in "\r\n\x00")
            ):
                raise ValueError(f"{field} must be a bounded single-line identifier")
        registration = body.get("register")
        if registration is not None:
            if (
                not isinstance(registration, dict)
                or set(registration) != {"model_id", "version"}
                or not all(isinstance(registration[key], str) for key in ("model_id", "version"))
                or any(
                    not registration[key].strip()
                    or registration[key] != registration[key].strip()
                    or len(registration[key]) > 256
                    or any(char in registration[key] for char in "\r\n\x00")
                    for key in ("model_id", "version")
                )
            ):
                raise ValueError("register must contain bounded model_id and version")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        if registration is not None and lab.task != "clustering":
            raise ValueError(
                "synchronous register is supported only for clustering; "
                "use the durable execution register route for supervised models"
            )
        rows = resolve_lab_rows(
            WorkspaceId(workspace_id), lab, body.get("rows"), self._dataset_resolver
        )
        if lab.task == "clustering":
            result = self._runner.run_clustering_result(lab, rows)
            payload = result.to_payload()
            if self._registry is not None and self._artifacts is not None:
                from studio_core.ml import MLRunId

                run = persist_clustering_result(
                    self._registry,
                    self._artifacts,
                    WorkspaceId(workspace_id),
                    lab,
                    result,
                    run_id=MLRunId(cast(str, body.get("run_id", f"run-{lab_id}"))),
                    execution_ref=cast(str, body.get("execution_ref", "ml-studio-local")),
                    source_revision=cast(str, body.get("source_revision", "local")),
                    now=_plugin_now(),
                    artifact_reference_barrier=self._artifact_reference_barrier,
                )
                payload["run"] = run.to_payload()
                if registration is not None:
                    from studio_core.ml import ModelId, ModelVersion

                    model = register_clustering_model(
                        self._registry,
                        self._artifacts,
                        WorkspaceId(workspace_id),
                        lab,
                        result,
                        run_id=MLRunId(run.id.value),
                        model_id=ModelId(cast(str, registration["model_id"])),
                        model_version=ModelVersion(cast(str, registration["version"])),
                        now=_plugin_now(),
                        artifact_reference_barrier=self._artifact_reference_barrier,
                    )
                    payload["model"] = model.to_payload()
            return payload
        experiment_result = self._runner.run(lab, rows)
        payload = experiment_result.to_payload()
        if self._registry is not None:
            from studio_core.ml import MLRunId

            run = persist_experiment_result(
                self._registry,
                WorkspaceId(workspace_id),
                lab,
                experiment_result,
                run_id=MLRunId(cast(str, body.get("run_id", f"run-{lab_id}"))),
                execution_ref=cast(str, body.get("execution_ref", "ml-studio-local")),
                source_revision=cast(str, body.get("source_revision", "local")),
                now=_plugin_now(),
            )
            payload["run"] = run.to_payload()
        return payload

    def get_run(self, workspace_id: str, run_id: str, **_kwargs: Any) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
        run_id = self._bounded_identifier(run_id, "run_id")
        from studio_core.ml import MLRunId

        run = self._registry.get_run(WorkspaceId(workspace_id), MLRunId(run_id))
        if run is None:
            raise KeyError(run_id)
        return run.to_payload()

    def quality_check(
        self,
        workspace_id: str | None = None,
        lab_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
        if lab_id is None:
            raise ValueError("lab_id is required")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        if not isinstance(body, dict) or set(body) - {"rows", "suite"}:
            raise ValueError("quality body supports optional rows and a versioned suite")
        if "rows" in body and body["rows"] is None:
            raise ValueError("quality rows must be an array when provided")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        raw_suite = body.get("suite")
        suite = QualitySuite.from_payload(raw_suite) if raw_suite is not None else None
        validate_quality_suite(lab, suite)
        rows = resolve_lab_rows(
            WorkspaceId(workspace_id), lab, body.get("rows"), self._dataset_resolver
        )
        return profile_and_validate(lab, rows, suite=suite).to_payload()

    def list_quality_suites(
        self, workspace_id: str | None = None, lab_id: str | None = None, **kwargs: Any
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, kwargs)
        if lab_id is None or self._labs is None:
            raise ValueError("lab_id is required and ML Studio must be ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        return {"items": [item.to_payload() for item in self._labs.list_quality_suites(WorkspaceId(workspace_id), lab_id)]}

    def save_quality_suite(
        self, workspace_id: str | None = None, lab_id: str | None = None, *, body: object | None = None, **kwargs: Any
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, kwargs)
        if lab_id is None or self._labs is None:
            raise ValueError("lab_id is required and ML Studio must be ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        suite = QualitySuite.from_payload(body)
        return self._labs.put_quality_suite(WorkspaceId(workspace_id), lab_id, suite).to_payload()

    def get_quality_suite(
        self, workspace_id: str | None = None, lab_id: str | None = None,
        suite_id: str | None = None, version: str | int | None = None, **kwargs: Any,
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, kwargs)
        if lab_id is None or suite_id is None or self._labs is None:
            raise ValueError("lab_id and suite_id are required and ML Studio must be ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        suite_id = self._bounded_identifier(unquote(suite_id), "suite_id")
        parsed_version = parse_catalog_version(version, "quality suite")
        suite = self._labs.get_quality_suite(
            WorkspaceId(workspace_id), lab_id, suite_id, parsed_version
        )
        if suite is None:
            raise KeyError(f"{lab_id}/{unquote(suite_id)}@{parsed_version}")
        return suite.to_payload()

    def list_drift_policies(
        self, workspace_id: str | None = None, lab_id: str | None = None, **kwargs: Any
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, kwargs)
        if lab_id is None or self._labs is None:
            raise ValueError("lab_id is required and ML Studio must be ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        return {
            "items": [
                item.to_payload()
                for item in self._labs.list_drift_policies(WorkspaceId(workspace_id), lab_id)
            ]
        }

    def save_drift_policy(
        self, workspace_id: str | None = None, lab_id: str | None = None,
        *, body: object | None = None, **kwargs: Any,
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, kwargs)
        if lab_id is None or self._labs is None:
            raise ValueError("lab_id is required and ML Studio must be ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        policy = DriftPolicy.from_payload(body)
        return self._labs.put_drift_policy(WorkspaceId(workspace_id), lab_id, policy).to_payload()

    def get_drift_policy(
        self, workspace_id: str | None = None, lab_id: str | None = None,
        policy_id: str | None = None, version: str | int | None = None, **kwargs: Any,
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, kwargs)
        if lab_id is None or policy_id is None or self._labs is None:
            raise ValueError("lab_id and policy_id are required and ML Studio must be ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        policy_id = self._bounded_identifier(unquote(policy_id), "policy_id")
        parsed_version = parse_catalog_version(version, "drift policy")
        policy = self._labs.get_drift_policy(
            WorkspaceId(workspace_id), lab_id, policy_id, parsed_version
        )
        if policy is None:
            raise KeyError(f"{lab_id}/{unquote(policy_id)}@{parsed_version}")
        return policy.to_payload()

    def drift_report(
        self,
        workspace_id: str | None = None,
        lab_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        """Compare explicit, bounded numeric windows against a Lab's feature contract."""
        workspace_id = self._workspace(workspace_id, _kwargs)
        if lab_id is None:
            raise ValueError("lab_id is required")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        if not isinstance(body, dict) or set(body) != {
            "baseline_rows", "current_rows", "policy"
        }:
            raise ValueError(
                "drift body requires baseline_rows, current_rows, and a versioned policy"
            )
        baseline_rows = body["baseline_rows"]
        current_rows = body["current_rows"]
        raw_policy = body["policy"]
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        if not isinstance(baseline_rows, list) or not isinstance(current_rows, list):
            raise ValueError("drift windows must be arrays of row objects")
        baseline_rows = resolve_lab_rows(
            WorkspaceId(workspace_id), lab, baseline_rows, None
        )
        current_rows = resolve_lab_rows(
            WorkspaceId(workspace_id), lab, current_rows, None
        )
        features = tuple(
            feature.column for feature in lab.features if feature.role == "numeric"
        )
        if not features:
            raise ValueError("drift reports require at least one Lab feature with numeric role")
        policy = DriftPolicy.from_payload(raw_policy)
        threshold_features = {item.feature for item in policy.thresholds}
        if threshold_features != set(features):
            raise ValueError("drift thresholds must define every numeric Lab feature exactly once")
        summaries = compare_numeric_drift(
            baseline_rows, current_rows, features, max_rows=100_000
        )
        assessment = assess_numeric_drift(summaries, policy.thresholds)
        return {
            "schema": "ronin.ml-drift-report/v1",
            "lab_id": lab.id,
            "policy": policy.to_payload(),
            "features": list(features),
            "baseline_row_count": len(baseline_rows),
            "current_row_count": len(current_rows),
            "summaries": [summary.to_payload() for summary in summaries],
            "assessment": assessment.to_payload(),
            "limitations": [
                "Numeric mean and population variance only; this report does not assess categorical drift or fairness."
            ],
        }

    def submit_execution(
        self,
        workspace_id: str | None = None,
        lab_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
        if lab_id is None:
            raise ValueError("lab_id is required")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        if not isinstance(body, dict) or set(body) - {
            "run_id",
            "rows",
            "algorithm",
            "preprocessor",
            "candidate_algorithms",
            "candidate_cluster_counts",
            "candidate_preprocessors",
            "selection_metric",
            "selection_direction",
            "register",
            "pipeline",
            "quality_suite",
        }:
            raise ValueError("execution body contains unsupported fields")
        if "rows" in body and body["rows"] is None:
            raise ValueError("execution rows must be an array when provided")
        run_id = body.get("run_id", f"run-{lab_id}")
        if (
            not isinstance(run_id, str)
            or not run_id
            or run_id != run_id.strip()
            or len(run_id) > 256
            or any(char in run_id for char in "\r\n\x00")
        ):
            raise ValueError("execution run_id must be 1 to 256 characters of trimmed text")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        if "pipeline" in body and body["pipeline"] is None:
            raise ValueError("pipeline must be a PipelineIR v2 or v3 object when provided")
        raw_pipeline = body.get("pipeline")
        suite = QualitySuite.from_payload(body["quality_suite"]) if "quality_suite" in body else None
        if raw_pipeline is not None and suite is not None:
            raise ValueError("quality_suite cannot be combined with an explicitly supplied pipeline")
        pipeline_options = {
            "algorithm",
            "preprocessor",
            "candidate_algorithms",
            "candidate_cluster_counts",
            "candidate_preprocessors",
            "selection_metric",
            "selection_direction",
            "register",
        }
        if raw_pipeline is not None and any(key in body for key in pipeline_options):
            raise ValueError("pipeline cannot be combined with compiler execution options")
        algorithm = body.get("algorithm")
        if algorithm is not None and (
            not isinstance(algorithm, str)
            or not algorithm
            or algorithm != algorithm.strip()
            or len(algorithm) > 256
            or any(char in algorithm for char in "\r\n\x00")
        ):
            raise ValueError("algorithm must be a non-empty trimmed string")
        candidate_algorithms = body.get("candidate_algorithms")
        if candidate_algorithms is not None and (
            not isinstance(candidate_algorithms, list)
            or len(candidate_algorithms) > 8
            or not all(
                isinstance(item, str)
                and item
                and item == item.strip()
                and len(item) <= 256
                and not any(char in item for char in "\r\n\x00")
                for item in candidate_algorithms
            )
        ):
            raise ValueError("candidate_algorithms must be an array of trimmed algorithm names")
        candidate_cluster_counts = body.get("candidate_cluster_counts")
        if candidate_cluster_counts is not None and (
            not isinstance(candidate_cluster_counts, list)
            or len(candidate_cluster_counts) > 8
            or any(
                not isinstance(item, int) or isinstance(item, bool)
                for item in candidate_cluster_counts
            )
        ):
            raise ValueError("candidate_cluster_counts must be an array of integers")
        candidate_preprocessors = body.get("candidate_preprocessors")
        if candidate_preprocessors is not None and (
            not isinstance(candidate_preprocessors, list)
            or len(candidate_preprocessors) > 5
            or not all(
                isinstance(item, str)
                and item
                and item == item.strip()
                and len(item) <= 256
                and not any(char in item for char in "\r\n\x00")
                for item in candidate_preprocessors
            )
        ):
            raise ValueError("candidate_preprocessors must be an array of trimmed names")
        selection_metric = body.get("selection_metric")
        if selection_metric is not None and (
            not isinstance(selection_metric, str)
            or not selection_metric
            or selection_metric != selection_metric.strip()
            or len(selection_metric) > 128
            or any(char in selection_metric for char in "\r\n\x00")
        ):
            raise ValueError("selection_metric must be a non-empty trimmed string")
        selection_direction = body.get("selection_direction")
        if selection_direction is not None and (
            not isinstance(selection_direction, str)
            or selection_direction not in {"maximize", "minimize"}
        ):
            raise ValueError("selection_direction must be maximize or minimize")
        preprocessor = body.get("preprocessor", "identity")
        if not isinstance(preprocessor, str) or preprocessor not in {
            "identity",
            "standard_scale",
            "one_hot",
            "median_impute",
            "one_hot_median_impute",
        }:
            raise ValueError("preprocessor is not supported")
        if candidate_preprocessors is not None and "preprocessor" in body:
            raise ValueError("preprocessor cannot be combined with candidate_preprocessors")
        if (
            candidate_preprocessors is None
            and lab.task == "clustering"
            and preprocessor != "identity"
        ):
            raise ValueError("preprocessor is not supported for clustering Labs")
        registration = body.get("register")
        if registration is not None and (
            not isinstance(registration, dict)
            or set(registration) != {"model_id", "version"}
            or any(
                not isinstance(registration.get(key), str)
                or not registration[key]
                or registration[key] != registration[key].strip()
                    or len(registration[key]) > 256
                    or any(char in registration[key] for char in "\r\n\x00")
                for key in ("model_id", "version")
            )
        ):
            raise ValueError("register must contain exactly a trimmed model_id and version")
        if raw_pipeline is not None:
            pipeline = PipelineIR.from_payload(raw_pipeline)
            if pipeline.schema not in {PIPELINE_SCHEMA_V2, PIPELINE_SCHEMA_V3}:
                raise ValueError("client supplied execution pipelines must use PipelineIR v2 or v3")
            supplied_parameters = dict(pipeline.parameters)
            if pipeline.schema == PIPELINE_SCHEMA_V3 and (
                "algorithm" in supplied_parameters or "preprocessor" in supplied_parameters
            ):
                raise ValueError(
                    "PipelineIR v3 algorithm and preprocessor choices belong in stage config"
                )
            supplied_algorithm = supplied_parameters.get("algorithm")
            supplied_preprocessor = supplied_parameters.get("preprocessor", "identity")
            if supplied_algorithm is not None and (
                not supplied_algorithm or supplied_algorithm != supplied_algorithm.strip()
            ):
                raise ValueError("pipeline algorithm must be trimmed text")
            if not isinstance(supplied_preprocessor, str):
                raise ValueError("pipeline preprocessor must be text")
            bound_pipeline = self._labs.compile(
                WorkspaceId(workspace_id),
                lab_id,
                algorithm=supplied_algorithm,
                preprocessor=supplied_preprocessor,
            )
            bound_parameters = dict(bound_pipeline.parameters)
            if pipeline.schema == PIPELINE_SCHEMA_V3:
                stage_registry_digest = getattr(
                    self._coordinator._runner, "stage_registry_digest", None
                )
                if not isinstance(stage_registry_digest, str):
                    raise ValueError("execution runner cannot pin the PipelineIR v3 stage registry")
                bound_parameters["stage_registry_digest"] = stage_registry_digest
            if set(supplied_parameters) - set(bound_parameters) or any(
                bound_parameters.get(key) != value for key, value in supplied_parameters.items()
            ):
                raise ValueError("custom ML pipeline parameters do not match the submitted Lab")
            pipeline = PipelineIR(
                pipeline.nodes,
                tuple(sorted(bound_parameters.items())),
                pipeline.schema,
            )
        else:
            pipeline = self._labs.compile(
                WorkspaceId(workspace_id),
                lab_id,
                algorithm=algorithm,
                preprocessor=preprocessor,
                candidate_algorithms=(
                    tuple(candidate_algorithms) if candidate_algorithms is not None else None
                ),
                candidate_cluster_counts=(
                    tuple(candidate_cluster_counts)
                    if candidate_cluster_counts is not None
                    else None
                ),
                candidate_preprocessors=(
                    tuple(candidate_preprocessors) if candidate_preprocessors is not None else None
                ),
                selection_metric=selection_metric,
                selection_direction=selection_direction,
                register_model=(
                    (registration["model_id"], registration["version"])
                    if isinstance(registration, dict)
                    else None
                ),
            )
            if suite is not None:
                stage_registry_digest = getattr(
                    self._coordinator._runner, "stage_registry_digest", None
                )
                if not isinstance(stage_registry_digest, str):
                    raise ValueError("execution runner cannot pin the PipelineIR v3 stage registry")
                pipeline = _pipeline_with_quality_suite(
                    pipeline, suite, stage_registry_digest
                )
        validate_pipeline = getattr(self._coordinator._runner, "validate_pipeline", None)
        if not callable(validate_pipeline):
            raise ValueError("execution runner cannot validate ML pipelines")
        validate_pipeline(lab, pipeline)
        if any(node.kind == "register" for node in pipeline.nodes) and (
            self._registry is None
            or self._artifacts is None
            or not isinstance(self._coordinator._store, JobStoreExecutionStore)
        ):
            raise ValueError(
                "pipeline register stage requires durable execution, registry, and artifact storage"
            )
        # Parse and validate caller supplied graphs before loading potentially
        # large Lab snapshots; invalid pipelines must not pay input-resolution cost.
        rows = resolve_lab_rows(
            WorkspaceId(workspace_id), lab, body.get("rows"), self._dataset_resolver
        )
        if raw_pipeline is not None:
            pipeline = self._labs.put_pipeline(WorkspaceId(workspace_id), lab_id, pipeline)
        return self._coordinator.submit(workspace_id, run_id, lab, rows, pipeline).to_payload()

    def compare_trials(
        self,
        workspace_id: str | None = None,
        lab_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        del lab_id
        self._workspace(workspace_id, _kwargs)
        if not isinstance(body, dict) or set(body) - {"spec", "trials"}:
            raise ValueError("compare body must be an object")
        raw_spec = body.get("spec", {})
        raw_trials = body.get("trials")
        if (
            not isinstance(raw_spec, dict)
            or not isinstance(raw_trials, list)
            or len(raw_trials) > 1_000
        ):
            raise ValueError("compare requires spec and trials")
        if set(raw_spec) - {
            "mode",
            "parameters",
            "metric",
            "direction",
            "tie_breakers",
            "max_trials",
            "random_seed",
        }:
            raise ValueError("compare spec contains unknown fields")
        parameters = raw_spec.get("parameters", [])
        if not isinstance(parameters, list):
            raise ValueError("spec parameters must be an array")
        normalized: list[tuple[str, tuple[object, ...]]] = []
        for item in parameters:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("values"), list)
            ):
                raise ValueError("invalid search parameter")
            normalized.append((item["name"], tuple(item["values"])))
        spec = SearchSpec(
            mode=raw_spec.get("mode", "single"),
            parameters=tuple(normalized),
            metric=raw_spec.get("metric", "score"),
            direction=raw_spec.get("direction", "maximize"),
            tie_breakers=_parse_tie_breakers(raw_spec.get("tie_breakers", [])),
            max_trials=raw_spec.get("max_trials", 100),
            random_seed=raw_spec.get("random_seed", 17),
        )
        trials: list[Trial] = []
        for item in raw_trials:
            if (
                not isinstance(item, dict)
                or set(item) != {"parameters", "metrics"}
                or not isinstance(item.get("parameters"), dict)
                or not isinstance(item.get("metrics"), dict)
            ):
                raise ValueError("invalid trial")
            metrics = item["metrics"]
            trials.append(Trial.create(item["parameters"], metrics))
        return {
            "metric": spec.metric,
            "direction": spec.direction,
            "tie_breakers": [
                {"metric": metric, "direction": direction}
                for metric, direction in spec.tie_breakers
            ],
            "items": [trial.to_payload() for trial in rank_trials(spec, tuple(trials))],
        }

    def search_trials(
        self,
        workspace_id: str | None = None,
        lab_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
        if self._labs is None or lab_id is None:
            raise RuntimeError("ML Studio is not ready")
        lab_id = self._bounded_identifier(lab_id, "lab_id")
        if (
            not isinstance(body, dict)
            or set(body) - {"rows", "spec", "register"}
            or not isinstance(body.get("rows"), list)
        ):
            raise ValueError("search requires rows and spec")
        raw_spec = body.get("spec")
        if not isinstance(raw_spec, dict):
            raise ValueError("search requires a spec")
        if set(raw_spec) - {
            "mode",
            "parameters",
            "metric",
            "direction",
            "tie_breakers",
            "max_trials",
            "random_seed",
            "stop_policy",
        }:
            raise ValueError("spec contains unknown fields")
        parameters = raw_spec.get("parameters", [])
        if not isinstance(parameters, list):
            raise ValueError("spec parameters must be an array")
        normalized = tuple(
            (item["name"], tuple(item["values"]))
            for item in parameters
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("values"), list)
        )
        if len(normalized) != len(parameters):
            raise ValueError("invalid search parameter")
        spec = SearchSpec(
            mode=raw_spec.get("mode", "single"),
            parameters=normalized,
            metric=raw_spec.get("metric", "score"),
            direction=raw_spec.get("direction", "maximize"),
            tie_breakers=_parse_tie_breakers(raw_spec.get("tie_breakers", [])),
            max_trials=raw_spec.get("max_trials", 100),
            random_seed=raw_spec.get("random_seed", 17),
        )
        raw_stop_policy = raw_spec.get("stop_policy", {})
        if not isinstance(raw_stop_policy, dict) or set(raw_stop_policy) - {
            "max_trials",
            "patience",
            "min_improvement",
        }:
            raise ValueError("invalid Bayesian stop_policy")
        if raw_stop_policy and spec.mode != "bayesian":
            raise ValueError("stop_policy is supported only for Bayesian search")
        stop_policy = BayesianStopPolicy(
            max_trials=raw_stop_policy.get("max_trials", spec.max_trials),
            patience=raw_stop_policy.get("patience", 10),
            min_improvement=raw_stop_policy.get("min_improvement", 0.0),
        )
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        rows = resolve_lab_rows(
            WorkspaceId(workspace_id), lab, body["rows"], self._dataset_resolver
        )
        if lab.task not in {"classification", "regression"}:
            raise ValueError("hyperparameter search requires a supervised lab")
        if "metric" not in raw_spec:
            spec = replace(spec, metric="accuracy" if lab.task == "classification" else "r2")
        supported_metrics = (
            {"accuracy"} if lab.task == "classification" else {"r2", "mean_squared_error"}
        )
        requested_metrics = {spec.metric, *(name for name, _ in spec.tie_breakers)}
        if not requested_metrics.issubset(supported_metrics):
            raise ValueError(f"unsupported ranking metric for {lab.task} search")
        allowed_parameters = {"seed"}
        if lab.task == "classification":
            allowed_parameters.update({"C", "max_iter"})
        for name, values in spec.parameters:
            if name not in allowed_parameters:
                raise ValueError(f"unsupported search parameter {name!r} for {lab.task}")
            for value in values:
                if name == "seed":
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        raise ValueError("seed search values must be non-negative integers")
                elif name == "max_iter":
                    if (
                        not isinstance(value, int)
                        or isinstance(value, bool)
                        or not 1 <= value <= 100_000
                    ):
                        raise ValueError("max_iter search values must be integers from 1 to 100000")
                elif (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not 0 < value <= 1_000_000
                ):
                    raise ValueError("C search values must be finite numbers in (0, 1000000]")
        trials: list[Trial] = []
        registered: list[dict[str, object]] = []
        registration = body.get("register")
        if registration is not None and (self._registry is None or self._artifacts is None):
            raise ValueError("register requires ml_registry and artifact_store services")
        if registration is not None and (
            not isinstance(registration, dict)
            or set(registration) - {"model_id", "version_prefix"}
            or not isinstance(registration.get("model_id", lab.id), str)
            or not isinstance(registration.get("version_prefix", "trial"), str)
        ):
            raise ValueError("register must contain only model_id and version_prefix text")
        pending = list(spec.trials()[:1] if spec.mode == "bayesian" else spec.trials())
        seen_parameters: set[tuple[tuple[str, object], ...]] = set()
        while pending and len(trials) < spec.max_trials:
            parameters = pending.pop(0)
            signature = tuple(sorted(parameters.items()))
            if signature in seen_parameters:
                continue
            seen_parameters.add(signature)
            identity = Trial.create(parameters, {}, random_seed=spec.random_seed)
            candidate = lab
            if "seed" in parameters:
                if not isinstance(parameters["seed"], int) or isinstance(parameters["seed"], bool):
                    raise ValueError("seed trial parameter must be an integer")
                candidate = replace(lab, seed=parameters["seed"])
            else:
                candidate = replace(
                    lab, seed=derive_trial_seed(spec.random_seed, identity.trial_id)
                )
            effective_values: list[tuple[str, float | int]] = []
            for name, value in parameters.items():
                if name == "seed":
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("search parameters must be numeric")
                effective_values.append((name, value))
            effective = tuple(effective_values)
            result = self._runner.run(candidate, rows, effective)
            trial = Trial.create(
                parameters, dict(result.model.metrics), random_seed=spec.random_seed
            )
            trials.append(trial)
            if isinstance(registration, dict):
                model_id = registration.get("model_id", lab.id)
                version_prefix = registration.get("version_prefix", "trial")
                if (
                    not isinstance(model_id, str)
                    or not isinstance(version_prefix, str)
                    or not model_id.strip()
                    or not version_prefix.strip()
                    or model_id != model_id.strip()
                    or version_prefix != version_prefix.strip()
                    or len(model_id) > 256
                    or len(version_prefix) > 256
                    or any(char in model_id for char in "\r\n\x00")
                    or any(char in version_prefix for char in "\r\n\x00")
                ):
                    raise ValueError("register model_id and version_prefix must be strings")
                from studio_core.ml import ExperimentId, MLRunId, ModelId, ModelVersion

                if lab.task not in {"classification", "regression"}:
                    raise ValueError("model registration requires a supervised lab")
                if self._registry is None or self._artifacts is None:
                    raise RuntimeError("model registration requires registry and artifact store")
                training_spec = TrainingSpec(
                    task=cast(Literal["classification", "regression"], lab.task),
                    algorithm="logistic_regression"
                    if lab.task == "classification"
                    else "linear_regression",
                    features=tuple(
                        feature.column for feature in lab.features if feature.role != "ignored"
                    ),
                    target=lab.target or "",
                    test_fraction=lab.test_fraction,
                    random_seed=candidate.seed,
                    parameters=effective,
                )
                registered_model = train_register_tabular(
                    self._registry,
                    self._artifacts,
                    WorkspaceId(workspace_id),
                    rows,
                    dataset=lab.dataset,
                    experiment_id=ExperimentId(lab.id),
                    run_id=MLRunId(f"{lab.id}-{trial.trial_id}"),
                    model_id=ModelId(model_id),
                    model_version=ModelVersion(f"{version_prefix}-{trial.trial_id}"),
                    source_revision="search",
                    execution_ref="ml-studio-search",
                    spec=training_spec,
                    now=_plugin_now(),
                    artifact_reference_barrier=self._artifact_reference_barrier,
                )
                registered.append(registered_model.to_payload())
            if spec.mode == "bayesian" and stop_policy.should_stop(spec, tuple(trials)):
                break
            if spec.mode == "bayesian" and len(trials) < spec.max_trials:
                pending.extend(propose_bayesian_candidates(spec, tuple(trials))[:1])
        response: dict[str, object] = {
            "metric": spec.metric,
            "direction": spec.direction,
            "tie_breakers": [
                {"metric": metric, "direction": direction}
                for metric, direction in spec.tie_breakers
            ],
            "items": [trial.to_payload() for trial in rank_trials(spec, tuple(trials))],
        }
        if registered:
            response["registered"] = registered
        return response

    def execution_status(
        self, run_id: str, workspace_id: str | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
        run_id = self._bounded_identifier(run_id, "run_id")
        return self._coordinator.status(workspace_id, run_id).to_payload()

    def register_execution_model(
        self,
        run_id: str,
        workspace_id: str | None = None,
        *,
        body: object | None = None,
        snapshot_override: ExecutionSnapshot | None = None,
        result_override: dict[str, object] | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        """Register a verified model artifact produced by a durable execution."""
        if self._registry is None or self._artifacts is None or self._labs is None:
            raise RuntimeError("model registration requires registry, artifact store and labs")
        run_id = self._bounded_identifier(run_id, "run_id")
        workspace_id = self._workspace(workspace_id, _kwargs)
        if (
            not isinstance(body, dict)
            or set(body) != {"model_id", "version"}
            or not isinstance(body.get("model_id"), str)
            or not isinstance(body.get("version"), str)
            or not body["model_id"]
            or not body["version"]
            or body["model_id"] != body["model_id"].strip()
            or body["version"] != body["version"].strip()
            or len(body["model_id"]) > 256
            or len(body["version"]) > 256
            or any(char in body["model_id"] for char in "\r\n\x00")
            or any(char in body["version"] for char in "\r\n\x00")
        ):
            raise ValueError("registration requires bounded model_id and version text")
        from studio_core.ml import (
            Experiment,
            ExperimentId,
            MetricValue,
            MLRunId,
            MLRunRecord,
            ModelId,
            ModelSignature,
            ModelVersion,
            RegisteredModelVersion,
        )

        if snapshot_override is None:
            snapshot = self._coordinator.status(workspace_id, run_id)
            if snapshot.state != "succeeded" or not isinstance(snapshot.result_payload, dict):
                raise ValueError(
                    "only a succeeded execution with a materialized model can be registered"
                )
            result = snapshot.result_payload
        else:
            if (
                snapshot_override.workspace_id != workspace_id
                or snapshot_override.run_id != run_id
                or result_override is None
            ):
                raise ValueError("pipeline registration context does not match its execution")
            snapshot = snapshot_override
            result = result_override
        required = {
            "task",
            "algorithm",
            "features",
            "artifact_ref",
            "artifact_digest",
            "artifact_media_type",
            "artifact_size_bytes",
        }
        if not required.issubset(result):
            raise ValueError("execution result does not contain a registrable model artifact")
        features = result["features"]
        artifact_ref = result["artifact_ref"]
        raw_digest = result["artifact_digest"]
        digest = raw_digest.removeprefix("sha256:") if isinstance(raw_digest, str) else raw_digest
        media_type = result["artifact_media_type"]
        size_bytes = result["artifact_size_bytes"]
        task = result["task"]
        algorithm = result["algorithm"]
        backend_id = result.get("backend_id")
        if (
            not isinstance(features, list)
            or not features
            or len(features) > 256
            or not all(isinstance(name, str) for name in features)
            or not all(
                name and name == name.strip() and len(name) <= 256 and not any(
                    char in name for char in "\r\n\x00"
                )
                for name in features
            )
            or not isinstance(artifact_ref, str)
            or not artifact_ref
            or artifact_ref != artifact_ref.strip()
            or len(artifact_ref) > 512
            or any(char in artifact_ref for char in "\r\n\x00")
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(media_type, str)
            or not media_type
            or media_type != media_type.strip()
            or len(media_type) > 256
            or any(char in media_type for char in "\r\n\x00")
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 1
            or size_bytes > 64 * 1024 * 1024
            or not isinstance(task, str)
            or task not in {"classification", "regression", "clustering"}
            or not isinstance(algorithm, str)
            or not algorithm
            or algorithm != algorithm.strip()
            or len(algorithm) > 256
            or any(char in algorithm for char in "\r\n\x00")
            or not isinstance(backend_id, str)
            or not backend_id
            or backend_id != backend_id.strip()
            or len(backend_id) > 256
            or any(char in backend_id for char in "\r\n\x00")
        ):
            raise ValueError("execution model artifact metadata is invalid")
        if not hasattr(self._artifacts, "get_bytes_by_storage_ref"):
            raise ValueError("artifact store does not support verified storage references")
        artifact = self._artifacts.get_bytes_by_storage_ref(artifact_ref, digest=digest)
        if len(artifact) != size_bytes or hashlib.sha256(artifact).hexdigest() != digest:
            raise ValueError("execution model artifact failed integrity verification")

        lab = self._labs.get(WorkspaceId(workspace_id), snapshot.lab_id)
        expected_features = tuple(
            feature.column for feature in lab.features if feature.role != "ignored"
        )
        if (
            lab.digest != snapshot.lab_digest
            or lab.task != task
            or lab.id != result.get("lab_id")
            or lab.backend_id != backend_id
            or tuple(features) != expected_features
        ):
            raise ValueError("execution Lab identity does not match its model result")
        rows_value = json.loads(snapshot.rows_json) if snapshot.rows_json is not None else None
        if (
            not isinstance(rows_value, list)
            or not rows_value
            or not all(isinstance(row, dict) for row in rows_value)
        ):
            raise ValueError("execution input snapshot is unavailable for model signature")
        rows = cast(list[dict[str, object]], rows_value)
        from .service import _input_signature, _output_signature

        if task == "clustering":
            inertia = result.get("inertia")
            if (
                media_type != "application/vnd.ronin.ml-kmeans+json"
                or algorithm != "kmeans"
                or not isinstance(inertia, (int, float))
                or isinstance(inertia, bool)
            ):
                raise ValueError("clustering result has an unsupported model artifact type")
            signature = ModelSignature(
                _input_signature(rows, tuple(features)), (("cluster", "int64"),)
            )
            metrics: tuple[MetricValue, ...] = (MetricValue("inertia", float(inertia)),)
            framework = "ronin-kmeans"
        else:
            if media_type != "application/vnd.ronin.sklearn-tabular+json":
                raise ValueError("supervised result has an unsupported model artifact type")
            target = result.get("target")
            if not isinstance(target, str) or target != lab.target:
                raise ValueError("supervised execution result is missing its target")
            signature = ModelSignature(
                _input_signature(rows, tuple(features)), _output_signature(task, target)
            )
            raw_metrics = result.get("metrics")
            if isinstance(raw_metrics, dict):
                metric_items = list(raw_metrics.items())
            elif isinstance(raw_metrics, list):
                try:
                    metric_items = [(str(pair[0]), float(pair[1])) for pair in raw_metrics]
                except (IndexError, TypeError, ValueError, OverflowError) as exc:
                    raise ValueError("execution metrics are invalid") from exc
            else:
                raise ValueError("supervised execution result is missing metrics")
            try:
                metrics = tuple(
                    MetricValue(str(name), float(value)) for name, value in metric_items
                )
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("execution metrics are invalid") from exc
            framework = "sklearn"
        model_id = ModelId(body["model_id"])
        model_version = ModelVersion(body["version"])
        ml_run_id = MLRunId(run_id)
        experiment_id = ExperimentId(lab.id)
        workspace = WorkspaceId(workspace_id)
        existing = self._registry.get_model(workspace, model_id, model_version)
        if existing is not None:
            if (
                existing.artifact_ref != artifact_ref
                or existing.artifact_digest != digest
                or existing.framework != framework
                or existing.signature != signature
            ):
                raise ValueError("model version already exists with different execution output")
            return existing.to_payload()
        self._registry.put_experiment(
            workspace,
            Experiment(experiment_id, lab.name, lab.project_id),
            now=_plugin_now(),
        )
        record = MLRunRecord(
            ml_run_id,
            experiment_id,
            f"ml-studio-execution:{run_id}",
            lab.digest,
            (lab.dataset,),
            parameters=(("algorithm", algorithm), ("backend_id", backend_id), ("task", task)),
            metrics=metrics,
            artifact_refs=(artifact_ref,),
        )
        self._registry.record_run(workspace, record, now=_plugin_now())
        requested = RegisteredModelVersion(
            model_id, model_version, ml_run_id, artifact_ref, digest, framework, signature
        )
        try:
            registered = self._registry.register_model(workspace, requested, now=_plugin_now())
        except Exception:
            existing = self._registry.get_model(workspace, model_id, model_version)
            if (
                existing is None
                or existing.artifact_ref != artifact_ref
                or existing.artifact_digest != digest
                or existing.framework != framework
                or existing.signature != signature
            ):
                raise
            registered = existing
        return registered.to_payload()

    def _finalize_pipeline_registration(
        self, snapshot: ExecutionSnapshot, result: dict[str, object]
    ) -> dict[str, object]:
        if snapshot.pipeline_json is None:
            raise ValueError("pipeline registration requires a pinned PipelineIR")
        pipeline = PipelineIR.from_json(snapshot.pipeline_json)
        registration_nodes = [node for node in pipeline.nodes if node.kind == "register"]
        if len(registration_nodes) != 1:
            raise ValueError("pipeline registration stage is missing or ambiguous")
        registered = self.register_execution_model(
            snapshot.run_id,
            snapshot.workspace_id,
            body=dict(registration_nodes[0].config),
            snapshot_override=snapshot,
            result_override=result,
        )
        return {**result, "registered_model": registered}

    def cancel_execution(
        self, run_id: str, workspace_id: str | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
        run_id = self._bounded_identifier(run_id, "run_id")
        return self._coordinator.cancel(workspace_id, run_id).to_payload()

    def retry_execution(
        self,
        run_id: str,
        workspace_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
        run_id = self._bounded_identifier(run_id, "run_id")
        if (
            not isinstance(body, dict)
            or set(body) != {"run_id", "from_stage"}
            or not isinstance(body.get("run_id"), str)
            or not isinstance(body.get("from_stage"), str)
            or not body["run_id"]
            or not body["run_id"].strip()
            or body["run_id"] != body["run_id"].strip()
            or len(body["run_id"]) > 256
            or any(char in body["run_id"] for char in "\r\n\x00")
            or not body["from_stage"]
            or not body["from_stage"].strip()
            or body["from_stage"] != body["from_stage"].strip()
            or len(body["from_stage"]) > 256
            or any(char in body["from_stage"] for char in "\r\n\x00")
        ):
            raise ValueError("retry requires bounded run_id and from_stage text")
        return self._coordinator.retry(
            workspace_id, run_id, body["run_id"], body["from_stage"]
        ).to_payload()

    def create_experiment(
        self,
        workspace_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        """Create an immutable experiment identity in the workspace registry."""
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        if not isinstance(body, dict):
            raise ValueError("experiment body is required")
        from studio_core.ml import Experiment

        experiment = Experiment.from_payload(body)
        workspace = WorkspaceId(workspace_id)
        existing = self._registry.get_experiment(workspace, experiment.id)
        if existing is not None:
            if existing != experiment:
                raise PluginRouteConflict(
                    f"experiment id already exists with a different definition: {experiment.id}"
                )
            stored = existing
        else:
            try:
                stored = self._registry.put_experiment(workspace, experiment, now=_plugin_now())
            except ValueError as exc:
                raise PluginRouteConflict(str(exc)) from exc
        return {
            "status": "created",
            "contract": "ml-studio/experiment/v1",
            **stored.to_payload(),
        }

    def list_experiments(
        self, workspace_id: str | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        return {
            "items": [
                experiment.to_payload()
                for experiment in self._registry.list_experiments(WorkspaceId(workspace_id))
            ]
        }

    def get_experiment(
        self,
        experiment_id: str,
        workspace_id: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
        workspace_id = self._workspace(workspace_id, _kwargs)
        experiment_id = self._bounded_identifier(experiment_id, "experiment_id")
        from studio_core.ml import ExperimentId

        experiment = self._registry.get_experiment(
            WorkspaceId(workspace_id), ExperimentId(experiment_id)
        )
        if experiment is None:
            raise KeyError(experiment_id)
        return experiment.to_payload()


def factory() -> MachineLearningStudioPlugin:
    return MachineLearningStudioPlugin()
