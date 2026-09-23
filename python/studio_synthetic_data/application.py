"""Application service for the local Govern Studio workflow.

This is intentionally storage-port shaped: the current reference adapter keeps
records in memory, while the next persistence adapter can replace the store
without changing the commands or plugin routes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Any, Protocol

from .engine import (
    CsvExporter,
    ExporterRegistry,
    GenerationPlan,
    GenerationResult,
    GovernanceState,
    SyntheticTable,
    ValidationReport,
    generate,
    validate,
)


class RunStatus(StrEnum):
    CREATED = "created"
    GENERATED = "generated"
    VALIDATED = "validated"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class GovernRun:
    run_id: str
    plan_fingerprint: str
    status: RunStatus
    result: GenerationResult | None = None
    validation: object | None = None
    error: str | None = None


class GovernRunStore(Protocol):
    """Persistence port for Govern Studio runs."""

    def put(self, run: GovernRun, *, idempotency_key: str, plan: GenerationPlan) -> None: ...
    def get(self, run_id: str) -> GovernRun: ...
    def find_by_idempotency(self, key: str) -> GovernRun | None: ...
    def all(self) -> tuple[GovernRun, ...]: ...
    def add_artifact(self, run_id: str, artifact: dict[str, Any]) -> None: ...
    def artifacts(self, run_id: str) -> tuple[dict[str, Any], ...]: ...


def _plan_payload(plan: GenerationPlan) -> dict[str, Any]:
    return {
        "seed": plan.seed,
        "tables": [
            {
                "name": t.name,
                "rows": t.rows,
                "primary_key": t.primary_key,
                "columns": [
                    {
                        "name": c.name,
                        "kind": c.kind,
                        "nullable": c.nullable,
                        "null_rate": c.null_rate,
                        "values": list(c.values),
                        "minimum": c.minimum,
                        "maximum": c.maximum,
                    }
                    for c in t.columns
                ],
            }
            for t in plan.tables
        ],
        "relationships": [
            {
                "child_table": r.child_table,
                "child_column": r.child_column,
                "parent_table": r.parent_table,
                "parent_column": r.parent_column,
            }
            for r in plan.relationships
        ],
    }


def _plan_fingerprint(plan: GenerationPlan) -> str:
    payload = json.dumps(_plan_payload(plan), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _result_json(result: GenerationResult | None) -> str | None:
    if result is None:
        return None
    return json.dumps(
        {
            "tables": [{"name": t.name, "rows": list(t.rows)} for t in result.tables],
            "plan_fingerprint": result.plan_fingerprint,
            "warnings": list(result.warnings),
            "state": result.state.value,
        },
        sort_keys=True,
    )


def _result_from_json(value: str | None) -> GenerationResult | None:
    if not value:
        return None
    payload = json.loads(value)
    return GenerationResult(
        tuple(SyntheticTable(t["name"], tuple(t["rows"])) for t in payload["tables"]),
        payload["plan_fingerprint"],
        tuple(payload["warnings"]),
        GovernanceState(payload["state"]),
    )


def _validation_json(report: object | None) -> str | None:
    if report is None:
        return None
    return json.dumps(
        {
            "passed": report.passed,
            "checks": list(report.checks),
            "errors": list(report.errors),
            "evidence_id": report.evidence_id,
        },
        sort_keys=True,
    )


def _validation_from_json(value: str | None) -> ValidationReport | None:
    if not value:
        return None
    payload = json.loads(value)
    return ValidationReport(
        payload["passed"],
        tuple(payload["checks"]),
        tuple(payload["errors"]),
        payload["evidence_id"],
    )


class InMemoryRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, GovernRun] = {}
        self._keys: dict[str, str] = {}
        self._artifacts: dict[str, list[dict[str, Any]]] = {}

    def put(self, run: GovernRun, *, idempotency_key: str, plan: GenerationPlan) -> None:
        del plan
        self._keys[idempotency_key] = run.run_id
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> GovernRun:
        return self._runs[run_id]

    def find_by_idempotency(self, key: str) -> GovernRun | None:
        run_id = self._keys.get(key)
        return self._runs.get(run_id) if run_id else None

    def all(self) -> tuple[GovernRun, ...]:
        return tuple(self._runs.values())

    def add_artifact(self, run_id: str, artifact: dict[str, Any]) -> None:
        if run_id not in self._runs:
            raise KeyError(run_id)
        self._artifacts.setdefault(run_id, []).append(dict(artifact))

    def artifacts(self, run_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(self._artifacts.get(run_id, ()))


class SqliteRunStore:
    """Durable local adapter; the database is deliberately portable SQLite."""

    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = RLock()
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            raise ValueError(f"unsupported Govern Studio database version: {version}")
        self._db.execute("""CREATE TABLE IF NOT EXISTS govern_runs (
            run_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
            plan_json TEXT NOT NULL, plan_fingerprint TEXT NOT NULL, status TEXT NOT NULL,
            result_json TEXT, validation_json TEXT, error TEXT)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS govern_artifacts (
            run_id TEXT NOT NULL, sequence INTEGER NOT NULL, artifact_json TEXT NOT NULL,
            PRIMARY KEY (run_id, sequence), FOREIGN KEY (run_id) REFERENCES govern_runs(run_id))""")
        if version == 0:
            self._db.execute("PRAGMA user_version = 1")
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def put(self, run: GovernRun, *, idempotency_key: str, plan: GenerationPlan) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            self._db.execute(
                """INSERT INTO govern_runs
            (run_id,idempotency_key,plan_json,plan_fingerprint,status,result_json,validation_json,error)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET
            status=excluded.status,result_json=excluded.result_json,
            validation_json=excluded.validation_json,error=excluded.error""",
                (
                    run.run_id,
                    idempotency_key,
                    json.dumps(_plan_payload(plan), sort_keys=True),
                    run.plan_fingerprint,
                    run.status.value,
                    _result_json(run.result),
                    _validation_json(run.validation),
                    run.error,
                ),
            )
            self._db.commit()

    @staticmethod
    def _row(row: tuple[Any, ...]) -> GovernRun:
        return GovernRun(
            row[0],
            row[3],
            RunStatus(row[4]),
            _result_from_json(row[5]),
            _validation_from_json(row[6]),
            row[7],
        )

    def get(self, run_id: str) -> GovernRun:
        with self._lock:
            row = self._db.execute(
                "SELECT run_id,idempotency_key,plan_json,plan_fingerprint,status,result_json,validation_json,error FROM govern_runs WHERE run_id=?",  # noqa: E501
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return self._row(row)

    def find_by_idempotency(self, key: str) -> GovernRun | None:
        with self._lock:
            row = self._db.execute(
                "SELECT run_id,idempotency_key,plan_json,plan_fingerprint,status,result_json,validation_json,error FROM govern_runs WHERE idempotency_key=?",  # noqa: E501
                (key,),
            ).fetchone()
        return self._row(row) if row else None

    def all(self) -> tuple[GovernRun, ...]:
        with self._lock:
            return tuple(
                self._row(row)
                for row in self._db.execute(
                    "SELECT run_id,idempotency_key,plan_json,plan_fingerprint,status,result_json,validation_json,error FROM govern_runs ORDER BY run_id"  # noqa: E501
                )
            )

    def add_artifact(self, run_id: str, artifact: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            sequence = self._db.execute(
                "SELECT COALESCE(MAX(sequence), -1) + 1 FROM govern_artifacts WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
            self._db.execute(
                "INSERT INTO govern_artifacts(run_id,sequence,artifact_json) VALUES(?,?,?)",
                (run_id, sequence, json.dumps(artifact, sort_keys=True)),
            )
            self._db.commit()

    def artifacts(self, run_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._db.execute(
                "SELECT artifact_json FROM govern_artifacts WHERE run_id=? ORDER BY sequence",
                (run_id,),
            )
            return tuple(json.loads(row[0]) for row in rows)


class GovernStudioService:
    """Idempotent local service for plan -> generate -> validate."""

    def __init__(
        self,
        store: GovernRunStore | None = None,
        *,
        publication_hook: Callable[[str, GenerationResult], None] | None = None,
    ) -> None:
        self._store = store or InMemoryRunStore()
        self._publication_hook = publication_hook
        self._lock = RLock()

    def create_run(self, plan: GenerationPlan, *, idempotency_key: str) -> GovernRun:
        if not idempotency_key.strip():
            raise ValueError("idempotency key is required")
        plan_fingerprint = _plan_fingerprint(plan)
        run_id = f"run-{plan_fingerprint}"
        with self._lock:
            existing = self._store.find_by_idempotency(idempotency_key)
            if existing is not None:
                if existing.plan_fingerprint != plan_fingerprint:
                    raise ValueError("idempotency key already belongs to another plan") from None
                return existing
            run = GovernRun(run_id, plan_fingerprint, RunStatus.CREATED)
            try:
                self._store.put(run, idempotency_key=idempotency_key, plan=plan)
            except sqlite3.IntegrityError as exc:
                # Another process won the idempotency race; return its durable record.
                winner = self._store.find_by_idempotency(idempotency_key)
                if winner is None:
                    raise exc from None
                if winner.plan_fingerprint != plan_fingerprint:
                    raise ValueError("idempotency key already belongs to another plan") from None
                return winner
            return run

    def generate(self, run_id: str, plan: GenerationPlan) -> GovernRun:
        with self._lock:
            run = self._store.get(run_id)
            if run.plan_fingerprint != _plan_fingerprint(plan):
                raise ValueError("plan does not match the run fingerprint")
            if run.status is RunStatus.GENERATED and run.result is not None:
                return run
            try:
                result = generate(plan)
            except Exception as exc:
                failed = GovernRun(
                    run.run_id, run.plan_fingerprint, RunStatus.FAILED, error=str(exc)
                )
                self._store.put(failed, idempotency_key=run_id, plan=plan)
                return failed
            updated = GovernRun(
                run.run_id, run.plan_fingerprint, RunStatus.GENERATED, result=result
            )
            if self._publication_hook is not None:
                try:
                    self._publication_hook(run.run_id, result)
                except Exception as exc:
                    failed = GovernRun(
                        run.run_id,
                        run.plan_fingerprint,
                        RunStatus.FAILED,
                        result=result,
                        error=f"output publication failed: {exc}",
                    )
                    self._store.put(failed, idempotency_key=run_id, plan=plan)
                    return failed
            self._store.put(updated, idempotency_key=run_id, plan=plan)
            return updated

    def validate(self, run_id: str, plan: GenerationPlan) -> GovernRun:
        with self._lock:
            run = self._store.get(run_id)
            if run.plan_fingerprint != _plan_fingerprint(plan):
                raise ValueError("plan does not match the run fingerprint")
            if run.result is None:
                raise ValueError("run has no generated result")
            report = validate(plan, run.result)
            status = RunStatus.VALIDATED if report.passed else RunStatus.FAILED
            updated = GovernRun(run.run_id, run.plan_fingerprint, status, run.result, report)
            self._store.put(updated, idempotency_key=run_id, plan=plan)
            return updated

    def get_run(self, run_id: str) -> GovernRun:
        with self._lock:
            return self._store.get(run_id)

    def snapshot(self) -> tuple[GovernRun, ...]:
        with self._lock:
            return self._store.all()

    def export(self, run_id: str, *, format_id: str, table_name: str) -> str:
        """Serialize one generated table through the extensible format registry."""
        with self._lock:
            run = self._store.get(run_id)
            if run.result is None:
                raise ValueError("run has no generated result")
            table = next((item for item in run.result.tables if item.name == table_name), None)
            if table is None:
                raise ValueError(f"unknown generated table: {table_name}")
            from .formats import builtin_format_providers

            registry = ExporterRegistry((CsvExporter(),))
            for provider in builtin_format_providers():
                if provider.format_id not in registry.formats:
                    registry.register(provider)
            content = registry.export(format_id, table)
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            self._store.add_artifact(
                run_id,
                {
                    "format_id": format_id,
                    "table": table_name,
                    "size_bytes": len(content.encode("utf-8")),
                    "digest": digest,
                    "storage_ref": f"artifact://sha256/{digest}",
                },
            )
            return content

    def artifacts(self, run_id: str) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return self._store.artifacts(run_id)


def plan_from_payload(payload: Mapping[str, Any]) -> GenerationPlan:
    """Parse the minimal UI/API plan shape without accepting executable code."""
    from .engine import ColumnSpec, ForeignKey, TableSpec

    tables = tuple(
        TableSpec(
            str(table["name"]),
            tuple(
                ColumnSpec(
                    str(column["name"]),
                    str(column.get("kind", "string")),
                    bool(column.get("nullable", True)),
                    float(column.get("null_rate", 0)),
                    tuple(str(value) for value in column.get("values", ())),
                    int(column.get("minimum", 0)),
                    int(column.get("maximum", 100)),
                )
                for column in table.get("columns", ())
            ),
            table.get("primary_key"),
            int(table.get("rows", 100)),
        )
        for table in payload.get("tables", ())
    )
    relationships = tuple(
        ForeignKey(
            str(item["child_table"]),
            str(item["child_column"]),
            str(item["parent_table"]),
            str(item["parent_column"]),
        )
        for item in payload.get("relationships", ())
    )
    return GenerationPlan(tables, relationships, int(payload.get("seed", 0)))


__all__ = [
    "GovernRun",
    "GovernRunStore",
    "InMemoryRunStore",
    "SqliteRunStore",
    "GovernStudioService",
    "RunStatus",
    "plan_from_payload",
]
