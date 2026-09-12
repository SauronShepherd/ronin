CREATE TABLE workspaces (
    workspace_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE workspace_projects (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    project_id TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, project_id)
) WITHOUT ROWID;

CREATE INDEX idx_workspaces_name ON workspaces(name, workspace_id);
CREATE INDEX idx_workspace_projects_project ON workspace_projects(project_id, workspace_id);
