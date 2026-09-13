CREATE TABLE scheduler_backfill_plans (
    workspace_id TEXT NOT NULL,
    backfill_id TEXT NOT NULL,
    schedule_json TEXT NOT NULL,
    workflow_json TEXT NOT NULL,
    cursor_at TEXT,
    max_concurrency INTEGER NOT NULL CHECK (max_concurrency >= 1),
    generation_complete INTEGER NOT NULL DEFAULT 0 CHECK (generation_complete IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, backfill_id),
    FOREIGN KEY (workspace_id, backfill_id)
        REFERENCES scheduler_backfills(workspace_id, backfill_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_scheduler_backfill_plans_generation
    ON scheduler_backfill_plans(workspace_id, generation_complete, updated_at, backfill_id);
