"""PostgreSQL persistence for the local ML Studio composition."""

from __future__ import annotations

from studio_core import WorkspaceId
from studio_storage.postgres_core import PostgresMetadataStore

from studio_ml.domain import FeatureDefinition, Lab, PipelineIR
from studio_ml.drift import DriftPolicy
from studio_ml.ports import FeatureDefinitionStore, MLLabStore
from studio_ml.quality import QualitySuite
from studio_ml.services import (
    DriftPolicyConflict,
    FeatureDefinitionConflict,
    MLLabConflict,
    QualitySuiteConflict,
)


class PostgresMLLabStore(PostgresMetadataStore, MLLabStore, FeatureDefinitionStore):
    """Durable PostgreSQL adapter for labs and pipeline definitions."""

    def migrate(self) -> None:
        super().migrate()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_studio_labs "
                    "(workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) "
                    "ON DELETE CASCADE, lab_id TEXT NOT NULL, lab_json TEXT NOT NULL, "
                    "PRIMARY KEY(workspace_id, lab_id))"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_studio_pipelines "
                    "(workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) "
                    "ON DELETE CASCADE, lab_id TEXT NOT NULL, pipeline_json TEXT NOT NULL, "
                    "PRIMARY KEY(workspace_id, lab_id))"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_studio_features "
                    "(workspace_id TEXT NOT NULL REFERENCES ronin_workspaces(workspace_id) "
                    "ON DELETE CASCADE, feature_id TEXT NOT NULL, version INTEGER NOT NULL, "
                    "feature_json TEXT NOT NULL, PRIMARY KEY(workspace_id, feature_id, version), "
                    "CHECK (version >= 1 AND version <= 2147483647))"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_studio_quality_suites "
                    "(workspace_id TEXT NOT NULL, lab_id TEXT NOT NULL, suite_id TEXT NOT NULL, "
                    "version INTEGER NOT NULL, suite_json TEXT NOT NULL, "
                    "PRIMARY KEY(workspace_id, lab_id, suite_id, version), "
                    "FOREIGN KEY(workspace_id, lab_id) REFERENCES ronin_ml_studio_labs(workspace_id, lab_id) ON DELETE CASCADE)"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS ronin_ml_studio_drift_policies "
                    "(workspace_id TEXT NOT NULL, lab_id TEXT NOT NULL, policy_id TEXT NOT NULL, "
                    "version INTEGER NOT NULL, policy_json TEXT NOT NULL, "
                    "PRIMARY KEY(workspace_id, lab_id, policy_id, version), "
                    "FOREIGN KEY(workspace_id, lab_id) REFERENCES ronin_ml_studio_labs(workspace_id, lab_id) ON DELETE CASCADE)"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def put_lab(self, workspace_id: WorkspaceId, lab: Lab) -> Lab:
        payload = lab.to_json()
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lab_json FROM ronin_ml_studio_labs WHERE workspace_id=%s AND lab_id=%s",
                    (str(workspace_id), lab.id),
                )
                row = cursor.fetchone()
                if row is not None and row["lab_json"] != payload:
                    raise MLLabConflict(f"lab id already exists: {lab.id}")
                cursor.execute(
                    "INSERT INTO ronin_ml_studio_labs(workspace_id,lab_id,lab_json) "
                    "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (str(workspace_id), lab.id, payload),
                )
            connection.commit()
            return lab
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_lab(self, workspace_id: WorkspaceId, lab_id: str) -> Lab | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lab_json FROM ronin_ml_studio_labs WHERE workspace_id=%s AND lab_id=%s",
                    (str(workspace_id), lab_id),
                )
                row = cursor.fetchone()
            return None if row is None else Lab.from_json(row["lab_json"])
        finally:
            connection.close()

    def list_labs(self, workspace_id: WorkspaceId) -> tuple[Lab, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lab_json FROM ronin_ml_studio_labs "
                    "WHERE workspace_id=%s ORDER BY lab_id",
                    (str(workspace_id),),
                )
                rows = cursor.fetchall()
            return tuple(Lab.from_json(row["lab_json"]) for row in rows)
        finally:
            connection.close()

    def put_pipeline(
        self, workspace_id: WorkspaceId, lab_id: str, pipeline: PipelineIR
    ) -> PipelineIR:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO ronin_ml_studio_pipelines(workspace_id,lab_id,pipeline_json) "
                    "VALUES (%s,%s,%s) ON CONFLICT (workspace_id,lab_id) DO UPDATE "
                    "SET pipeline_json=EXCLUDED.pipeline_json",
                    (str(workspace_id), lab_id, pipeline.to_json()),
                )
            connection.commit()
            return pipeline
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_pipeline(self, workspace_id: WorkspaceId, lab_id: str) -> PipelineIR | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pipeline_json FROM ronin_ml_studio_pipelines "
                    "WHERE workspace_id=%s AND lab_id=%s",
                    (str(workspace_id), lab_id),
                )
                row = cursor.fetchone()
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

    def put_feature_definition(
        self, workspace_id: WorkspaceId, definition: FeatureDefinition
    ) -> FeatureDefinition:
        connection = self._connect()
        key = (str(workspace_id), definition.id, definition.version)
        payload = definition.to_json()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT feature_json FROM ronin_ml_studio_features "
                    "WHERE workspace_id=%s AND feature_id=%s AND version=%s FOR UPDATE",
                    key,
                )
                row = cursor.fetchone()
                if row is not None:
                    if row["feature_json"] != payload:
                        raise FeatureDefinitionConflict(
                            f"feature definition version already exists: {definition.id}/{definition.version}"
                        )
                    connection.commit()
                    return definition
                cursor.execute(
                    "SELECT MAX(version) AS version FROM ronin_ml_studio_features "
                    "WHERE workspace_id=%s AND feature_id=%s",
                    key[:2],
                )
                latest = cursor.fetchone()["version"]
                if latest is not None and definition.version <= int(latest):
                    raise FeatureDefinitionConflict(
                        f"feature definition version must advance: {definition.id}/{latest}"
                    )
                cursor.execute(
                    "INSERT INTO ronin_ml_studio_features "
                    "(workspace_id,feature_id,version,feature_json) VALUES (%s,%s,%s,%s)",
                    (*key, payload),
                )
            connection.commit()
            return definition
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_feature_definition(
        self, workspace_id: WorkspaceId, feature_id: str, version: int | None = None
    ) -> FeatureDefinition | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                if version is None:
                    cursor.execute(
                        "SELECT feature_json FROM ronin_ml_studio_features "
                        "WHERE workspace_id=%s AND feature_id=%s ORDER BY version DESC LIMIT 1",
                        (str(workspace_id), feature_id),
                    )
                else:
                    cursor.execute(
                        "SELECT feature_json FROM ronin_ml_studio_features "
                        "WHERE workspace_id=%s AND feature_id=%s AND version=%s",
                        (str(workspace_id), feature_id, version),
                    )
                row = cursor.fetchone()
            return None if row is None else FeatureDefinition.from_json(row["feature_json"])
        finally:
            connection.close()

    def list_feature_definitions(
        self, workspace_id: WorkspaceId, feature_id: str | None = None
    ) -> tuple[FeatureDefinition, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                if feature_id is None:
                    cursor.execute(
                        "SELECT feature_json FROM ronin_ml_studio_features "
                        "WHERE workspace_id=%s ORDER BY feature_id,version",
                        (str(workspace_id),),
                    )
                else:
                    cursor.execute(
                        "SELECT feature_json FROM ronin_ml_studio_features "
                        "WHERE workspace_id=%s AND feature_id=%s ORDER BY version",
                        (str(workspace_id), feature_id),
                    )
                rows = cursor.fetchall()
            return tuple(FeatureDefinition.from_json(row["feature_json"]) for row in rows)
        finally:
            connection.close()

    def put_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite: QualitySuite
    ) -> QualitySuite:
        connection = self._connect()
        key = (str(workspace_id), lab_id, suite.id)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lab_id FROM ronin_ml_studio_labs WHERE workspace_id=%s AND lab_id=%s FOR UPDATE",
                    (str(workspace_id), lab_id),
                )
                if cursor.fetchone() is None:
                    raise KeyError(lab_id)
                cursor.execute(
                    "SELECT suite_json FROM ronin_ml_studio_quality_suites WHERE workspace_id=%s AND lab_id=%s AND suite_id=%s AND version=%s FOR UPDATE",
                    (*key, suite.version),
                )
                row = cursor.fetchone()
                if row is not None:
                    if QualitySuite.from_json(row["suite_json"]) != suite:
                        raise QualitySuiteConflict(
                            f"quality suite version already exists: {suite.id}@{suite.version}"
                        )
                    connection.commit()
                    return suite
                cursor.execute(
                    "SELECT MAX(version) AS version FROM ronin_ml_studio_quality_suites WHERE workspace_id=%s AND lab_id=%s AND suite_id=%s",
                    key,
                )
                latest = cursor.fetchone()["version"]
                if latest is not None and suite.version <= latest:
                    raise QualitySuiteConflict("quality suite versions must increase monotonically")
                cursor.execute(
                    "INSERT INTO ronin_ml_studio_quality_suites(workspace_id,lab_id,suite_id,version,suite_json) VALUES (%s,%s,%s,%s,%s)",
                    (*key, suite.version, suite.to_json()),
                )
            connection.commit()
            return suite
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_quality_suite(
        self, workspace_id: WorkspaceId, lab_id: str, suite_id: str, version: int | None = None
    ) -> QualitySuite | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                if version is None:
                    cursor.execute(
                        "SELECT suite_json FROM ronin_ml_studio_quality_suites WHERE workspace_id=%s AND lab_id=%s AND suite_id=%s ORDER BY version DESC LIMIT 1",
                        (str(workspace_id), lab_id, suite_id),
                    )
                else:
                    cursor.execute(
                        "SELECT suite_json FROM ronin_ml_studio_quality_suites WHERE workspace_id=%s AND lab_id=%s AND suite_id=%s AND version=%s",
                        (str(workspace_id), lab_id, suite_id, version),
                    )
                row = cursor.fetchone()
            return None if row is None else QualitySuite.from_json(row["suite_json"])
        finally:
            connection.close()

    def list_quality_suites(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[QualitySuite, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT suite_json FROM ronin_ml_studio_quality_suites WHERE workspace_id=%s AND lab_id=%s ORDER BY suite_id,version",
                    (str(workspace_id), lab_id),
                )
                rows = cursor.fetchall()
            return tuple(QualitySuite.from_json(row["suite_json"]) for row in rows)
        finally:
            connection.close()

    def put_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy: DriftPolicy
    ) -> DriftPolicy:
        connection = self._connect()
        key = (str(workspace_id), lab_id, policy.id)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT lab_id FROM ronin_ml_studio_labs WHERE workspace_id=%s AND lab_id=%s FOR UPDATE",
                    (str(workspace_id), lab_id),
                )
                if cursor.fetchone() is None:
                    raise KeyError(lab_id)
                cursor.execute(
                    "SELECT policy_json FROM ronin_ml_studio_drift_policies WHERE workspace_id=%s AND lab_id=%s AND policy_id=%s AND version=%s FOR UPDATE",
                    (*key, policy.version),
                )
                row = cursor.fetchone()
                if row is not None:
                    if DriftPolicy.from_json(row["policy_json"]) != policy:
                        raise DriftPolicyConflict(
                            f"drift policy version already exists: {policy.id}@{policy.version}"
                        )
                    connection.commit()
                    return policy
                cursor.execute(
                    "SELECT MAX(version) AS version FROM ronin_ml_studio_drift_policies WHERE workspace_id=%s AND lab_id=%s AND policy_id=%s",
                    key,
                )
                latest = cursor.fetchone()["version"]
                if latest is not None and policy.version <= latest:
                    raise DriftPolicyConflict("drift policy versions must increase monotonically")
                cursor.execute(
                    "INSERT INTO ronin_ml_studio_drift_policies(workspace_id,lab_id,policy_id,version,policy_json) VALUES (%s,%s,%s,%s,%s)",
                    (*key, policy.version, policy.to_json()),
                )
            connection.commit()
            return policy
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_drift_policy(
        self, workspace_id: WorkspaceId, lab_id: str, policy_id: str, version: int | None = None
    ) -> DriftPolicy | None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                if version is None:
                    cursor.execute(
                        "SELECT policy_json FROM ronin_ml_studio_drift_policies WHERE workspace_id=%s AND lab_id=%s AND policy_id=%s ORDER BY version DESC LIMIT 1",
                        (str(workspace_id), lab_id, policy_id),
                    )
                else:
                    cursor.execute(
                        "SELECT policy_json FROM ronin_ml_studio_drift_policies WHERE workspace_id=%s AND lab_id=%s AND policy_id=%s AND version=%s",
                        (str(workspace_id), lab_id, policy_id, version),
                    )
                row = cursor.fetchone()
            return None if row is None else DriftPolicy.from_json(row["policy_json"])
        finally:
            connection.close()

    def list_drift_policies(
        self, workspace_id: WorkspaceId, lab_id: str
    ) -> tuple[DriftPolicy, ...]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT policy_json FROM ronin_ml_studio_drift_policies WHERE workspace_id=%s AND lab_id=%s ORDER BY policy_id,version",
                    (str(workspace_id), lab_id),
                )
                rows = cursor.fetchall()
            return tuple(DriftPolicy.from_json(row["policy_json"]) for row in rows)
        finally:
            connection.close()


__all__ = ("PostgresMLLabStore",)
