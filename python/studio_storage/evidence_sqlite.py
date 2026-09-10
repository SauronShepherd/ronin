"""Evidence-aware extension of the canonical lease-fenced SQLite adapter."""

from __future__ import annotations

from studio_orchestrator import AttemptId, StoredEvidenceRef

from studio_storage.fenced_sqlite import SqliteJobStore as _FencedSqliteJobStore


class SqliteJobStore(_FencedSqliteJobStore):
    """Persist v1 evidence availability while preserving worker lease fencing."""

    def put_evidence(self, *args: object, **kwargs: object) -> None:
        owner = kwargs.pop("owner", None)
        lease_token = kwargs.pop("lease_token", None)
        now = kwargs.pop("now", None)
        keyword_attempt = kwargs.pop("attempt_id", None)
        keyword_ref = kwargs.pop("ref", None)
        if kwargs:
            raise TypeError("unexpected put_evidence arguments")

        if len(args) == 1 and keyword_attempt is None and keyword_ref is None:
            if isinstance(args[0], StoredEvidenceRef):
                raise ValueError("worker write requires active lease")
            raise TypeError("invalid put_evidence arguments")
        if not args and keyword_attempt is None and isinstance(keyword_ref, StoredEvidenceRef):
            raise ValueError("worker write requires active lease")

        if len(args) == 2 and keyword_attempt is None and keyword_ref is None:
            attempt_id, ref = args
        elif not args and keyword_attempt is not None and keyword_ref is not None:
            attempt_id, ref = keyword_attempt, keyword_ref
        else:
            raise TypeError("invalid put_evidence arguments")
        if not isinstance(attempt_id, AttemptId) or not isinstance(ref, StoredEvidenceRef):
            raise TypeError("invalid put_evidence arguments")

        owner, lease_token, current = self._require_write_lease(
            owner=owner,
            lease_token=lease_token,
            now=now,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            attempt = self._active_attempt_row(
                connection,
                attempt_id,
                owner=owner,
                lease_token=lease_token,
                now=current,
            )
            if ref.run_id.value != attempt["run_id"]:
                raise ValueError("evidence run does not match attempt")
            connection.execute(
                "INSERT OR REPLACE INTO evidence_refs("
                "run_id,cell_id,role,digest_algorithm,digest,media_type,size_bytes,storage_ref,"
                "availability,unavailable_reason) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    str(ref.run_id),
                    ref.cell_id,
                    ref.role,
                    ref.digest_algorithm,
                    ref.digest,
                    ref.media_type,
                    ref.size_bytes,
                    ref.storage_ref,
                    ref.availability.value,
                    ref.unavailable_reason,
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


__all__ = ("SqliteJobStore",)
