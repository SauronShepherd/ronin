"""Durable SQLite FinOps ledger for the Ronin reference profile."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

from studio_core import WorkspaceId
from studio_orchestrator import Instant

from .contracts import BudgetPolicy, CostRecord, RateCard, UsageRecord


class FinOpsConflict(RuntimeError):
    """Raised when immutable ledger identity is reused with different content."""


class SqliteFinOpsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS finops_usage (
                    usage_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    labels_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS finops_usage_workspace_period_idx
                    ON finops_usage(workspace_id, period_start, period_end);
                CREATE TABLE IF NOT EXISTS finops_rate_cards (
                    rate_card_id TEXT PRIMARY KEY,
                    resource_type TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    cost_per_unit TEXT NOT NULL,
                    effective_from TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS finops_rate_lookup_idx
                    ON finops_rate_cards(resource_type, unit, effective_from);
                CREATE TABLE IF NOT EXISTS finops_costs (
                    usage_id TEXT PRIMARY KEY REFERENCES finops_usage(usage_id) ON DELETE CASCADE,
                    workspace_id TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    rate_card_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS finops_budgets (
                    budget_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    limit_amount TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    action TEXT NOT NULL,
                    labels_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS finops_budget_workspace_idx
                    ON finops_budgets(workspace_id, period_start, period_end);
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _labels(values: tuple[tuple[str, str], ...]) -> str:
        return json.dumps(dict(values), sort_keys=True, separators=(",", ":"))

    def record_usage(self, usage: UsageRecord) -> UsageRecord:
        payload = (
            usage.workspace_id.value,
            usage.resource_type,
            str(usage.quantity),
            usage.unit,
            str(usage.period_start),
            str(usage.period_end),
            usage.source_ref,
            usage.provenance,
            self._labels(usage.labels),
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT workspace_id,resource_type,quantity,unit,period_start,period_end,"
                "source_ref,provenance,labels_json FROM finops_usage WHERE usage_id=?",
                (usage.id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO finops_usage(usage_id,workspace_id,resource_type,quantity,unit,"
                    "period_start,period_end,source_ref,provenance,labels_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (usage.id, *payload),
                )
            elif tuple(existing) != payload:
                raise FinOpsConflict(f"usage id already exists with different content: {usage.id}")
            connection.commit()
            return usage
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def put_rate_card(self, rate: RateCard) -> RateCard:
        payload = (
            rate.resource_type,
            rate.unit,
            rate.currency,
            str(rate.cost_per_unit),
            str(rate.effective_from),
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT resource_type,unit,currency,cost_per_unit,effective_from "
                "FROM finops_rate_cards WHERE rate_card_id=?",
                (rate.id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO finops_rate_cards(rate_card_id,resource_type,unit,currency,"
                    "cost_per_unit,effective_from) VALUES (?,?,?,?,?,?)",
                    (rate.id, *payload),
                )
            elif tuple(existing) != payload:
                raise FinOpsConflict(
                    f"rate card id already exists with different content: {rate.id}"
                )
            connection.commit()
            return rate
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def resolve_rate(
        self,
        resource_type: str,
        unit: str,
        *,
        at: Instant | str,
    ) -> RateCard | None:
        moment = Instant(at)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT rate_card_id,currency,cost_per_unit,effective_from "
                "FROM finops_rate_cards WHERE resource_type=? AND unit=? AND effective_from<=? "
                "ORDER BY effective_from DESC, rate_card_id DESC LIMIT 1",
                (resource_type, unit, str(moment)),
            ).fetchone()
            if row is None:
                return None
            return RateCard(
                str(row[0]),
                resource_type,
                unit,
                str(row[1]),
                Decimal(str(row[2])),
                Instant(row[3]),
            )
        finally:
            connection.close()

    def record_cost(self, cost: CostRecord) -> CostRecord:
        payload = (
            cost.workspace_id.value,
            str(cost.amount),
            cost.currency,
            cost.provenance,
            cost.rate_card_id,
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            usage = connection.execute(
                "SELECT workspace_id FROM finops_usage WHERE usage_id=?",
                (cost.usage_id,),
            ).fetchone()
            if usage is None:
                raise KeyError(f"usage record not found: {cost.usage_id}")
            if usage[0] != cost.workspace_id.value:
                raise FinOpsConflict("cost workspace does not match usage workspace")
            existing = connection.execute(
                "SELECT workspace_id,amount,currency,provenance,rate_card_id "
                "FROM finops_costs WHERE usage_id=?",
                (cost.usage_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO finops_costs(usage_id,workspace_id,amount,currency,provenance,rate_card_id) "
                    "VALUES (?,?,?,?,?,?)",
                    (cost.usage_id, *payload),
                )
            elif tuple(existing) != payload:
                raise FinOpsConflict(
                    f"cost for usage already exists with different content: {cost.usage_id}"
                )
            connection.commit()
            return cost
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def put_budget(self, budget: BudgetPolicy) -> BudgetPolicy:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO finops_budgets(budget_id,workspace_id,currency,limit_amount,period_start,"
                "period_end,action,labels_json) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(budget_id) DO UPDATE SET workspace_id=excluded.workspace_id,"
                "currency=excluded.currency,limit_amount=excluded.limit_amount,"
                "period_start=excluded.period_start,period_end=excluded.period_end,"
                "action=excluded.action,labels_json=excluded.labels_json",
                (
                    budget.id,
                    budget.workspace_id.value,
                    budget.currency,
                    str(budget.limit),
                    str(budget.period_start),
                    str(budget.period_end),
                    budget.action,
                    self._labels(budget.labels),
                ),
            )
            connection.commit()
            return budget
        finally:
            connection.close()

    def list_usage(
        self,
        workspace_id: WorkspaceId,
        *,
        period_start: Instant | str,
        period_end: Instant | str,
    ) -> tuple[UsageRecord, ...]:
        start = Instant(period_start)
        end = Instant(period_end)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT usage_id,resource_type,quantity,unit,period_start,period_end,source_ref,"
                "provenance,labels_json FROM finops_usage WHERE workspace_id=? "
                "AND period_end>? AND period_start<? ORDER BY period_start,usage_id",
                (workspace_id.value, str(start), str(end)),
            ).fetchall()
            result: list[UsageRecord] = []
            for row in rows:
                labels = json.loads(row[8])
                result.append(
                    UsageRecord(
                        str(row[0]),
                        workspace_id,
                        str(row[1]),
                        Decimal(str(row[2])),
                        str(row[3]),
                        Instant(row[4]),
                        Instant(row[5]),
                        str(row[6]),
                        str(row[7]),  # type: ignore[arg-type]
                        tuple(sorted((str(key), str(value)) for key, value in labels.items())),
                    )
                )
            return tuple(result)
        finally:
            connection.close()

    def list_costs(
        self,
        workspace_id: WorkspaceId,
        *,
        period_start: Instant | str,
        period_end: Instant | str,
    ) -> tuple[CostRecord, ...]:
        start = Instant(period_start)
        end = Instant(period_end)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT c.usage_id,c.amount,c.currency,c.provenance,c.rate_card_id "
                "FROM finops_costs c JOIN finops_usage u ON u.usage_id=c.usage_id "
                "WHERE c.workspace_id=? AND u.period_end>? AND u.period_start<? "
                "ORDER BY u.period_start,c.usage_id",
                (workspace_id.value, str(start), str(end)),
            ).fetchall()
            return tuple(
                CostRecord(
                    str(row[0]),
                    workspace_id,
                    Decimal(str(row[1])),
                    str(row[2]),
                    str(row[3]),  # type: ignore[arg-type]
                    str(row[4]),
                )
                for row in rows
            )
        finally:
            connection.close()


__all__ = ("FinOpsConflict", "SqliteFinOpsStore")
