"""PostgreSQL FinOps reader for the composed Ronin server profile."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from studio_core import WorkspaceId
from studio_orchestrator import Instant
from .contracts import BudgetPolicy, CostRecord, UsageRecord


def _psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("PostgreSQL FinOps requires psycopg") from exc
    return psycopg, dict_row


class PostgresFinOpsStore:
    """Read the durable FinOps ledger from the configured PostgreSQL database."""

    def __init__(self, dsn: str, *, application_name: str = "ronin-finops") -> None:
        self._dsn = dsn
        self._application_name = application_name
        psycopg, _ = _psycopg()
        with psycopg.connect(dsn, application_name=application_name) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS finops_usage (
                        usage_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
                        resource_type TEXT NOT NULL, quantity NUMERIC NOT NULL,
                        unit TEXT NOT NULL, period_start TEXT NOT NULL,
                        period_end TEXT NOT NULL, source_ref TEXT NOT NULL,
                        provenance TEXT NOT NULL, labels_json JSONB NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS finops_costs (
                        usage_id TEXT PRIMARY KEY REFERENCES finops_usage(usage_id),
                        workspace_id TEXT NOT NULL, amount NUMERIC NOT NULL,
                        currency TEXT NOT NULL, provenance TEXT NOT NULL,
                        rate_card_id TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS finops_budgets (
                        budget_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
                        currency TEXT NOT NULL, limit_amount NUMERIC NOT NULL,
                        period_start TEXT NOT NULL, period_end TEXT NOT NULL,
                        action TEXT NOT NULL, labels_json JSONB NOT NULL,
                        PRIMARY KEY (workspace_id, budget_id)
                    )
                """)

    def _connect(self):
        psycopg, dict_row = _psycopg()
        return psycopg.connect(self._dsn, row_factory=dict_row, application_name=self._application_name)

    def list_usage(self, workspace_id: WorkspaceId, *, period_start: Instant | str,
                   period_end: Instant | str) -> tuple[UsageRecord, ...]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM finops_usage WHERE workspace_id=%s
                AND period_end>%s AND period_start<%s ORDER BY period_start,usage_id""",
                           (workspace_id.value, str(Instant(period_start)), str(Instant(period_end))))
            return tuple(UsageRecord(str(row["usage_id"]), workspace_id, str(row["resource_type"]),
                Decimal(str(row["quantity"])), str(row["unit"]), Instant(row["period_start"]),
                Instant(row["period_end"]), str(row["source_ref"]), str(row["provenance"]),
                tuple(sorted((str(k), str(v)) for k, v in dict(row["labels_json"]).items()))) for row in cursor)

    def list_costs(self, workspace_id: WorkspaceId, *, period_start: Instant | str,
                   period_end: Instant | str) -> tuple[CostRecord, ...]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT c.* FROM finops_costs c JOIN finops_usage u USING (usage_id)
                WHERE c.workspace_id=%s AND u.period_end>%s AND u.period_start<%s
                ORDER BY u.period_start,c.usage_id""",
                (workspace_id.value, str(Instant(period_start)), str(Instant(period_end))))
            return tuple(CostRecord(str(row["usage_id"]), workspace_id, Decimal(str(row["amount"])),
                str(row["currency"]), str(row["provenance"]), str(row["rate_card_id"])) for row in cursor)

    def list_budgets(self, workspace_id: WorkspaceId) -> tuple[BudgetPolicy, ...]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM finops_budgets WHERE workspace_id=%s ORDER BY budget_id",
                           (workspace_id.value,))
            return tuple(BudgetPolicy(str(row["budget_id"]), workspace_id, str(row["currency"]),
                Decimal(str(row["limit_amount"])), Instant(row["period_start"]), Instant(row["period_end"]),
                str(row["action"]), tuple(sorted((str(k), str(v)) for k, v in dict(row["labels_json"]).items())))
                for row in cursor)


__all__ = ("PostgresFinOpsStore",)
