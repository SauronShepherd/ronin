"""SQLite adapter for the ML Studio lab and pipeline ports."""
# ruff: noqa: E501, E701, E702

from __future__ import annotations

import sqlite3
from pathlib import Path

from studio_core import WorkspaceId
from studio_core.canonical_json import encode as encode_canonical_json
from studio_orchestrator import Instant
from studio_storage.sqlite import open_database

from .domain import FeatureDefinition, Lab, PipelineIR
from .drift import DriftPolicy
from .ports import FeatureDefinitionStore, MLLabStore
from .quality import QualitySuite
from .services import FeatureDefinitionConflict, MLLabConflict


class SqliteMLLabStore(MLLabStore, FeatureDefinitionStore):
    def __init__(self, path: Path, *, migration_now: Instant | str) -> None:
        self._path = path
        connection = open_database(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_labs (workspace_id TEXT NOT NULL, lab_id TEXT NOT NULL, lab_json TEXT NOT NULL, PRIMARY KEY(workspace_id, lab_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_pipelines (workspace_id TEXT NOT NULL, lab_id TEXT NOT NULL, pipeline_json TEXT NOT NULL, PRIMARY KEY(workspace_id, lab_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_features (workspace_id TEXT NOT NULL, feature_id TEXT NOT NULL, version INTEGER NOT NULL, feature_json TEXT NOT NULL, PRIMARY KEY(workspace_id, feature_id, version))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_quality_suites (workspace_id TEXT NOT NULL, lab_id TEXT NOT NULL, suite_id TEXT NOT NULL, version INTEGER NOT NULL, suite_json TEXT NOT NULL, PRIMARY KEY(workspace_id, lab_id, suite_id, version), FOREIGN KEY(workspace_id, lab_id) REFERENCES ml_studio_labs(workspace_id, lab_id) ON DELETE CASCADE)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ml_studio_drift_policies (workspace_id TEXT NOT NULL, lab_id TEXT NOT NULL, policy_id TEXT NOT NULL, version INTEGER NOT NULL, policy_json TEXT NOT NULL, PRIMARY KEY(workspace_id, lab_id, policy_id, version), FOREIGN KEY(workspace_id, lab_id) REFERENCES ml_studio_labs(workspace_id, lab_id) ON DELETE CASCADE)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO ml_studio_schema_migrations(version, applied_at) VALUES (1, ?)",
                (str(Instant(migration_now)),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO ml_studio_schema_migrations(version, applied_at) VALUES (2, ?)",
                (str(Instant(migration_now)),),
            )
            connection.execute(
                "INSERT OR IGNORE INTO ml_studio_schema_migrations(version, applied_at) VALUES (3, ?)",
                (str(Instant(migration_now)),),
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return open_database(self._path)

    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        connection = self._connect()
        payload = lab.to_json()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT lab_json FROM ml_studio_labs WHERE workspace_id=? AND lab_id=?",
                (str(workspace_id), lab.id),
            ).fetchone()
            if row is not None and row["lab_json"] != payload:
                raise MLLabConflict(f"lab id already exists: {lab.id}")
            connection.execute(
                "INSERT OR IGNORE INTO ml_studio_labs(workspace_id, lab_id, lab_json) VALUES (?,?,?)",
                (str(workspace_id), lab.id, payload),
            )
            connection.execute("COMMIT")
            return lab
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT lab_json FROM ml_studio_labs WHERE workspace_id=? AND lab_id=?",
                (str(workspace_id), lab_id),
            ).fetchone()
            return None if row is None else Lab.from_json(row["lab_json"])
        finally:
            connection.close()

    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT lab_json FROM ml_studio_labs WHERE workspace_id=? ORDER BY lab_id",
                (str(workspace_id),),
            ).fetchall()
            return tuple(Lab.from_json(row["lab_json"]) for row in rows)
        finally:
            connection.close()

    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT OR REPLACE INTO ml_studio_pipelines(workspace_id, lab_id, pipeline_json) VALUES (?,?,?)",
                (str(workspace_id), lab_id, pipeline.to_json()),
            )
            return pipeline
        finally:
            connection.close()

    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT pipeline_json FROM ml_studio_pipelines WHERE workspace_id=? AND lab_id=?",
                (str(workspace_id), lab_id),
            ).fetchone()
            if row is None:
                return None
            raw = row["pipeline_json"]
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if not isinstance(raw, str):
                raise ValueError("stored ML pipeline must be JSON text")
            return PipelineIR.from_json(raw)
        finally:
            connection.close()

    def put_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite: QualitySuite
    ) -> QualitySuite:
        connection = self._connect()
        key = (str(workspace_id), lab_id, suite.id)
        payload = suite.to_json()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT suite_json FROM ml_studio_quality_suites WHERE workspace_id=? AND lab_id=? AND suite_id=? AND version=?",
                (*key, suite.version),
            ).fetchone()
            if row is not None:
                if QualitySuite.from_json(row["suite_json"]) != suite:
                    from .services import QualitySuiteConflict

                    raise QualitySuiteConflict(
                        f"quality suite version already exists: {suite.id}@{suite.version}"
                    )
                connection.execute("COMMIT")
                return suite
            latest = connection.execute(
                "SELECT MAX(version) AS version FROM ml_studio_quality_suites WHERE workspace_id=? AND lab_id=? AND suite_id=?",
                key,
            ).fetchone()["version"]
            if latest is not None and suite.version <= latest:
                from .services import QualitySuiteConflict

                raise QualitySuiteConflict("quality suite versions must increase monotonically")
            connection.execute(
                "INSERT INTO ml_studio_quality_suites(workspace_id,lab_id,suite_id,version,suite_json) VALUES (?,?,?,?,?)",
                (*key, suite.version, payload),
            )
            connection.execute("COMMIT")
            return suite
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite_id: str, version: int | None = None
    ) -> QualitySuite | None:
        connection = self._connect()
        try:
            if version is None:
                row = connection.execute(
                    "SELECT suite_json FROM ml_studio_quality_suites WHERE workspace_id=? AND lab_id=? AND suite_id=? ORDER BY version DESC LIMIT 1",
                    (str(workspace_id), lab_id, suite_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT suite_json FROM ml_studio_quality_suites WHERE workspace_id=? AND lab_id=? AND suite_id=? AND version=?",
                    (str(workspace_id), lab_id, suite_id, version),
                ).fetchone()
            return None if row is None else QualitySuite.from_json(row["suite_json"])
        finally:
            connection.close()

    def list_quality_suites(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[QualitySuite, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT suite_json FROM ml_studio_quality_suites WHERE workspace_id=? AND lab_id=? ORDER BY suite_id,version",
                (str(workspace_id), lab_id),
            ).fetchall()
            return tuple(QualitySuite.from_json(row["suite_json"]) for row in rows)
        finally:
            connection.close()

    def put_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy: DriftPolicy
    ) -> DriftPolicy:
        connection = self._connect()
        key = (str(workspace_id), lab_id, policy.id)
        payload = encode_canonical_json(policy.to_payload()).decode("utf-8")
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT policy_json FROM ml_studio_drift_policies WHERE workspace_id=? AND lab_id=? AND policy_id=? AND version=?",
                (*key, policy.version),
            ).fetchone()
            if row is not None:
                if DriftPolicy.from_json(row["policy_json"]) != policy:
                    from .services import DriftPolicyConflict

                    raise DriftPolicyConflict(
                        f"drift policy version already exists: {policy.id}@{policy.version}"
                    )
                connection.execute("COMMIT")
                return policy
            latest = connection.execute(
                "SELECT MAX(version) AS version FROM ml_studio_drift_policies WHERE workspace_id=? AND lab_id=? AND policy_id=?",
                key,
            ).fetchone()["version"]
            if latest is not None and policy.version <= latest:
                from .services import DriftPolicyConflict

                raise DriftPolicyConflict("drift policy versions must increase monotonically")
            connection.execute(
                "INSERT INTO ml_studio_drift_policies(workspace_id,lab_id,policy_id,version,policy_json) VALUES (?,?,?,?,?)",
                (*key, policy.version, payload),
            )
            connection.execute("COMMIT")
            return policy
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy_id: str, version: int | None = None
    ) -> DriftPolicy | None:
        connection = self._connect()
        try:
            if version is None:
                row = connection.execute(
                    "SELECT policy_json FROM ml_studio_drift_policies WHERE workspace_id=? AND lab_id=? AND policy_id=? ORDER BY version DESC LIMIT 1",
                    (str(workspace_id), lab_id, policy_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT policy_json FROM ml_studio_drift_policies WHERE workspace_id=? AND lab_id=? AND policy_id=? AND version=?",
                    (str(workspace_id), lab_id, policy_id, version),
                ).fetchone()
            return None if row is None else DriftPolicy.from_json(row["policy_json"])
        finally:
            connection.close()

    def list_drift_policies(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[DriftPolicy, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT policy_json FROM ml_studio_drift_policies WHERE workspace_id=? AND lab_id=? ORDER BY policy_id,version",
                (str(workspace_id), lab_id),
            ).fetchall()
            return tuple(DriftPolicy.from_json(row["policy_json"]) for row in rows)
        finally:
            connection.close()

    def put_feature_definition(
        self, workspace_id: WorkspaceId, definition: FeatureDefinition
    ) -> FeatureDefinition:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            key = (str(workspace_id), definition.id, definition.version)
            row = connection.execute(
                "SELECT feature_json FROM ml_studio_features "
                "WHERE workspace_id=? AND feature_id=? AND version=?",
                key,
            ).fetchone()
            payload = definition.to_json()
            if row is not None:
                if row["feature_json"] != payload:
                    raise FeatureDefinitionConflict(
                        f"feature definition version already exists: {definition.id}/{definition.version}"
                    )
                connection.execute("COMMIT")
                return definition
            latest = connection.execute(
                "SELECT MAX(version) AS version FROM ml_studio_features "
                "WHERE workspace_id=? AND feature_id=?",
                (str(workspace_id), definition.id),
            ).fetchone()["version"]
            if latest is not None and definition.version <= int(latest):
                raise FeatureDefinitionConflict(
                    f"feature definition version must advance: {definition.id}/{latest}"
                )
            connection.execute(
                "INSERT INTO ml_studio_features(workspace_id,feature_id,version,feature_json) VALUES (?,?,?,?)",
                (*key, payload),
            )
            connection.execute("COMMIT")
            return definition
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_feature_definition(
        self, workspace_id: WorkspaceId, feature_id: str, version: int | None = None
    ) -> FeatureDefinition | None:
        connection = self._connect()
        try:
            if version is None:
                row = connection.execute(
                    "SELECT feature_json FROM ml_studio_features WHERE workspace_id=? AND feature_id=? ORDER BY version DESC LIMIT 1",
                    (str(workspace_id), feature_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT feature_json FROM ml_studio_features WHERE workspace_id=? AND feature_id=? AND version=?",
                    (str(workspace_id), feature_id, version),
                ).fetchone()
            return None if row is None else FeatureDefinition.from_json(row["feature_json"])
        finally:
            connection.close()

    def list_feature_definitions(
        self, workspace_id: WorkspaceId, feature_id: str | None = None
    ) -> tuple[FeatureDefinition, ...]:
        connection = self._connect()
        try:
            query = "SELECT feature_json FROM ml_studio_features WHERE workspace_id=?"
            args: tuple[object, ...] = (str(workspace_id),)
            if feature_id is not None:
                query += " AND feature_id=?"
                args += (feature_id,)
            query += " ORDER BY feature_id,version"
            rows = connection.execute(query, args).fetchall()
            return tuple(FeatureDefinition.from_json(row["feature_json"]) for row in rows)
        finally:
            connection.close()


__all__ = ["SqliteMLLabStore"]
