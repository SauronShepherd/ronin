import pytest

from studio_ai_studio.observability import AuditRecord, Metrics, redact_mapping, workspace_label


def test_redaction_and_workspace_labels_are_safe():
    data = redact_mapping({"Authorization": "secret", "model": "qwen", "prompt": "not logged"})
    assert data["Authorization"] == "[REDACTED]"
    assert data["model"] == "qwen"
    assert len(workspace_label("workspace-1")) == 16
    assert workspace_label("workspace-1") == workspace_label("workspace-1")


def test_audit_rejects_secret_metadata_and_metrics_are_bounded():
    with pytest.raises(ValueError, match="secret"):
        AuditRecord("endpoint.updated", "endpoint/x", "success", metadata=(("api_key", "x"),))
    metrics = Metrics(max_series=1)
    metrics.increment("requests", "chat")
    with pytest.raises(ValueError, match="cardinality"):
        metrics.increment("requests", "embedding")
