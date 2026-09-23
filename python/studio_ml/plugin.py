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
from .domain import Lab
from .optimization import SearchSpec, Trial, propose_bayesian_candidates, rank_trials
from .orchestration import ExecutionStore, LocalExecutionCoordinator
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
from .ports import MLLabStore
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

    def register(self, context: PluginContext) -> None:
        store = context.services.get("ml_lab_store")
        if store is None:
            store = InMemoryMLLabStore()
        self._labs = LabService(cast(MLLabStore, store))
        execution_store = context.services.get("ml_execution_store")
        if execution_store is not None:
            self._coordinator.close()
            self._coordinator = LocalExecutionCoordinator(
                self._runner, store=cast(ExecutionStore, execution_store)
            )
        self._registry = cast(MLRegistryStore | None, context.services.get("ml_registry"))
        self._artifacts = cast(ArtifactStore | None, context.services.get("artifact_store"))
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
            "/v1/ml-studio/executions/{run_id}/cancel",
            context.plugin_id,
            self.cancel_execution,
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

    def startup(self) -> None:
        pass

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
        rows = body.get("rows")
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("run rows must be an array of objects")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
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
        if not isinstance(body, dict) or not isinstance(body.get("rows"), list):
            raise ValueError("quality body must contain rows array")
        if not all(isinstance(row, dict) for row in body["rows"]):
            raise ValueError("quality rows must be objects")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        return profile_and_validate(lab, body["rows"]).to_payload()

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
        if not isinstance(body, dict) or not isinstance(body.get("rows"), list):
            raise ValueError("execution body must contain rows array")
        if not all(isinstance(row, dict) for row in body["rows"]):
            raise ValueError("execution rows must be objects")
        lab = self._labs.get(WorkspaceId(workspace_id), lab_id)
        return self._coordinator.submit(
            str(body.get("run_id", f"run-{lab_id}")), lab, body["rows"]
        ).to_payload()

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
            candidate = lab
            if "seed" in parameters:
                if not isinstance(parameters["seed"], int) or isinstance(parameters["seed"], bool):
                    raise ValueError("seed trial parameter must be an integer")
                candidate = replace(lab, seed=parameters["seed"])
            effective_values: list[tuple[str, float | int]] = []
            for name, value in parameters.items():
                if name == "seed":
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("search parameters must be numeric")
                effective_values.append((name, value))
            effective = tuple(effective_values)
            result = self._runner.run(candidate, rows, effective)
            trials.append(Trial.create(parameters, dict(result.model.metrics)))
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
                    run_id=MLRunId(f"{lab.id}-trial-{len(trials)}"),
                    model_id=ModelId(model_id),
                    model_version=ModelVersion(f"{version_prefix}-{len(trials)}"),
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

    def execution_status(self, run_id: str, **_kwargs: Any) -> dict[str, object]:
        return self._coordinator.status(run_id).to_payload()

    def cancel_execution(self, run_id: str, **_kwargs: Any) -> dict[str, object]:
        return self._coordinator.cancel(run_id).to_payload()

    def create_experiment(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
        return {"status": "accepted", "contract": "ml-studio/experiment/v1"}


def factory() -> MachineLearningStudioPlugin:
    return MachineLearningStudioPlugin()
