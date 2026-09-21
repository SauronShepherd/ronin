"""Pure Kubernetes manifest rendering for the runtime-neutral execution port.

This module does not import a Kubernetes client or make network calls. A later
adapter can submit the rendered object through the local kind/in-cluster API.
Keeping rendering pure makes policy and manifest tests deterministic.
"""

from __future__ import annotations

import re
from typing import Any

from .backend import WorkloadSpec

_DNS_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


class KubernetesManifestError(ValueError):
    """Raised when a workload cannot be represented safely as a Job."""


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
        "ronin.io/worker-protocol": _label(spec.worker_protocol.replace("/", "-"), "worker_protocol"),
    }
    labels.update({_label(key, "label key"): _label(value, "label value") for key, value in spec.labels.items()})
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
                    "containers": [{
                        "name": "worker",
                        "image": spec.image,
                        "command": list(spec.command),
                        "resources": {
                            "requests": {"cpu": spec.resource_limits.cpu, "memory": spec.resource_limits.memory},
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
                    }],
                },
            },
        },
    }


__all__ = ("KubernetesManifestError", "render_job")
