"""Explicit dispatch boundary for scheduler workload families."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from studio_orchestrator import Job
from studio_sql import SqlEngine

from .scheduler_sql import SchedulerSqlResult, execute_scheduler_sql


class UnsupportedSchedulerWorkload(RuntimeError):
    """Raised when a scheduler workload has no qualified runtime adapter."""


@dataclass(frozen=True, slots=True)
class SchedulerWorkloadResult:
    family: str
    sql: SchedulerSqlResult | None = None

    def evidence_payload(self) -> dict[str, Any]:
        """Return the portable, deterministic payload stored as scheduler evidence."""

        if self.family == "sql" and self.sql is not None:
            return {
                "family": self.family,
                "evidence_digest": self.sql.evidence_digest,
                "columns": [
                    {"name": column.name, "type": column.type_name}
                    for column in self.sql.result.columns
                ],
                "rows": [list(row) for row in self.sql.result.rows],
                "version": 1,
            }
        raise UnsupportedSchedulerWorkload("scheduler result has no portable evidence payload")


def execute_scheduler_job(
    job: Job,
    *,
    sql_engine: SqlEngine | None = None,
    max_rows: int = 10_000,
    timeout_seconds: int | None = None,
) -> SchedulerWorkloadResult:
    """Dispatch a scheduler Job without falling back to notebook semantics."""

    if job.target == "sql.query":
        if sql_engine is None:
            raise UnsupportedSchedulerWorkload("sql.query requires an injected SQL engine")
        return SchedulerWorkloadResult(
            family="sql",
            sql=execute_scheduler_sql(
                job,
                sql_engine,
                max_rows=max_rows,
                timeout_seconds=timeout_seconds,
            ),
        )
    raise UnsupportedSchedulerWorkload(f"no qualified scheduler adapter for {job.target}")


__all__ = ("SchedulerWorkloadResult", "UnsupportedSchedulerWorkload", "execute_scheduler_job")
