"""PostgreSQL FinOps reader for the composed Ronin server profile."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from studio_core import WorkspaceId
from studio_orchestrator import Instant
from .contracts import BudgetPolicy, CostRecord, RateCard, UsageRecord

from .store import FinOpsConflict


def _psycopg() -> tuple[Any, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("PostgreSQL FinOps requires psycopg") from exc
    return psycopg, dict_row


class PostgresFinOpsStore:
    """Durable PostgreSQL FinOps ledger for the composed Ronin server profile."""

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
                    CREATE TABLE IF NOT EXISTS finops_rate_cards (
                        rate_card_id TEXT PRIMARY KEY, resource_type TEXT NOT NULL,
                        unit TEXT NOT NULL, currency TEXT NOT NULL,
                        cost_per_unit NUMERIC NOT NULL, effective_from TEXT NOT NULL
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

    def record_usage(self, usage: UsageRecord) -> UsageRecord:
        payload = (usage.id, usage.workspace_id.value, usage.resource_type, str(usage.quantity),
                   usage.unit, str(usage.period_start), str(usage.period_end), usage.source_ref,
                   usage.provenance, json.dumps(dict(usage.labels), sort_keys=True))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM finops_usage WHERE usage_id=%s", (usage.id,))
            existing = cursor.fetchone()
            if existing is None:
                cursor.execute("""INSERT INTO finops_usage
                    (usage_id,workspace_id,resource_type,quantity,unit,period_start,period_end,
                     source_ref,provenance,labels_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", payload)
            elif (str(existing["usage_id"]), str(existing["workspace_id"]), str(existing["resource_type"]),
                  str(existing["quantity"]), str(existing["unit"]), str(existing["period_start"]),
                  str(existing["period_end"]), str(existing["source_ref"]), str(existing["provenance"]),
                  json.dumps(dict(existing["labels_json"]), sort_keys=True)) != payload:
                raise FinOpsConflict(f"usage id already exists with different content: {usage.id}")
        return usage

    def put_rate_card(self, rate: RateCard) -> RateCard:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO finops_rate_cards
                (rate_card_id,resource_type,unit,currency,cost_per_unit,effective_from)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (rate_card_id) DO UPDATE SET resource_type=EXCLUDED.resource_type,
                unit=EXCLUDED.unit,currency=EXCLUDED.currency,cost_per_unit=EXCLUDED.cost_per_unit,
                effective_from=EXCLUDED.effective_from""",
                (rate.id, rate.resource_type, rate.unit, rate.currency, str(rate.cost_per_unit), str(rate.effective_from)))
        return rate

    def resolve_rate(self, resource_type: str, unit: str, *, at: Instant | str) -> RateCard | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM finops_rate_cards WHERE resource_type=%s AND unit=%s
                AND effective_from<=%s ORDER BY effective_from DESC,rate_card_id DESC LIMIT 1""",
                (resource_type, unit, str(Instant(at))))
            row = cursor.fetchone()
            return None if row is None else RateCard(str(row["rate_card_id"]), resource_type, unit,
                str(row["currency"]), Decimal(str(row["cost_per_unit"])), Instant(row["effective_from"]))

    def record_cost(self, cost: CostRecord) -> CostRecord:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT workspace_id FROM finops_usage WHERE usage_id=%s", (cost.usage_id,))
            usage = cursor.fetchone()
            if usage is None:
                raise KeyError(f"usage record not found: {cost.usage_id}")
            if str(usage["workspace_id"]) != cost.workspace_id.value:
                raise FinOpsConflict("cost workspace does not match usage workspace")
            cursor.execute("""INSERT INTO finops_costs
                (usage_id,workspace_id,amount,currency,provenance,rate_card_id)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (usage_id) DO NOTHING""",
                (cost.usage_id, cost.workspace_id.value, str(cost.amount), cost.currency,
                 cost.provenance, cost.rate_card_id))
        return cost

    def put_budget(self, budget: BudgetPolicy) -> BudgetPolicy:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO finops_budgets
                (budget_id,workspace_id,currency,limit_amount,period_start,period_end,action,labels_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (workspace_id,budget_id) DO UPDATE SET currency=EXCLUDED.currency,
                limit_amount=EXCLUDED.limit_amount,period_start=EXCLUDED.period_start,
                period_end=EXCLUDED.period_end,action=EXCLUDED.action,labels_json=EXCLUDED.labels_json""",
                (budget.id, budget.workspace_id.value, budget.currency, str(budget.limit),
                 str(budget.period_start), str(budget.period_end), budget.action,
                 json.dumps(dict(budget.labels), sort_keys=True)))
        return budget

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
