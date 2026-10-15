ALTER TABLE workspace_projects ADD COLUMN archived_at TEXT;
CREATE INDEX idx_workspace_projects_active
    ON workspace_projects(workspace_id, project_id)
    WHERE archived_at IS NULL;
