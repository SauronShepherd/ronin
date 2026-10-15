import pytest
from studio_execution import (
    KubernetesExecutionAdapter,
    KubernetesManifestError,
    WorkloadSpec,
    render_job,
)


def workload(**overrides: object) -> WorkloadSpec:
    values: dict[str, object] = {
        "run_id": "run-42",
        "worker_protocol": "plugin-worker/v1",
        "image": "ronin-worker@sha256:abc",
        "command": ("ronin-worker", "--serve"),
        "labels": {"team": "studio"},
    }
    values.update(overrides)
    return WorkloadSpec(**values)


def test_render_job_is_deterministic_and_non_privileged() -> None:
    first = render_job(workload())
    second = render_job(workload())
    assert first == second
    pod = first["spec"]["template"]["spec"]
    assert pod["automountServiceAccountToken"] is False
    assert pod["containers"][0]["securityContext"]["allowPrivilegeEscalation"] is False
    assert pod["containers"][0]["securityContext"]["runAsUser"] == 65532
    assert first["spec"]["backoffLimit"] == 0


def test_render_job_rejects_invalid_namespace() -> None:
    with pytest.raises(KubernetesManifestError):
        render_job(workload(), namespace="Ronin System")


def test_workload_rejects_boolean_timeout_and_non_string_labels() -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        workload(timeout_seconds=True)
    with pytest.raises(ValueError, match="labels"):
        workload(labels={"attempt": 1})


class _Client:
    def __init__(self) -> None:
        self.calls = []

    def create_job(self, manifest):
        self.calls.append(("create", manifest))

    def get_job(self, *, namespace, name):
        self.calls.append(("get", namespace, name))
        return {"name": name}

    def delete_job(self, *, namespace, name):
        self.calls.append(("delete", namespace, name))

    def cancel_job(self, *, namespace, name):
        self.calls.append(("cancel", namespace, name))

    def get_job_logs(self, *, namespace, name, container):
        self.calls.append(("logs", namespace, name, container))
        return "worker output"


def test_kubernetes_adapter_exposes_bounded_job_logs_port() -> None:
    client = _Client()
    adapter = KubernetesExecutionAdapter(client)
    assert adapter.submit(workload())["job_name"] == "run-run-42"
    assert adapter.logs("run-42") == "worker output"
    adapter.cancel("run-42")
    adapter.cleanup("run-42")
    assert ("cancel", "ronin-system", "run-run-42") in client.calls
    assert ("delete", "ronin-system", "run-run-42") in client.calls
    with pytest.raises(KubernetesManifestError):
        adapter.logs("run-42", container="worker/sidecar")
