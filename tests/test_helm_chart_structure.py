from pathlib import Path


def test_reference_helm_chart_has_safe_single_replica_baseline() -> None:
    root = Path("deploy/helm/ronin")
    assert (root / "Chart.yaml").is_file()
    assert (root / "values.yaml").is_file()
    deployment = (root / "templates/deployment.yaml").read_text(encoding="utf-8")
    assert "replicas: {{ .Values.server.replicas }}" in deployment
    assert "RONIN_DB" in deployment
    assert "persistentVolumeClaim:" in deployment
    assert "secretKeyRef:" in deployment
    assert "readinessProbe:" in deployment
    assert "livenessProbe:" in deployment
    assert "runAsNonRoot: true" in deployment
    assert "type: RuntimeDefault" in deployment
    assert "allowPrivilegeEscalation: false" in deployment
    assert "readOnlyRootFilesystem: true" in deployment
    assert 'drop: ["ALL"]' in deployment
    values = (root / "values.yaml").read_text(encoding="utf-8")
    assert "replicas: 1" in values
