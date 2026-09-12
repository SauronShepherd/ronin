CREATE TABLE workflow_deployments (
    workspace_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    environment_id TEXT,
    binding_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, workflow_id),
    FOREIGN KEY (workspace_id, workflow_id)
        REFERENCES workflows(workspace_id, workflow_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, project_id)
        REFERENCES workspace_projects(workspace_id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, environment_id)
        REFERENCES environments(workspace_id, environment_id) ON DELETE RESTRICT
) WITHOUT ROWID;

CREATE INDEX idx_workflow_deployments_project
    ON workflow_deployments(workspace_id, project_id, workflow_id);
CREATE INDEX idx_workflow_deployments_environment
    ON workflow_deployments(workspace_id, environment_id, workflow_id);
