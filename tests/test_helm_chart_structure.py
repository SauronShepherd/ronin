import json
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
    assert "Ronin Public v1 supports one server replica" in deployment
    schema = json.loads((root / "values.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["server"]["properties"]["token"]["minLength"] == 1
    assert schema["properties"]["server"]["properties"]["tokenScopes"]["not"] == {"const": "{}"}
    token_scopes_schema = schema["properties"]["server"]["properties"]["tokenScopes"]
    assert "version" in token_scopes_schema["pattern"]
    assert "grants" in token_scopes_schema["pattern"]
    assert "read:jobs,write:jobs" not in token_scopes_schema["pattern"]
    assert schema["properties"]["server"]["properties"]["bindPolicy"]["enum"] == [
        "insecure-plaintext-network"
    ]
    assert schema["properties"]["server"]["properties"]["replicas"]["maximum"] == 1
    values = (root / "values.yaml").read_text(encoding="utf-8")
    assert "replicas: 1" in values
    assert 'bindPolicy: ""' in values
    assert "RONIN_BIND_POLICY" in deployment
    assert "multiUser" not in values + deployment
    assert "multi-user" not in values + deployment
    assert "RONIN_STORAGE_BACKEND" not in deployment
    assert "RONIN_POSTGRES_DSN" not in deployment
    assert "multiUser" not in json.dumps(schema)


def test_helm_qualification_runner_isolated_and_checks_restart_persistence() -> None:
    script = Path("tools/run_helm_qualification.ps1").read_text(encoding="utf-8")
    assert "Refusing release qualification with a dirty worktree" in script
    assert "Use -AllowDirtyWorktree only for diagnostics" in script
    assert "^sha256:[0-9a-f]{64}$" in script
    assert '$kubeContext = "kind-$clusterName"' in script
    assert 'rollout restart "deployment/$deployment"' in script
    assert "persistent_job_after_restart" in script
    assert "helm upgrade ronin" in script
    assert "helm rollback ronin 1" in script
    assert "helm_upgrade" in script
    assert "helm_rollback" in script
    assert "Get-HelmRevisionRecords" in script
    assert "-UseBasicParsing" in script
    assert "rollback_status = $rollbackStatus" in script
    assert "Isolated kind cluster remains after cleanup" in script
    assert "[string]$DockerEvidenceDirectory" in script
    assert "docker-qualification.log" in script
    assert "v01-acceptance-strict.json" in script
    assert r"Ronin image (sha256:[0-9a-f]{64}) \(built from checkout\);" in script
    assert (
        "Docker qualification evidence does not match this source SHA and worktree mode." in script
    )
    assert "strict_success -ne $true" in script
    assert "passed -ne 15" in script
    assert "Supplied Ronin image ID does not match the full Docker acceptance evidence." in script
    assert "docker_evidence_directory = $dockerEvidenceRoot" in script
