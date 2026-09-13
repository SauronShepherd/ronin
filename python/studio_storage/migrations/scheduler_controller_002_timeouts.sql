CREATE TABLE task_timeout_requests (
    workspace_id TEXT NOT NULL,
    task_attempt_id TEXT NOT NULL,
    job_id TEXT,
    requested_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, task_attempt_id),
    FOREIGN KEY (workspace_id, task_attempt_id)
        REFERENCES task_attempts(workspace_id, task_attempt_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_task_timeout_requests_job
    ON task_timeout_requests(job_id, workspace_id, task_attempt_id);
