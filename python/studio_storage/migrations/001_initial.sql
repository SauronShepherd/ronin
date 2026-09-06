CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    UNIQUE(project_id, idempotency_key)
);

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    state TEXT NOT NULL,
    not_before TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    UNIQUE(job_id, ordinal)
);

CREATE TABLE attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    state TEXT NOT NULL,
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    UNIQUE(run_id, ordinal)
);

CREATE TABLE attempt_events (
    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (attempt_id, sequence)
) WITHOUT ROWID;

CREATE TABLE cell_results (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    cell_id TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    execution_identity_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    result_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, cell_id)
) WITHOUT ROWID;

CREATE TABLE evidence_refs (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    cell_id TEXT,
    role TEXT NOT NULL,
    digest_algorithm TEXT NOT NULL,
    digest TEXT NOT NULL,
    media_type TEXT,
    size_bytes INTEGER,
    storage_ref TEXT,
    PRIMARY KEY (run_id, role, digest_algorithm, digest)
) WITHOUT ROWID;

CREATE INDEX idx_runs_claimable ON runs(state, not_before, run_id);
CREATE INDEX idx_attempts_expiry ON attempts(state, lease_expires_at);
CREATE INDEX idx_runs_job ON runs(job_id, ordinal);
CREATE INDEX idx_attempts_run ON attempts(run_id, ordinal);
