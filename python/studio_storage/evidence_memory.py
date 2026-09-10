"""Evidence-bounded in-memory adapter matching the SQLite v0.1 contract."""

from __future__ import annotations

from studio_orchestrator import AttemptId, Instant, LeaseToken, StoredEvidenceRef

from studio_storage.evidence_sqlite import MAX_EVIDENCE_REFS_PER_RUN
from studio_storage.paged_store import InMemoryJobStore as _PagedInMemoryJobStore


class InMemoryJobStore(_PagedInMemoryJobStore):
    """Reference adapter with the same per-Run evidence bound as SQLite."""

    def put_evidence(
        self,
        attempt_id: AttemptId,
        ref: StoredEvidenceRef,
        *,
        owner: str,
        lease_token: LeaseToken,
        now: Instant | str,
    ) -> None:
        with self._lock:
            attempt = self._active_attempt_for_write(
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=now,
            )
            if ref.run_id != attempt.run_id:
                raise ValueError("evidence run does not match attempt")
            target = self._evidence.setdefault(ref.run_id, [])
            if len(target) >= MAX_EVIDENCE_REFS_PER_RUN:
                raise ValueError(
                    f"run evidence must contain at most {MAX_EVIDENCE_REFS_PER_RUN} references"
                )
            target.append(ref)


__all__ = ("InMemoryJobStore",)
