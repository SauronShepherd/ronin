"""Pure per-cell resume identity and fail-closed reuse decisions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from studio_orchestrator.lifecycle import RunId


def _require_text(name: str, value: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be non-empty, trimmed, and single-line")
    return value


def _require_sha256(name: str, value: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
    return value


@dataclass(frozen=True, slots=True)
class CellExecutionIdentity:
    """Frozen inputs that make a succeeded cell result reusable across Attempts."""

    run_id: RunId
    cell_id: str
    source_digest: str
    repository_digest: str
    runtime_digest: str
    parameter_digest: str
    upstream_result_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text("cell id", self.cell_id)
        _require_sha256("source digest", self.source_digest)
        _require_sha256("repository digest", self.repository_digest)
        _require_sha256("runtime digest", self.runtime_digest)
        _require_sha256("parameter digest", self.parameter_digest)
        for digest in self.upstream_result_digests:
            _require_sha256("upstream result digest", digest)

    @property
    def digest(self) -> str:
        payload = {
            "cell_id": self.cell_id,
            "parameter_digest": self.parameter_digest,
            "repository_digest": self.repository_digest,
            "run_id": str(self.run_id),
            "runtime_digest": self.runtime_digest,
            "source_digest": self.source_digest,
            "upstream_result_digests": list(self.upstream_result_digests),
            "version": 1,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CellResumeRecord:
    run_id: RunId
    cell_id: str
    state: str
    execution_identity_digest: str
    artifact_digests: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text("cell id", self.cell_id)
        _require_text("cell state", self.state)
        _require_sha256("execution identity digest", self.execution_identity_digest)
        for digest in self.artifact_digests:
            _require_sha256("artifact digest", digest)


def can_resume_cell(
    current: CellExecutionIdentity,
    record: CellResumeRecord,
    *,
    artifacts_verified: bool,
) -> bool:
    """Return true only when a prior succeeded result is provably reusable."""
    return (
        record.state == "succeeded"
        and record.run_id == current.run_id
        and record.cell_id == current.cell_id
        and record.execution_identity_digest == current.digest
        and bool(record.artifact_digests)
        and artifacts_verified
    )


__all__ = ("CellExecutionIdentity", "CellResumeRecord", "can_resume_cell")
