CREATE TABLE environments (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    environment_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, environment_id)
) WITHOUT ROWID;

CREATE TABLE project_environment_bindings (
    workspace_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    bindings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, project_id, environment_id),
    FOREIGN KEY (workspace_id, project_id)
        REFERENCES workspace_projects(workspace_id, project_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, environment_id)
        REFERENCES environments(workspace_id, environment_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_environments_workspace
    ON environments(workspace_id, environment_id);
CREATE INDEX idx_project_environment_bindings_environment
    ON project_environment_bindings(workspace_id, environment_id, project_id);
