CREATE TABLE scheduler_backfills (
    workspace_id TEXT NOT NULL,
    backfill_id TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending','running','completed','cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, backfill_id),
    FOREIGN KEY (workspace_id, schedule_id)
        REFERENCES schedules(workspace_id, schedule_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE TABLE scheduler_backfill_runs (
    workspace_id TEXT NOT NULL,
    backfill_id TEXT NOT NULL,
    logical_time TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, backfill_id, logical_time),
    UNIQUE (workspace_id, workflow_run_id),
    FOREIGN KEY (workspace_id, backfill_id)
        REFERENCES scheduler_backfills(workspace_id, backfill_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, workflow_run_id)
        REFERENCES workflow_runs(workspace_id, workflow_run_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_scheduler_backfills_state
    ON scheduler_backfills(workspace_id, state, created_at, backfill_id);
