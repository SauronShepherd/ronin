"""Workspace-scoped, bounded model artifact API tests."""

from __future__ import annotations

import base64
import hashlib

import pytest
from studio_core.ml import (
    MLRunId,
    ModelId,
    ModelSignature,
    ModelVersion,
    RegisteredModelVersion,
)
from studio_core.plugins import PluginManager, PluginRecord
from studio_ml.plugin import MachineLearningStudioPlugin
from studio_storage import LocalArtifactStore


def _plugin(
    tmp_path,
    data: bytes = b'{"schema":"ronin.ml-tabular/v1","value":1}',
    *,
    framework: str = "sklearn",
    artifact_media_type: str = "application/vnd.ronin.sklearn-tabular+json",
):
    artifacts = LocalArtifactStore(tmp_path / "artifacts")
    artifact = artifacts.put_bytes(
        role="model",
        data=data,
        media_type=artifact_media_type,
    )
    model = RegisteredModelVersion(
        ModelId("churn"),
        ModelVersion("v1"),
        MLRunId("run-1"),
        artifact.storage_ref,
        artifact.digest,
        framework,
        ModelSignature((("x", "int64"),), (("target", "label"),)),
    )

    class Registry:
        def get_model(self, workspace_id, model_id, version):
            if (
                str(workspace_id) == "workspace-a"
                and model_id == model.model_id
                and version == model.version
            ):
                return model
            return None

    plugin = MachineLearningStudioPlugin()
    plugin._registry = Registry()
    plugin._artifacts = artifacts
    return plugin, artifacts, model


def test_model_artifact_returns_digest_verified_bounded_chunks(tmp_path) -> None:
    data = b"abcdefghijklmnopqrstuvwxyz"
    plugin, _artifacts, model = _plugin(tmp_path, data)
    try:
        first = plugin.model_artifact(
            "churn", "v1", query="workspace_id=workspace-a&offset=0&length=5"
        )
        second = plugin.model_artifact(
            "churn", "v1", query="workspace_id=workspace-a&offset=5&length=8"
        )
        final = plugin.model_artifact(
            "churn", "v1", query="workspace_id=workspace-a&offset=13&length=512"
        )
        chunks = [base64.b64decode(item["data_base64"]) for item in (first, second, final)]
        assert b"".join(chunks) == data
        assert first["next_offset"] == 5
        assert second["next_offset"] == 13
        assert final["next_offset"] is None
        assert final["complete"] is True
        assert final["digest"] == hashlib.sha256(data).hexdigest() == model.artifact_digest
        assert final["media_type"] == "application/vnd.ronin.sklearn-tabular+json"
    finally:
        plugin._coordinator.close()


def test_model_artifact_rejects_wrong_workspace_and_invalid_ranges(tmp_path) -> None:
    plugin, _artifacts, _model = _plugin(tmp_path)
    try:
        with pytest.raises(KeyError):
            plugin.model_artifact("churn", "v1", query="workspace_id=workspace-b")
        with pytest.raises(ValueError, match="duplicate parameters"):
            plugin.model_artifact("churn", "v1", query="workspace_id=workspace-a&offset=0&offset=1")
        with pytest.raises(ValueError, match="length must be between"):
            plugin.model_artifact("churn", "v1", query="workspace_id=workspace-a&length=524289")
        with pytest.raises(ValueError, match="offset exceeds"):
            plugin.model_artifact("churn", "v1", query="workspace_id=workspace-a&offset=999")
    finally:
        plugin._coordinator.close()


def test_model_artifact_rejects_corrupt_storage_bytes(tmp_path) -> None:
    plugin, _artifacts, _model = _plugin(tmp_path)

    class CorruptArtifacts:
        def get_bytes_by_storage_ref(self, _storage_ref: str, *, digest: str) -> bytes:
            return b"corrupt-" + digest.encode()

    plugin._artifacts = CorruptArtifacts()
    try:
        with pytest.raises(ValueError, match="integrity verification"):
            plugin.model_artifact("churn", "v1", query="workspace_id=workspace-a")
    finally:
        plugin._coordinator.close()


def test_model_artifact_reports_kmeans_media_type(tmp_path) -> None:
    plugin, _artifacts, _model = _plugin(
        tmp_path,
        b'{"schema":"ronin.ml-kmeans/v1"}',
        framework="ronin-kmeans",
        artifact_media_type="application/vnd.ronin.ml-kmeans+json",
    )
    try:
        chunk = plugin.model_artifact("churn", "v1", query="workspace_id=workspace-a")
        assert chunk["media_type"] == "application/vnd.ronin.ml-kmeans+json"
    finally:
        plugin._coordinator.close()


def test_model_artifact_route_requires_read_permission() -> None:
    plugin = MachineLearningStudioPlugin()
    plan = PluginManager().compose((PluginRecord(plugin.manifest, plugin, "test"),))
    try:
        route = next(
            item
            for item in plan.contributions.routes
            if item.path == "/v1/ml-studio/models/{model_id}/{version}/artifact"
        )
        assert route.method == "GET"
        assert route.permission == "ml-studio:read"
        assert route.permission in plugin.manifest.permissions
    finally:
        plugin.shutdown()
