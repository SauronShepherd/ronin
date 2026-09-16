"""Durable project-scoped persistence for semantic models."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .contracts import DashboardDefinition, SemanticModel


class SemanticModelConflict(RuntimeError):
    """Raised when a model identity is reused with different content."""


class SqliteSemanticStore:
    """SQLite reference store for reusable semantic models."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS semantic_models ("
                "project_id TEXT NOT NULL, model_id TEXT NOT NULL, "
                "model_json TEXT NOT NULL, "
                "PRIMARY KEY(project_id, model_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS semantic_dashboards ("
                "project_id TEXT NOT NULL, dashboard_id TEXT NOT NULL, "
                "dashboard_json TEXT NOT NULL, "
                "PRIMARY KEY(project_id, dashboard_id))"
            )

    def put_model(self, project_id: str, model: SemanticModel) -> SemanticModel:
        self._validate_project(project_id)
        payload = model.to_json()
        with sqlite3.connect(self._path) as connection:
            existing = connection.execute(
                "SELECT model_json FROM semantic_models WHERE project_id=? AND model_id=?",
                (project_id, model.id),
            ).fetchone()
            if existing is not None and existing[0] != payload:
                raise SemanticModelConflict(
                    f"semantic model already exists with different content: {model.id}"
                )
            connection.execute(
                "INSERT OR IGNORE INTO semantic_models("
                "project_id,model_id,model_json) VALUES (?,?,?)",
                (project_id, model.id, payload),
            )
        return model

    def get_model(self, project_id: str, model_id: str) -> SemanticModel | None:
        self._validate_project(project_id)
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT model_json FROM semantic_models WHERE project_id=? AND model_id=?",
                (project_id, model_id),
            ).fetchone()
        return None if row is None else SemanticModel.from_json(str(row[0]))

    def list_models(self, project_id: str) -> tuple[SemanticModel, ...]:
        self._validate_project(project_id)
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                "SELECT model_json FROM semantic_models WHERE project_id=? ORDER BY model_id",
                (project_id,),
            ).fetchall()
        return tuple(SemanticModel.from_json(str(row[0])) for row in rows)

    def put_dashboard(self, project_id: str, dashboard: DashboardDefinition) -> DashboardDefinition:
        self._validate_project(project_id)
        payload = dashboard.to_json()
        with sqlite3.connect(self._path) as connection:
            existing = connection.execute(
                "SELECT dashboard_json FROM semantic_dashboards "
                "WHERE project_id=? AND dashboard_id=?",
                (project_id, dashboard.id),
            ).fetchone()
            if existing is not None and existing[0] != payload:
                raise SemanticModelConflict(
                    f"semantic dashboard already exists with different content: {dashboard.id}"
                )
            connection.execute(
                "INSERT OR IGNORE INTO semantic_dashboards("
                "project_id,dashboard_id,dashboard_json) VALUES (?,?,?)",
                (project_id, dashboard.id, payload),
            )
        return dashboard

    def get_dashboard(self, project_id: str, dashboard_id: str) -> DashboardDefinition | None:
        self._validate_project(project_id)
        with sqlite3.connect(self._path) as connection:
            row = connection.execute(
                "SELECT dashboard_json FROM semantic_dashboards "
                "WHERE project_id=? AND dashboard_id=?",
                (project_id, dashboard_id),
            ).fetchone()
        return None if row is None else DashboardDefinition.from_json(str(row[0]))

    def list_dashboards(self, project_id: str) -> tuple[DashboardDefinition, ...]:
        self._validate_project(project_id)
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute(
                "SELECT dashboard_json FROM semantic_dashboards "
                "WHERE project_id=? ORDER BY dashboard_id",
                (project_id,),
            ).fetchall()
        return tuple(DashboardDefinition.from_json(str(row[0])) for row in rows)

    @staticmethod
    def _validate_project(project_id: str) -> None:
        if not project_id or project_id != project_id.strip() or "\x00" in project_id:
            raise ValueError("semantic project_id must be non-empty and trimmed")


__all__ = ("SemanticModelConflict", "SqliteSemanticStore")
