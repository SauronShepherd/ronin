"""Ronin plugin boundary for Synthetic Data Studio."""

import os
from typing import Any

from studio_core import AssetId, AssetRef, AssetVersion, WorkspaceId
from studio_core.plugins import PluginContext, PluginManifest
from studio_storage.catalog import SqliteCatalogStore

from studio_synthetic_data.application import GovernStudioService, plan_from_payload
from studio_synthetic_data.async_generation import LocalGenerationJobs
from studio_synthetic_data.engine import GenerationPlan, assess_privacy
from studio_synthetic_data.engine import validate as validate_plan
from studio_synthetic_data.formats import format_availability
from studio_synthetic_data.local_catalogs import (
    list_local_catalog_profiles,
    resolve_local_identifier,
)


class SyntheticDataStudioPlugin:
    manifest = PluginManifest(
        id="com.ronin.synthetic-data-studio",
        name="Synthetic Data Studio",
        version="0.1.0",
        plugin_api="1.0",
        host_requires=">=1,<2",
        capabilities=(
            "synthetic-data-studio.plan.v1",
            "synthetic-data-studio.generate.v1",
            "synthetic-data-studio.validate.v1",
            "synthetic-data-studio.export.v1",
            "synthetic-data-studio.jobs.v1",
        ),
        permissions=("synthetic:read", "synthetic:write", "synthetic:execute"),
    )

    def __init__(
        self, service: GovernStudioService | None = None, artifact_store: Any = None
    ) -> None:
        self.started = False
        # Hosts can inject a SqliteRunStore-backed service; ephemeral sessions use memory.
        self.service = service or GovernStudioService()
        self.artifact_store = artifact_store
        self.catalog_store: SqliteCatalogStore | None = None
        self.jobs = LocalGenerationJobs(self.service, db_path=os.getenv("SDS_JOBS_DB"))

    def register(self, context: PluginContext) -> None:
        injected_service = context.services.get("govern_studio_service")
        if isinstance(injected_service, GovernStudioService):
            self.service = injected_service
            self.jobs.close()
            self.jobs = LocalGenerationJobs(self.service, db_path=os.getenv("SDS_JOBS_DB"))
        if "artifact_store" in context.services:
            self.artifact_store = context.services["artifact_store"]
        injected_catalog = context.services.get("catalog_store")
        if isinstance(injected_catalog, SqliteCatalogStore):
            self.catalog_store = injected_catalog
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/formats",
            context.plugin_id,
            self.formats,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/health",
            context.plugin_id,
            self.health,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/synthetic-data-studio/plans",
            context.plugin_id,
            self.create_plan,
            permission="synthetic:write",
        )
        context.contributions.add_route(
            "POST",
            "/v1/synthetic-data-studio/generate",
            context.plugin_id,
            self.generate,
            permission="synthetic:execute",
        )
        context.contributions.add_route("POST", "/v1/synthetic-data-studio/generate/async", context.plugin_id, self.generate_async, permission="synthetic:execute")
        context.contributions.add_route("GET", "/v1/synthetic-data-studio/jobs/{job_id}", context.plugin_id, self.get_generation_job, permission="synthetic:read")
        context.contributions.add_route("POST", "/v1/synthetic-data-studio/jobs/{job_id}/cancel", context.plugin_id, self.cancel_generation_job, permission="synthetic:execute")
        context.contributions.add_route(
            "POST",
            "/v1/synthetic-data-studio/validate",
            context.plugin_id,
            self.validate,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/runs/{run_id}",
            context.plugin_id,
            self.get_run,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/runs",
            context.plugin_id,
            self.list_runs,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/synthetic-data-studio/export",
            context.plugin_id,
            self.export,
            permission="synthetic:execute",
        )
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/catalog/assets",
            context.plugin_id,
            self.list_assets,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/catalog/providers",
            context.plugin_id,
            self.catalog_providers,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "POST",
            "/v1/synthetic-data-studio/catalog/resolve",
            context.plugin_id,
            self.resolve_catalog_identifier,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "GET", "/v1/synthetic-data-studio/catalog/namespaces", context.plugin_id,
            self.list_catalog_namespaces, permission="synthetic:read"
        )
        context.contributions.add_route(
            "POST", "/v1/synthetic-data-studio/catalog/namespaces", context.plugin_id,
            self.register_catalog_namespace, permission="synthetic:write"
        )
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/catalog/assets/{asset_id}",
            context.plugin_id,
            self.get_asset,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/catalog/assets/{asset_id}/lineage",
            context.plugin_id,
            self.get_lineage,
            permission="synthetic:read",
        )
        context.contributions.add_route(
            "GET",
            "/v1/synthetic-data-studio/catalog/assets/{asset_id}/revisions",
            context.plugin_id,
            self.list_revisions,
            permission="synthetic:read",
        )

    def startup(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.started = False
        self.jobs.close()

    def create_plan(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        plan = _decode_plan(body)
        key = str(_kwargs.get("idempotency_key", "plan"))
        run = self.service.create_run(plan, idempotency_key=key)
        return {
            "status": "completed" if run.result else "failed",
            "run_id": run.run_id,
            "planFingerprint": run.plan_fingerprint,
            "tables": [table.name for table in plan.tables],
        }

    def formats(self, *_args: Any, **_kwargs: Any) -> list[dict[str, object]]:
        return [
            {
                "format_id": item.format_id,
                "status": item.status,
                "missing_dependencies": item.missing_dependencies,
                "reason": item.reason,
            }
            for item in format_availability()
        ]

    def health(self, **_kwargs: Any) -> dict[str, object]:
        checks = {
            "service": "ready" if self.service is not None else "failed",
            "catalog": "ready" if self.catalog_store is not None else "degraded",
        }
        status = "ready" if all(value == "ready" for value in checks.values()) else "degraded"
        return {"plugin": self.manifest.id, "status": status, "checks": checks}

    def generate(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        plan = _decode_plan(body)
        run_id = str((body or {}).get("run_id", "")) if isinstance(body, dict) else ""
        if not run_id:
            run_id = self.service.create_run(
                plan, idempotency_key=str(_kwargs.get("idempotency_key", "generate"))
            ).run_id
        run = self.service.generate(run_id, plan)
        result = run.result
        generated_report = validate_plan(plan, result) if result else None
        return {
            "status": run.status,
            "run_id": run.run_id,
            "contract": "synthetic-data-studio/generation/v1",
            "planFingerprint": run.plan_fingerprint,
            "tables": [
                {"name": table.name, "rows": [dict(row) for row in table.rows]}
                for table in result.tables
            ]
            if result
            else [],
            "error": run.error,
            "validation": {
                "passed": generated_report.passed,
                "errors": list(generated_report.errors),
                "evidenceId": generated_report.evidence_id,
            }
            if generated_report
            else None,
            "privacy": assess_privacy(result, _source_sample(body)).to_payload() if result else None,
        }

    def generate_async(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        plan = _decode_plan(body)
        job = self.jobs.submit(plan, idempotency_key=str(_kwargs.get("idempotency_key", "async-generate")))
        return {"job_id": job.job_id, "run_id": job.run_id, "status": job.status, "contract": "synthetic-data-studio/jobs/v1"}

    def get_generation_job(self, *, job_id: str, **_kwargs: Any) -> dict[str, object]:
        job = self.jobs.get(job_id)
        return {"job_id": job.job_id, "run_id": job.run_id, "status": job.status, "error": job.error}

    def cancel_generation_job(self, *, job_id: str, **_kwargs: Any) -> dict[str, object]:
        job = self.jobs.cancel(job_id)
        return {"job_id": job.job_id, "run_id": job.run_id, "status": job.status, "error": job.error}

    def validate(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        plan = _decode_plan(body)
        if not isinstance(body, dict) or not body.get("run_id"):
            run_id = self.service.create_run(plan, idempotency_key="compat-validate").run_id
            self.service.generate(run_id, plan)
        else:
            run_id = str(body["run_id"])
        run = self.service.validate(run_id, plan)
        report = run.validation
        return {
            "status": run.status,
            "contract": "synthetic-data-studio/validation/v1",
            "checks": list(report.checks) if report else [],
            "errors": list(report.errors) if report else [],
            "evidenceId": report.evidence_id if report else None,
        }

    def get_run(self, *, run_id: str, **_kwargs: Any) -> dict[str, object]:
        run = self.service.get_run(run_id)
        return {
            "run_id": run.run_id,
            "status": run.status,
            "planFingerprint": run.plan_fingerprint,
            "error": run.error,
            "hasResult": run.result is not None,
            "hasValidation": run.validation is not None,
        }

    def list_runs(self, **_kwargs: Any) -> dict[str, object]:
        return {
            "items": [
                {
                    "run_id": run.run_id,
                    "status": run.status,
                    "planFingerprint": run.plan_fingerprint,
                    "error": run.error,
                    "hasResult": run.result is not None,
                    "hasValidation": run.validation is not None,
                }
                for run in self.service.snapshot()
            ]
        }

    def export(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        if not isinstance(body, dict) or not body.get("run_id"):
            raise ValueError("run_id is required for export")
        format_id = str(body.get("format_id", ""))
        table_name = str(body.get("table", ""))
        if not format_id or not table_name:
            raise ValueError("format_id and table are required for export")
        content = self.service.export(
            str(body["run_id"]), format_id=format_id, table_name=table_name
        )
        response: dict[str, object] = {
            "status": "completed",
            "contract": "synthetic-data-studio/export/v1",
            "run_id": str(body["run_id"]),
            "format_id": format_id,
            "table": table_name,
            "content": content,
        }
        if self.artifact_store is not None:
            ref = self.artifact_store.put_bytes(
                role=f"govern-studio/{body['run_id']}/{table_name}.{format_id}",
                data=content.encode("utf-8"),
                media_type=_media_type(format_id),
            )
            response["artifact"] = {
                "storage_ref": ref.storage_ref,
                "digest": ref.digest,
                "size_bytes": ref.size_bytes,
                "media_type": ref.media_type,
            }
        return response

    def list_assets(self, *, body: object | None = None, query: str | None = None, **_kwargs: Any) -> dict[str, object]:
        store, workspace_id = self._catalog_request(body, query)
        search = body.get("search") if isinstance(body, dict) else None
        if not isinstance(search, str) and query:
            from urllib.parse import parse_qs
            search = parse_qs(query).get("search", [None])[0]
        if isinstance(search, str) and search.strip():
            assets = store.search_assets(workspace_id, search)
        else:
            assets = store.list_assets(workspace_id)
        return {
            "items": [asset.to_payload() for asset in assets],
            "workspace_id": str(workspace_id),
            "search": search.strip() if isinstance(search, str) and search.strip() else None,
        }

    def catalog_providers(self, **_kwargs: Any) -> dict[str, object]:
        return {
            "mode": "local-only",
            "external_connections": False,
            "items": [profile.to_payload() for profile in list_local_catalog_profiles()],
        }

    def resolve_catalog_identifier(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        if not isinstance(body, dict):
            raise ValueError("body must be an object")
        provider_id = body.get("provider_id")
        identifier = body.get("identifier")
        if not isinstance(provider_id, str) or not isinstance(identifier, str):
            raise ValueError("provider_id and identifier are required")
        return {"provider_id": provider_id, "identifier": identifier, "namespace": resolve_local_identifier(provider_id, identifier)}

    def list_catalog_namespaces(self, *, body: object | None = None, query: str | None = None, **_kwargs: Any) -> dict[str, object]:
        store, workspace_id = self._catalog_request(body, query)
        provider = body.get("provider_id") if isinstance(body, dict) else None
        return {"workspace_id": str(workspace_id), "items": list(store.list_namespaces(workspace_id, provider_id=provider if isinstance(provider, str) else None))}

    def register_catalog_namespace(self, *, body: object | None = None, **_kwargs: Any) -> dict[str, object]:
        store, workspace_id = self._catalog_request(body)
        if not isinstance(body, dict) or not isinstance(body.get("provider_id"), str) or not isinstance(body.get("identifier"), str) or not isinstance(body.get("namespace"), dict):
            raise ValueError("workspace_id, provider_id, identifier and namespace are required")
        namespace = body["namespace"]
        if not all(isinstance(key, str) and isinstance(value, str) for key, value in namespace.items()):
            raise ValueError("namespace values must be strings")
        return store.register_namespace(workspace_id, provider_id=body["provider_id"], identifier=body["identifier"], namespace=namespace, now="2026-01-01T00:00:00.000000Z")

    def get_asset(self, *, asset_id: str, body: object | None = None, query: str | None = None, **_kwargs: Any) -> dict[str, object]:
        store, workspace_id = self._catalog_request(body, query)
        asset = store.get_asset(workspace_id, AssetId(asset_id))
        if asset is None:
            raise KeyError(asset_id)
        return {"asset": asset.to_payload(), "workspace_id": str(workspace_id)}

    def get_lineage(self, *, asset_id: str, body: object | None = None, query: str | None = None, **_kwargs: Any) -> dict[str, object]:
        store, workspace_id = self._catalog_request(body, query)
        version = body.get("version") if isinstance(body, dict) else None
        if not isinstance(version, str) and query:
            from urllib.parse import parse_qs
            version = parse_qs(query).get("version", [None])[0]
        if not isinstance(version, str):
            raise ValueError("body.version is required for lineage")
        ref = AssetRef(AssetId(asset_id), AssetVersion(version))
        return {
            "asset": ref.to_payload(),
            "upstream": [edge.to_payload() for edge in store.upstream(workspace_id, ref)],
            "downstream": [edge.to_payload() for edge in store.downstream(workspace_id, ref)],
        }

    def list_revisions(self, *, asset_id: str, body: object | None = None, query: str | None = None, **_kwargs: Any) -> dict[str, object]:
        store, workspace_id = self._catalog_request(body, query)
        return {
            "asset_id": asset_id,
            "items": [revision.to_payload() for revision in store.list_revisions(workspace_id, AssetId(asset_id))],
        }

    def _catalog_request(self, body: object | None, query: str | None = None) -> tuple[SqliteCatalogStore, WorkspaceId]:
        if self.catalog_store is None:
            raise RuntimeError("catalog store is not configured")
        workspace = body.get("workspace_id") if isinstance(body, dict) else None
        if not isinstance(workspace, str) and query:
            from urllib.parse import parse_qs
            workspace = parse_qs(query).get("workspace_id", [None])[0]
        if not isinstance(workspace, str):
            raise ValueError("body.workspace_id is required")
        return self.catalog_store, WorkspaceId(workspace)


def _decode_plan(body: object | None) -> GenerationPlan:
    if not isinstance(body, dict):
        raise ValueError("body must be an object")
    raw = body.get("plan", body)
    if isinstance(raw, GenerationPlan):
        plan = raw
    else:
        if not isinstance(raw, dict):
            raise ValueError("body.plan must be a GenerationPlan or JSON plan object")
        try:
            plan = plan_from_payload(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid synthetic plan: {exc}") from exc
    _enforce_limits(plan)
    return plan


def _source_sample(body: object | None) -> dict[str, tuple[dict[str, object], ...]] | None:
    if not isinstance(body, dict) or body.get("source_sample") is None:
        return None
    raw = body["source_sample"]
    if not isinstance(raw, dict):
        raise ValueError("source_sample must be an object of table names to row arrays")
    sample: dict[str, tuple[dict[str, object], ...]] = {}
    for table, rows in raw.items():
        if not isinstance(table, str) or not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("source_sample rows must be objects")
        sample[table] = tuple(rows)
    return sample


def _limit(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _enforce_limits(plan: GenerationPlan) -> None:
    if len(plan.tables) > _limit("SDS_MAX_TABLES_PER_PLAN", 100):
        raise ValueError("synthetic plan exceeds table limit")
    if any(len(table.columns) > _limit("SDS_MAX_COLUMNS_PER_TABLE", 2000) for table in plan.tables):
        raise ValueError("synthetic plan exceeds column limit")
    if sum(table.rows for table in plan.tables) > _limit("SDS_MAX_ROWS_PER_RUN", 100_000):
        raise ValueError("synthetic plan exceeds row limit")


def _media_type(format_id: str) -> str:
    media_types = {
        "csv": "text/csv", "json": "application/json",
        "jsonl": "application/x-ndjson", "xml": "application/xml",
    }
    return media_types.get(format_id, "application/octet-stream")


def factory() -> SyntheticDataStudioPlugin:
    return SyntheticDataStudioPlugin()


GovernStudioPlugin = SyntheticDataStudioPlugin
SyntheticDataPlugin = SyntheticDataStudioPlugin

__all__ = ["SyntheticDataStudioPlugin", "GovernStudioPlugin", "SyntheticDataPlugin", "factory"]
