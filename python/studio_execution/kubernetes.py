"""Pure Kubernetes manifest rendering for the runtime-neutral execution port.

This module does not import a Kubernetes client or make network calls. A later
adapter can submit the rendered object through the local kind/in-cluster API.
Keeping rendering pure makes policy and manifest tests deterministic.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from .backend import WorkloadSpec

_DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


class KubernetesManifestError(ValueError):
    """Raised when a workload cannot be represented safely as a Job."""


class KubernetesJobClient(Protocol):
    """Minimal client port implemented by an SDK adapter or a test double."""

    def create_job(self, manifest: dict[str, Any]) -> object: ...
    def get_job(self, *, namespace: str, name: str) -> object | None: ...
    def delete_job(self, *, namespace: str, name: str) -> None: ...
    def cancel_job(self, *, namespace: str, name: str) -> None: ...
    def get_job_logs(self, *, namespace: str, name: str, container: str) -> str: ...


def _label(value: str, field: str) -> str:
    candidate = value.lower().replace("_", "-")
    if len(candidate) > 63 or not _DNS_LABEL.fullmatch(candidate):
        raise KubernetesManifestError(f"{field} is not a valid Kubernetes label: {value!r}")
    return candidate


def render_job(spec: WorkloadSpec, *, namespace: str = "ronin-system") -> dict[str, Any]:
    """Render a restricted, non-privileged Kubernetes Job manifest."""

    namespace = _label(namespace, "namespace")
    run_id = _label(spec.run_id, "run_id")
    workload_id = _label(f"run-{spec.run_id}", "workload_id")
    labels = {
        "app.kubernetes.io/managed-by": "ronin",
        "ronin.io/run-id": run_id,
        "ronin.io/worker-protocol": _label(
            spec.worker_protocol.replace("/", "-"), "worker_protocol"
        ),
    }
    labels.update(
        {
            _label(key, "label key"): _label(value, "label value")
            for key, value in spec.labels.items()
        }
    )
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": workload_id, "namespace": namespace, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": spec.timeout_seconds,
            "ttlSecondsAfterFinished": 3600,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "automountServiceAccountToken": False,
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "worker",
                            "image": spec.image,
                            "command": list(spec.command),
                            "resources": {
                                "requests": {
                                    "cpu": spec.resource_limits.cpu,
                                    "memory": spec.resource_limits.memory,
                                },
                                "limits": {
                                    "cpu": spec.resource_limits.cpu,
                                    "memory": spec.resource_limits.memory,
                                    "ephemeral-storage": spec.resource_limits.ephemeral_storage,
                                },
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "runAsNonRoot": True,
                                "runAsUser": 65532,
                                "runAsGroup": 65532,
                            },
                        }
                    ],
                },
            },
        },
    }


class KubernetesExecutionAdapter:
    """Runtime-neutral lifecycle adapter around the rendered Job contract."""

    def __init__(self, client: KubernetesJobClient, *, namespace: str = "ronin-system") -> None:
        self._client = client
        self._namespace = _label(namespace, "namespace")

    def submit(self, spec: WorkloadSpec) -> dict[str, str]:
        manifest = render_job(spec, namespace=self._namespace)
        self._client.create_job(manifest)
        return {
            "run_id": spec.run_id,
            "namespace": self._namespace,
            "job_name": manifest["metadata"]["name"],
        }

    def status(self, run_id: str) -> object | None:
        name = _label(f"run-{run_id}", "workload_id")
        return self._client.get_job(namespace=self._namespace, name=name)

    def cancel(self, run_id: str) -> None:
        name = _label(f"run-{run_id}", "workload_id")
        cancel_job = getattr(self._client, "cancel_job", None)
        if cancel_job is not None:
            cancel_job(namespace=self._namespace, name=name)
            return
        # Older clients only exposed deletion; retain that safe cancellation
        # fallback while newer adapters can distinguish cancel from cleanup.
        self._client.delete_job(namespace=self._namespace, name=name)

    def cleanup(self, run_id: str) -> None:
        """Remove a completed/orphaned Job after evidence has been collected."""
        name = _label(f"run-{run_id}", "workload_id")
        self._client.delete_job(namespace=self._namespace, name=name)

    def logs(self, run_id: str, *, container: str = "worker") -> str:
        """Return provider logs through the bounded runtime-neutral client port."""
        container = _label(container, "container")
        name = _label(f"run-{run_id}", "workload_id")
        logs = self._client.get_job_logs(namespace=self._namespace, name=name, container=container)
        if not isinstance(logs, str):
            raise KubernetesManifestError("Kubernetes job logs must be text")
        return logs


__all__ = (
    "KubernetesExecutionAdapter",
    "KubernetesJobClient",
    "KubernetesManifestError",
    "render_job",
)
