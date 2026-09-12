CREATE TABLE task_execution_intents (
    workspace_id TEXT NOT NULL,
    task_attempt_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    target TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    not_before TEXT NOT NULL,
    PRIMARY KEY (workspace_id, task_attempt_id),
    UNIQUE (job_id),
    FOREIGN KEY (workspace_id, task_attempt_id)
        REFERENCES task_execution_links(workspace_id, task_attempt_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_task_execution_intents_job
    ON task_execution_intents(job_id, workspace_id, task_attempt_id);
