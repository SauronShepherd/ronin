CREATE TABLE schedule_cursors (
    workspace_id TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    last_evaluated_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, schedule_id),
    FOREIGN KEY (workspace_id, schedule_id)
        REFERENCES schedules(workspace_id, schedule_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE TABLE schedule_fires (
    workspace_id TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, schedule_id, scheduled_for),
    FOREIGN KEY (workspace_id, schedule_id)
        REFERENCES schedules(workspace_id, schedule_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, workflow_run_id)
        REFERENCES workflow_runs(workspace_id, workflow_run_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_schedule_fires_run
    ON schedule_fires(workspace_id, workflow_run_id, schedule_id);
