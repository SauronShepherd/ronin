CREATE TABLE workflows (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    workflow_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, workflow_id)
) WITHOUT ROWID;

CREATE TABLE schedules (
    workspace_id TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    schedule_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, schedule_id),
    FOREIGN KEY (workspace_id, workflow_id)
        REFERENCES workflows(workspace_id, workflow_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE TABLE workflow_runs (
    workspace_id TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    trigger_key TEXT NOT NULL,
    state TEXT NOT NULL,
    run_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, workflow_run_id),
    UNIQUE (workspace_id, workflow_id, trigger_key)
) WITHOUT ROWID;

CREATE TABLE task_runs (
    workspace_id TEXT NOT NULL,
    task_run_id TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    state TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, task_run_id),
    UNIQUE (workspace_id, workflow_run_id, node_id),
    FOREIGN KEY (workspace_id, workflow_run_id)
        REFERENCES workflow_runs(workspace_id, workflow_run_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_schedules_workflow ON schedules(workspace_id, workflow_id, schedule_id);
CREATE INDEX idx_workflow_runs_state ON workflow_runs(workspace_id, state, created_at, workflow_run_id);
CREATE INDEX idx_task_runs_state ON task_runs(workspace_id, state, created_at, task_run_id);
