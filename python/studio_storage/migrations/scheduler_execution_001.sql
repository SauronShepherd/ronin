CREATE TABLE task_execution_links (
    workspace_id TEXT NOT NULL,
    task_attempt_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, task_attempt_id),
    UNIQUE (job_id),
    FOREIGN KEY (workspace_id, task_attempt_id)
        REFERENCES task_attempts(workspace_id, task_attempt_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_task_execution_links_job
    ON task_execution_links(job_id, workspace_id, task_attempt_id);
