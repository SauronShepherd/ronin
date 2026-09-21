import pytest

from studio_execution import KubernetesManifestError, WorkloadSpec, render_job


def workload() -> WorkloadSpec:
    return WorkloadSpec(
        run_id="run-42",
        worker_protocol="plugin-worker/v1",
        image="ronin-worker@sha256:abc",
        command=("ronin-worker", "--serve"),
        labels={"team": "studio"},
    )


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
