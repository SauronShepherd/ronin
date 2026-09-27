"""Provider-neutral HTTP adapter for semantic models and dashboards."""

from __future__ import annotations

from .contracts import DashboardDefinition, MetricQuery, SemanticModel
from .joins import SemanticJoin
from .runtime import ProjectScopedSemanticRuntime, SemanticRuntime
from .store import SqliteSemanticStore


class SemanticHTTPAdapter:
    def __init__(
        self, store: SqliteSemanticStore, runtime: SemanticRuntime | ProjectScopedSemanticRuntime
    ) -> None:
        self._store = store
        self._runtime = runtime

    def put_model(self, project_id: str, body: object) -> dict[str, object]:
        model = SemanticModel.from_json(_json_body(body))
        return self._store.put_model(project_id, model).to_payload()

    def list_models(self, project_id: str) -> dict[str, object]:
        return {"items": [model.to_payload() for model in self._store.list_models(project_id)]}

    def put_dashboard(self, project_id: str, body: object) -> dict[str, object]:
        dashboard = DashboardDefinition.from_payload(_object_body(body))
        return self._store.put_dashboard(project_id, dashboard).to_payload()

    def list_dashboards(self, project_id: str) -> dict[str, object]:
        return {
            "items": [
                dashboard.to_payload() for dashboard in self._store.list_dashboards(project_id)
            ]
        }

    def get_dashboard(self, project_id: str, dashboard_id: str) -> dict[str, object] | None:
        dashboard = self._store.get_dashboard(project_id, dashboard_id)
        return None if dashboard is None else dashboard.to_payload()

    def query(self, project_id: str, body: object) -> dict[str, object]:
        query = MetricQuery.from_payload(_object_body(body))
        model = self._store.get_model(project_id, query.model_id)
        if model is None:
            raise KeyError(f"semantic model not found: {query.model_id}")
        if isinstance(self._runtime, ProjectScopedSemanticRuntime):
            result = self._runtime.execute_for_project(project_id, model, query)
        else:
            result = self._runtime.execute(model, query)
        return {
            "columns": [{"name": item.name, "type": item.type_name} for item in result.columns],
            "rows": [list(row) for row in result.rows],
        }

    def join_query(self, project_id: str, body: object) -> dict[str, object]:
        """Execute a bounded left-deep semantic join chain for a project."""
        payload = _object_body(body)
        base_id = payload.get("base_model_id")
        raw_steps = payload.get("steps")
        raw_limit = payload.get("limit", 10_000)
        if not isinstance(base_id, str) or not base_id.strip():
            raise ValueError("semantic join base_model_id must be a non-empty string")
        if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 8:
            raise ValueError("semantic join steps must contain between 1 and 8 items")
        if (
            not isinstance(raw_limit, int)
            or isinstance(raw_limit, bool)
            or not 1 <= raw_limit <= 100_000
        ):
            raise ValueError("semantic join limit must be between 1 and 100000")
        base = self._store.get_model(project_id, base_id)
        if base is None:
            raise KeyError(f"semantic model not found: {base_id}")
        steps: list[tuple[SemanticModel, SemanticJoin]] = []
        for item in raw_steps:
            if not isinstance(item, dict) or set(item) != {
                "model_id",
                "left_column",
                "right_column",
                "join_type",
            }:
                raise ValueError("semantic join step has invalid shape")
            model_id = item["model_id"]
            if not isinstance(model_id, str) or not model_id.strip():
                raise ValueError("semantic join model_id must be a non-empty string")
            model = self._store.get_model(project_id, model_id)
            if model is None:
                raise KeyError(f"semantic model not found: {model_id}")
            join = SemanticJoin(item["left_column"], item["right_column"], item["join_type"])
            steps.append((model, join))
        if isinstance(self._runtime, ProjectScopedSemanticRuntime):
            result = self._runtime.execute_join_chain_for_project(
                project_id, base, tuple(steps), max_rows=raw_limit
            )
        else:
            result = self._runtime.execute_join_chain(base, tuple(steps), max_rows=raw_limit)
        return {
            "columns": [{"name": item.name, "type": item.type_name} for item in result.columns],
            "rows": [list(row) for row in result.rows],
        }

    def execute_dashboard(self, project_id: str, dashboard_id: str) -> dict[str, object]:
        dashboard = self._store.get_dashboard(project_id, dashboard_id)
        if dashboard is None:
            raise KeyError(f"semantic dashboard not found: {dashboard_id}")
        models = {model.id: model for model in self._store.list_models(project_id)}
        if isinstance(self._runtime, ProjectScopedSemanticRuntime):
            results = self._runtime.execute_dashboard_for_project(project_id, models, dashboard)
        else:
            results = self._runtime.execute_dashboard(models, dashboard)
        tiles = []
        for item in results:
            tiles.append(
                {
                    "tile_id": item.tile_id,
                    "columns": [
                        {"name": column.name, "type": column.type_name}
                        for column in item.result.columns
                    ],
                    "rows": [list(row) for row in item.result.rows],
                }
            )
        return {"dashboard_id": dashboard.id, "tiles": tiles}


def _object_body(body: object) -> dict[str, object]:
    if not isinstance(body, dict):
        raise ValueError("semantic request body must be an object")
    return body


def _json_body(body: object) -> str:
    payload = _object_body(body)
    from studio_core.canonical_json import encode

    return encode(payload).decode("utf-8")


__all__ = ("SemanticHTTPAdapter",)
