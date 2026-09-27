"""Run/Evidence bridge for Migration Studio qualification artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .benchmark import BenchmarkResult, OptimizationDecision, promotion_evidence
from .validation import ValidationReport


@dataclass(frozen=True, slots=True)
class MigrationEvidence:
    """Canonical evidence payload and its content-addressed Run reference."""

    run_id: object
    cell_id: str
    role: str
    payload: dict[str, object]

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def reference(self, factory: Callable[..., object], storage_ref: str) -> object:
        content = self.canonical_bytes()
        return factory(
            run_id=self.run_id,
            cell_id=self.cell_id,
            role=self.role,
            digest_algorithm="sha256",
            digest=hashlib.sha256(content).hexdigest(),
            media_type="application/json",
            size_bytes=len(content),
            storage_ref=storage_ref,
        )


def validation_evidence(
    report: ValidationReport,
    *,
    run_id: object,
    cell_id: str,
    storage_ref: str,
) -> MigrationEvidence:
    """Convert a validation result into a provenance-bearing Run evidence cell."""
    if not cell_id or cell_id != cell_id.strip():
        raise ValueError("cell_id must be non-empty and trimmed")
    if not storage_ref or storage_ref != storage_ref.strip():
        raise ValueError("storage_ref must be non-empty and trimmed")
    return MigrationEvidence(
        run_id,
        cell_id,
        "migration-validation",
        {
            "schema": "ronin.migration.validation-evidence/v1",
            "asset_id": report.asset_id,
            "level": report.level,
            "status": report.status,
            "report_digest": report.digest,
            "expected_digest": report.expected_digest,
            "actual_digest": report.actual_digest,
            "checks": report.to_payload()["checks"],
            "storage_ref": storage_ref,
        },
    )


def publish_migration_evidence(
    store: object,
    evidence: MigrationEvidence,
    *,
    evidence_ref_factory: Callable[..., object],
    attempt_id: object,
    owner: str,
    lease_token: object,
    now: object,
    storage_ref: str,
) -> object:
    """Publish through Ronin's fenced evidence contract, never a parallel store."""
    reference = evidence.reference(evidence_ref_factory, storage_ref)
    put_evidence = getattr(store, "put_evidence", None)
    if not callable(put_evidence):
        raise TypeError("store must provide fenced put_evidence")
    put_evidence(
        attempt_id,
        reference,
        owner=owner,
        lease_token=lease_token,
        now=now,
    )
    return reference


def publish_validation_evidence(
    store: object,
    report: ValidationReport,
    *,
    run_id: object,
    cell_id: str,
    attempt_id: object,
    owner: str,
    lease_token: object,
    now: object,
    evidence_ref_factory: Callable[..., object],
    storage_ref: str,
) -> object:
    """Create and publish validation evidence in one fenced operation."""
    return publish_migration_evidence(
        store,
        validation_evidence(report, run_id=run_id, cell_id=cell_id, storage_ref=storage_ref),
        evidence_ref_factory=evidence_ref_factory,
        attempt_id=attempt_id,
        owner=owner,
        lease_token=lease_token,
        now=now,
        storage_ref=storage_ref,
    )


def publish_promotion_evidence(
    store: object,
    decision: OptimizationDecision,
    *,
    baseline: BenchmarkResult,
    candidate: BenchmarkResult,
    semantic_passed: bool,
    quality_passed: bool,
    run_id: object,
    cell_id: str,
    attempt_id: object,
    owner: str,
    lease_token: object,
    now: object,
    evidence_ref_factory: Callable[..., object],
    storage_ref: str,
) -> object:
    """Create and publish safe-promotion evidence in one fenced operation."""
    evidence = MigrationEvidence(
        run_id,
        cell_id,
        "migration-optimization",
        promotion_evidence(
            decision,
            baseline=baseline,
            candidate=candidate,
            semantic_passed=semantic_passed,
            quality_passed=quality_passed,
        ),
    )
    return publish_migration_evidence(
        store,
        evidence,
        evidence_ref_factory=evidence_ref_factory,
        attempt_id=attempt_id,
        owner=owner,
        lease_token=lease_token,
        now=now,
        storage_ref=storage_ref,
    )


def publish_evidence_bundle(
    store: object,
    evidence: Iterable[MigrationEvidence],
    *,
    attempt_id: object,
    owner: str,
    lease_token: object,
    now: object,
    evidence_ref_factory: Callable[..., object],
    storage_prefix: str,
) -> tuple[object, ...]:
    """Publish a worker's evidence bundle under one fenced attempt context."""
    if not storage_prefix or storage_prefix != storage_prefix.strip():
        raise ValueError("storage_prefix must be non-empty and trimmed")
    items = tuple(evidence)
    cell_ids = [item.cell_id for item in items]
    if any(
        not cell_id
        or cell_id != cell_id.strip()
        or cell_id in {".", ".."}
        or "/" in cell_id
        or "\\" in cell_id
        for cell_id in cell_ids
    ):
        raise ValueError("bundle cell_id must be a path-safe non-empty token")
    if len(set(cell_ids)) != len(cell_ids):
        raise ValueError("bundle cell_id values must be unique")
    return tuple(
        publish_migration_evidence(
            store,
            item,
            evidence_ref_factory=evidence_ref_factory,
            attempt_id=attempt_id,
            owner=owner,
            lease_token=lease_token,
            now=now,
            storage_ref=f"{storage_prefix.rstrip('/')}/{item.cell_id}.json",
        )
        for item in items
    )


__all__ = (
    "MigrationEvidence",
    "publish_migration_evidence",
    "publish_evidence_bundle",
    "publish_promotion_evidence",
    "publish_validation_evidence",
    "validation_evidence",
)
