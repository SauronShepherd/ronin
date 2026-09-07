"""Portable execution-evidence adapters layered over local runner persistence."""

from __future__ import annotations

import hashlib

from studio_kernel import CellExecutionRequest, ExecutionAttemptId, ExecutionEvidenceReference

from .container import LocalExecutionEvidenceStore as _OpaqueLocalExecutionEvidenceStore


class PortableLocalExecutionEvidenceStore(_OpaqueLocalExecutionEvidenceStore):
    """Preserve local persistence while adding location-independent content identity."""

    def persist_json(
        self,
        kind: str,
        attempt_id: ExecutionAttemptId,
        cell: CellExecutionRequest,
        payload: dict[str, object],
    ) -> ExecutionEvidenceReference:
        opaque = super().persist_json(kind, attempt_id, cell, payload)
        prefix = "local-evidence://"
        if not opaque.ref.startswith(prefix):
            raise ValueError("local evidence store returned an unsupported locator")
        data = (self.root / opaque.ref.removeprefix(prefix)).read_bytes()
        return ExecutionEvidenceReference(
            opaque.kind,
            opaque.ref,
            "sha256",
            hashlib.sha256(data).hexdigest(),
            "application/vnd.ronin.execution-evidence+json",
            len(data),
        )


__all__ = ["PortableLocalExecutionEvidenceStore"]
