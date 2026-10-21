"""Machine Learning Studio vertical plugin boundary."""
# ruff: noqa: E501, E701

import base64
import hashlib
import json
from dataclasses import replace
from typing import Any, Literal, cast
from urllib.parse import parse_qs

from studio_core import WorkspaceId
from studio_core.plugins import PluginContext, PluginManifest, SurfaceContribution
from studio_storage.ports import ArtifactStore

from .backends import default_backends
from .datasets import DatasetResolver, resolve_lab_rows
from .domain import Lab
from .optimization import (
    SearchSpec,
    Trial,
    derive_trial_seed,
    propose_bayesian_candidates,
    rank_trials,
)
from .orchestration import JobStoreExecutionStore, LocalExecutionCoordinator
from .ports import MLLabStore
from .quality import profile_and_validate
from .runner import LocalExperimentRunner
from .runtime import TrainingSpec
from .service import (
    MLRegistryStore,
    persist_clustering_result,
    persist_experiment_result,
    predict_registered_tabular,
    register_clustering_model,
    train_register_tabular,
)
from .services import InMemoryMLLabStore, LabService


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
        ),
        permissions=("ml-studio:read", "ml-studio:write", "ml-studio:execute"),
        ui_entry="ml-studio",
        surface_ids=(
            "ml-studio.backends.v1",
            "ml-studio.labs.v1",
            "ml-studio.run.v1",
            "ml-studio.models.v1",
        ),
    )

    def __init__(self) -> None:
        self._labs: LabService | None = None
        self._runner = LocalExperimentRunner()
        self._coordinator = LocalExecutionCoordinator(self._runner)
        self._registry: MLRegistryStore | None = None
        self._artifacts: ArtifactStore | None = None
        self._dataset_resolver: DatasetResolver | None = None

    def register(self, context: PluginContext) -> None:
        store = context.services.get("ml_lab_store")
        if store is None:
            store = InMemoryMLLabStore()
        self._labs = LabService(cast(MLLabStore, store))
        coordinator_runner = self._coordinator._runner
        self._coordinator.close()
        self._artifacts = cast(ArtifactStore | None, context.services.get("artifact_store"))
        execution_service = context.services.get("ml_execution_service")
        execution_store = (
            JobStoreExecutionStore(cast(Any, execution_service), self._artifacts)
            if execution_service is not None
            else None
        )
        self._coordinator = LocalExecutionCoordinator(
            coordinator_runner, store=execution_store, autostart=False
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

    def startup(self) -> None:
        self._coordinator.start()

    def shutdown(self) -> None:
        self._coordinator.close()

    def backends(self, *_args: Any, **_kwargs: Any) -> dict[str, object]:
        items = []
        for backend in default_backends():
            capabilities = getattr(backend, "capabilities", None)
            item: dict[str, object] = {
                "id": backend.backend_id,
                "name": backend.display_name,
                "status": "available",
            }
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
        if not model_id or not version:
            raise ValueError("model_id and version are required")
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("reason"), str)
            or not body["reason"].strip()
        ):
            raise ValueError("promotion reason is required")
        from studio_core.ml import ModelId, ModelVersion

        model = self._registry.promote_model(
            WorkspaceId(workspace_id), ModelId(model_id), ModelVersion(version), now="plugin"
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
        if not model_id or not version or not isinstance(body, dict):
            raise ValueError("model, version and body are required")
        encoded = body.get("artifact_base64")
        rows = body.get("rows")
        from studio_core.ml import ModelId, ModelVersion

        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("predict requires rows")
        model = self._registry.get_model(
            WorkspaceId(workspace_id), ModelId(model_id), ModelVersion(version)
        )
        if model is None:
            raise KeyError(f"{model_id}@{version}")
        if isinstance(encoded, str):
            try:
                artifact = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise ValueError("artifact_base64 is invalid") from exc
        elif self._artifacts is not None and hasattr(self._artifacts, "get_bytes_by_storage_ref"):
            artifact = self._artifacts.get_bytes_by_storage_ref(
                model.artifact_ref, digest=model.artifact_digest
            )
        else:
            raise ValueError("artifact_base64 is required when artifact store is unavailable")

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
        if not isinstance(body, dict) or not isinstance(body.get("batch_id"), str):
            raise ValueError("batch_id is required for batch prediction")
        batch_id = body["batch_id"].strip()
        if not batch_id or len(batch_id) > 256 or any(char in batch_id for char in "\r\n\x00"):
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
                    json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
        if not model_id or not version:
            raise ValueError("model_id and version are required")
        from studio_core.ml import ModelId, ModelVersion

        model = self._registry.get_model(
            WorkspaceId(workspace_id), ModelId(model_id), ModelVersion(version)
        )
        if model is None:
            raise KeyError(f"{model_id}@{version}")
        return {
            "schema": "ronin.ml-model-card/v1",
            "identity": {"model_id": model_id, "version": version, "stage": model.stage},
            "provenance": {
                "source_run_id": model.source_run_id.value,
                "artifact_ref": model.artifact_ref,
                "artifact_digest": model.artifact_digest,
            },
            "framework": model.framework,
            "signature": model.signature.to_payload(),
            "limitations": ["Review dataset quality and evaluation evidence before promotion."],
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
        workspace_id = self._workspace(workspace_id, _kwargs)
        raw_query = _kwargs.get("query")
        query = parse_qs(raw_query if isinstance(raw_query, str) else "", keep_blank_values=True)
        if set(query) - {"workspace_id", "offset", "length"} or any(
            len(values) != 1 for values in query.values()
        ):
            raise ValueError("artifact query contains unknown or duplicate parameters")

        def query_int(name: str, default: int) -> int:
            value = query.get(name, [str(default)])[0]
            if not value.isascii() or not value.isdecimal():
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

    def list_labs(self, workspace_id: str, **_kwargs: Any) -> dict[str, object]:
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        return {"items": [lab.to_payload() for lab in self._labs.list(WorkspaceId(workspace_id))]}

    @staticmethod
    def _workspace(workspace_id: str | None, kwargs: dict[str, Any]) -> str:
        if workspace_id:
            return workspace_id
        query = str(kwargs.get("query", ""))
        value = parse_qs(query).get("workspace_id", [None])[0]
        if not value:
            raise ValueError("workspace_id is required")
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
        return self._labs.get(WorkspaceId(workspace_id), lab_id).to_payload()

    def compile_lab(self, workspace_id: str, lab_id: str, **_kwargs: Any) -> dict[str, object]:
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        return self._labs.compile(WorkspaceId(workspace_id), lab_id).to_payload()

    def run_lab(
        self, workspace_id: str, lab_id: str, *, body: object | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        if not isinstance(body, dict) or set(body) - {
            "rows",
            "run_id",
            "execution_ref",
            "source_revision",
        }:
            raise ValueError("run body has invalid shape")
        if "rows" in body and body["rows"] is None:
            raise ValueError("run rows must be an array when provided")
        if "rows" in body and (
            not isinstance(body["rows"], list)
            or not all(isinstance(row, dict) for row in body["rows"])
        ):
            raise ValueError("run rows must be an array of objects")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
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
                    run_id=MLRunId(str(body.get("run_id", f"run-{lab_id}"))),
                    execution_ref=str(body.get("execution_ref", "ml-studio-local")),
                    source_revision=str(body.get("source_revision", "local")),
                    now="plugin",
                )
                payload["run"] = run.to_payload()
                registration = body.get("register")
                if registration is not None:
                    if not isinstance(registration, dict):
                        raise ValueError("register must be an object")
                    from studio_core.ml import ModelId, ModelVersion

                    model = register_clustering_model(
                        self._registry,
                        self._artifacts,
                        WorkspaceId(workspace_id),
                        lab,
                        result,
                        run_id=MLRunId(run.id.value),
                        model_id=ModelId(str(registration.get("model_id", lab.id))),
                        model_version=ModelVersion(str(registration.get("version", "candidate-1"))),
                        now="plugin",
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
                run_id=MLRunId(str(body.get("run_id", f"run-{lab_id}"))),
                execution_ref=str(body.get("execution_ref", "ml-studio-local")),
                source_revision=str(body.get("source_revision", "local")),
                now="plugin",
            )
            payload["run"] = run.to_payload()
        return payload

    def get_run(self, workspace_id: str, run_id: str, **_kwargs: Any) -> dict[str, object]:
        if self._registry is None:
            raise RuntimeError("ML registry is unavailable")
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
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        if not isinstance(body, dict) or set(body) - {"rows"}:
            raise ValueError("quality body must contain optional rows only")
        if "rows" in body and body["rows"] is None:
            raise ValueError("quality rows must be an array when provided")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        rows = resolve_lab_rows(
            WorkspaceId(workspace_id), lab, body.get("rows"), self._dataset_resolver
        )
        return profile_and_validate(lab, rows).to_payload()

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
        if self._labs is None:
            raise RuntimeError("ML Studio is not ready")
        if not isinstance(body, dict) or set(body) - {
            "run_id",
            "rows",
            "algorithm",
            "preprocessor",
            "candidate_algorithms",
            "candidate_cluster_counts",
            "selection_metric",
            "selection_direction",
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
        ):
            raise ValueError("execution run_id must be 1 to 256 characters of trimmed text")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        algorithm = body.get("algorithm")
        if algorithm is not None and (
            not isinstance(algorithm, str) or not algorithm or algorithm != algorithm.strip()
        ):
            raise ValueError("algorithm must be a non-empty trimmed string")
        candidate_algorithms = body.get("candidate_algorithms")
        if candidate_algorithms is not None and (
            not isinstance(candidate_algorithms, list)
            or not all(
                isinstance(item, str) and item and item == item.strip()
                for item in candidate_algorithms
            )
        ):
            raise ValueError("candidate_algorithms must be an array of trimmed algorithm names")
        candidate_cluster_counts = body.get("candidate_cluster_counts")
        if candidate_cluster_counts is not None and (
            not isinstance(candidate_cluster_counts, list)
            or any(
                not isinstance(item, int) or isinstance(item, bool)
                for item in candidate_cluster_counts
            )
        ):
            raise ValueError("candidate_cluster_counts must be an array of integers")
        selection_metric = body.get("selection_metric")
        if selection_metric is not None and (
            not isinstance(selection_metric, str)
            or not selection_metric
            or selection_metric != selection_metric.strip()
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
        if lab.task == "clustering" and preprocessor != "identity":
            raise ValueError("preprocessor is not supported for clustering Labs")
        rows = resolve_lab_rows(
            WorkspaceId(workspace_id), lab, body.get("rows"), self._dataset_resolver
        )
        pipeline = self._labs.compile(
            WorkspaceId(workspace_id),
            lab_id,
            algorithm=algorithm,
            preprocessor=preprocessor,
            candidate_algorithms=(
                tuple(candidate_algorithms) if candidate_algorithms is not None else None
            ),
            candidate_cluster_counts=(
                tuple(candidate_cluster_counts) if candidate_cluster_counts is not None else None
            ),
            selection_metric=selection_metric,
            selection_direction=selection_direction,
        )
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
        if not isinstance(body, dict):
            raise ValueError("compare body must be an object")
        raw_spec = body.get("spec", {})
        raw_trials = body.get("trials")
        if not isinstance(raw_spec, dict) or not isinstance(raw_trials, list):
            raise ValueError("compare requires spec and trials")
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
            max_trials=raw_spec.get("max_trials", 100),
            random_seed=raw_spec.get("random_seed", 17),
        )
        trials: list[Trial] = []
        for item in raw_trials:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("parameters"), dict)
                or not isinstance(item.get("metrics"), dict)
            ):
                raise ValueError("invalid trial")
            metrics = item["metrics"]
            if not all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in metrics.values()
            ):
                raise ValueError("trial metrics must be numeric")
            trials.append(
                Trial.create(
                    item["parameters"], {key: float(value) for key, value in metrics.items()}
                )
            )
        return {
            "metric": spec.metric,
            "direction": spec.direction,
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
        if not isinstance(body, dict) or not isinstance(body.get("rows"), list):
            raise ValueError("search requires rows and spec")
        raw_spec = body.get("spec")
        if not isinstance(raw_spec, dict):
            raise ValueError("search requires a spec")
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
            max_trials=raw_spec.get("max_trials", 100),
            random_seed=raw_spec.get("random_seed", 17),
        )
        rows = body["rows"]
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError("search rows must be objects")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        if lab.task not in {"classification", "regression"}:
            raise ValueError("hyperparameter search requires a supervised lab")
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
        if registration is not None and not isinstance(registration, dict):
            raise ValueError("register must be an object")
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
                if not isinstance(model_id, str) or not isinstance(version_prefix, str):
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
                    now="plugin",
                )
                registered.append(registered_model.to_payload())
            if spec.mode == "bayesian" and len(trials) < spec.max_trials:
                pending.extend(propose_bayesian_candidates(spec, tuple(trials)))
        response: dict[str, object] = {
            "metric": spec.metric,
            "direction": spec.direction,
            "items": [trial.to_payload() for trial in rank_trials(spec, tuple(trials))],
        }
        if registered:
            response["registered"] = registered
        return response

    def execution_status(
        self, run_id: str, workspace_id: str | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
        return self._coordinator.status(workspace_id, run_id).to_payload()

    def register_execution_model(
        self,
        run_id: str,
        workspace_id: str | None = None,
        *,
        body: object | None = None,
        **_kwargs: Any,
    ) -> dict[str, object]:
        """Register a verified model artifact produced by a durable execution."""
        if self._registry is None or self._artifacts is None or self._labs is None:
            raise RuntimeError("model registration requires registry, artifact store and labs")
        workspace_id = self._workspace(workspace_id, _kwargs)
        if (
            not isinstance(body, dict)
            or set(body) != {"model_id", "version"}
            or not isinstance(body.get("model_id"), str)
            or not isinstance(body.get("version"), str)
        ):
            raise ValueError("registration requires exactly model_id and version")
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

        snapshot = self._coordinator.status(workspace_id, run_id)
        if snapshot.state != "succeeded" or not isinstance(snapshot.result_payload, dict):
            raise ValueError(
                "only a succeeded execution with a materialized model can be registered"
            )
        result = snapshot.result_payload
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
        digest = result["artifact_digest"]
        media_type = result["artifact_media_type"]
        size_bytes = result["artifact_size_bytes"]
        task = result["task"]
        algorithm = result["algorithm"]
        backend_id = result.get("backend_id")
        if (
            not isinstance(features, list)
            or not features
            or not all(isinstance(name, str) for name in features)
            or not isinstance(artifact_ref, str)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(media_type, str)
            or not isinstance(size_bytes, int)
            or isinstance(size_bytes, bool)
            or size_bytes < 1
            or size_bytes > 64 * 1024 * 1024
            or not isinstance(task, str)
            or task not in {"classification", "regression", "clustering"}
            or not isinstance(algorithm, str)
            or not isinstance(backend_id, str)
            or not backend_id
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
                except (IndexError, TypeError, ValueError) as exc:
                    raise ValueError("execution metrics are invalid") from exc
            else:
                raise ValueError("supervised execution result is missing metrics")
            try:
                metrics = tuple(
                    MetricValue(str(name), float(value)) for name, value in metric_items
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("execution metrics are invalid") from exc
            framework = "sklearn"
        model_id = ModelId(body["model_id"])
        model_version = ModelVersion(body["version"])
        ml_run_id = MLRunId(run_id)
        experiment_id = ExperimentId(lab.id)
        self._registry.put_experiment(
            WorkspaceId(workspace_id),
            Experiment(experiment_id, lab.name, lab.project_id),
            now="plugin",
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
        self._registry.record_run(WorkspaceId(workspace_id), record, now="plugin")
        registered = self._registry.register_model(
            WorkspaceId(workspace_id),
            RegisteredModelVersion(
                model_id, model_version, ml_run_id, artifact_ref, digest, framework, signature
            ),
            now="plugin",
        )
        return registered.to_payload()

    def cancel_execution(
        self, run_id: str, workspace_id: str | None = None, **_kwargs: Any
    ) -> dict[str, object]:
        workspace_id = self._workspace(workspace_id, _kwargs)
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
        if (
            not isinstance(body, dict)
            or set(body) != {"run_id", "from_stage"}
            or not isinstance(body.get("run_id"), str)
            or not isinstance(body.get("from_stage"), str)
        ):
            raise ValueError("retry requires exactly run_id and from_stage")
        return self._coordinator.retry(
            workspace_id, run_id, body["run_id"], body["from_stage"]
        ).to_payload()

    def create_experiment(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {"status": "accepted", "contract": "ml-studio/experiment/v1"}


def factory() -> MachineLearningStudioPlugin:
    return MachineLearningStudioPlugin()
