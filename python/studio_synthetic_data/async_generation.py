"""Bounded local asynchronous generation facade."""

from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event, RLock, Thread
from uuid import uuid4

from .application import GovernStudioService, _plan_payload, plan_from_payload
from .engine import GenerationPlan


@dataclass(frozen=True, slots=True)
class GenerationJob:
    job_id: str
    run_id: str
    status: str
    error: str | None = None


class LocalGenerationJobs:
    def __init__(
        self, service: GovernStudioService, *, workers: int = 2, db_path: str | None = None
    ) -> None:
        self._service = service
        self._owner = uuid4().hex
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sds")
        self._jobs: dict[str, GenerationJob] = {}
        self._futures: dict[str, Future[object]] = {}
        self._lock = RLock()
        self._db = sqlite3.connect(db_path, check_same_thread=False) if db_path else None
        if self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS synthetic_jobs (job_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, plan_json TEXT NOT NULL, status TEXT NOT NULL, error TEXT, lease_owner TEXT, lease_epoch INTEGER NOT NULL DEFAULT 0, lease_expires_at REAL)"
            )
            for statement in (
                "ALTER TABLE synthetic_jobs ADD COLUMN lease_owner TEXT",
                "ALTER TABLE synthetic_jobs ADD COLUMN lease_epoch INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE synthetic_jobs ADD COLUMN lease_expires_at REAL",
            ):
                try:
                    self._db.execute(statement)
                except sqlite3.OperationalError:
                    pass
            self._db.commit()
            for job_id, run_id, plan_json in self._db.execute(
                "SELECT job_id,run_id,plan_json FROM synthetic_jobs WHERE status='queued' OR (status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)",
                (time.time(),),
            ).fetchall():
                self._jobs[job_id] = GenerationJob(job_id, run_id, "queued")
                self._db.execute(
                    "UPDATE synthetic_jobs SET status='queued',lease_owner=NULL,lease_expires_at=NULL,error=NULL WHERE job_id=?",
                    (job_id,),
                )
                self._futures[job_id] = self._executor.submit(
                    self._execute, job_id, run_id, plan_from_payload(json.loads(plan_json))
                )
            self._db.commit()

    def submit(self, plan: GenerationPlan, *, idempotency_key: str) -> GenerationJob:
        run = self._service.create_run(plan, idempotency_key=idempotency_key)
        job = GenerationJob(uuid4().hex, run.run_id, "queued")
        with self._lock:
            self._jobs[job.job_id] = job
            if self._db:
                self._db.execute(
                    "INSERT INTO synthetic_jobs(job_id,run_id,plan_json,status,error) VALUES(?,?,?,?,?)",
                    (
                        job.job_id,
                        job.run_id,
                        json.dumps(_plan_payload(plan), sort_keys=True),
                        job.status,
                        None,
                    ),
                )
                self._db.commit()
            future = self._executor.submit(self._execute, job.job_id, run.run_id, plan)
            self._futures[job.job_id] = future
        return job

    def _execute(self, job_id: str, run_id: str, plan: GenerationPlan) -> None:
        with self._lock:
            if self._db:
                claimed = self._db.execute(
                    "UPDATE synthetic_jobs SET status='running',lease_owner=?,lease_epoch=lease_epoch+1,lease_expires_at=? WHERE job_id=? AND status='queued'",
                    (self._owner, time.time() + 60, job_id),
                ).rowcount
                self._db.commit()
                if not claimed:
                    return
        self._set(job_id, "running")
        stop_heartbeat = Event()
        heartbeat = Thread(target=self._heartbeat, args=(job_id, stop_heartbeat), daemon=True)
        heartbeat.start()
        try:
            self._service.generate(run_id, plan)
        except Exception as exc:  # surfaced through job polling
            self._set(job_id, "failed", str(exc))
        else:
            self._set(job_id, "completed")
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=1)

    def _heartbeat(self, job_id: str, stop: Event) -> None:
        while not stop.wait(10):
            with self._lock:
                if self._db:
                    self._db.execute(
                        "UPDATE synthetic_jobs SET lease_expires_at=? WHERE job_id=? AND status='running' AND lease_owner=?",
                        (time.time() + 60, job_id, self._owner),
                    )
                    self._db.commit()

    def _set(self, job_id: str, status: str, error: str | None = None) -> None:
        with self._lock:
            current = self._jobs[job_id]
            self._jobs[job_id] = GenerationJob(current.job_id, current.run_id, status, error)
            if self._db:
                self._db.execute(
                    "UPDATE synthetic_jobs SET status=?,error=?,lease_owner=NULL,lease_expires_at=NULL WHERE job_id=?",
                    (status, error, job_id),
                )
                self._db.commit()

    def get(self, job_id: str) -> GenerationJob:
        with self._lock:
            if job_id not in self._jobs and self._db:
                row = self._db.execute(
                    "SELECT run_id,status,error FROM synthetic_jobs WHERE job_id=?", (job_id,)
                ).fetchone()
                if row:
                    self._jobs[job_id] = GenerationJob(job_id, row[0], row[1], row[2])
            try:
                return self._jobs[job_id]
            except KeyError as exc:
                raise KeyError(job_id) from exc

    def cancel(self, job_id: str) -> GenerationJob:
        with self._lock:
            job = self.get(job_id)
            if job.status in {"queued", "running"}:
                future = self._futures.get(job_id)
                if future is not None:
                    future.cancel()
                self._jobs[job_id] = GenerationJob(job.job_id, job.run_id, "cancelled")
                if self._db:
                    self._db.execute(
                        "UPDATE synthetic_jobs SET status='cancelled' WHERE job_id=?", (job_id,)
                    )
                    self._db.commit()
            return self._jobs[job_id]

    def close(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)
        if self._db:
            self._db.close()


__all__ = ["GenerationJob", "LocalGenerationJobs"]
