ALTER TABLE task_runs ADD COLUMN next_eligible_at TEXT;

CREATE TABLE task_attempts (
    workspace_id TEXT NOT NULL,
    task_attempt_id TEXT NOT NULL,
    task_run_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    state TEXT NOT NULL,
    lease_owner TEXT NOT NULL,
    lease_token TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, task_attempt_id),
    UNIQUE (workspace_id, task_run_id, ordinal),
    FOREIGN KEY (workspace_id, task_run_id)
        REFERENCES task_runs(workspace_id, task_run_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_task_attempts_active
    ON task_attempts(workspace_id, state, lease_expires_at, task_attempt_id);
CREATE INDEX idx_task_attempts_task
    ON task_attempts(workspace_id, task_run_id, ordinal);
