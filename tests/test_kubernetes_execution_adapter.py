from studio_execution import KubernetesExecutionAdapter, WorkloadSpec


class FakeClient:
    def __init__(self):
        self.jobs = {}

    def create_job(self, manifest):
        self.jobs[manifest["metadata"]["name"]] = manifest

    def get_job(self, *, namespace, name):
        del namespace
        return self.jobs.get(name)

    def delete_job(self, *, namespace, name):
        del namespace
        self.jobs.pop(name, None)


def _spec():
    return WorkloadSpec(
        run_id="run-123",
        image="python:3.13",
        command=("python", "-c", "print(1)"),
        worker_protocol="ronin/worker/v1",
    )


def test_kubernetes_adapter_owns_job_lifecycle():
    client = FakeClient()
    adapter = KubernetesExecutionAdapter(client)
    evidence = adapter.submit(_spec())
    assert evidence["job_name"] == "run-run-123"
    assert adapter.status("run-123") is not None
    adapter.cancel("run-123")
    assert adapter.status("run-123") is None
