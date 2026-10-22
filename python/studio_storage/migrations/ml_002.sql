CREATE TABLE model_deployments (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    deployment_id TEXT NOT NULL,
    deployment_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, deployment_id)
) WITHOUT ROWID;
