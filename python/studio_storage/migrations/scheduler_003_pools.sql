ALTER TABLE task_attempts ADD COLUMN pool_name TEXT;

CREATE TABLE scheduler_resource_pools (
    workspace_id TEXT NOT NULL,
    pool_name TEXT NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, pool_name),
    FOREIGN KEY (workspace_id)
        REFERENCES workspaces(workspace_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_task_attempts_pool_active
    ON task_attempts(workspace_id, pool_name, state, lease_expires_at);
