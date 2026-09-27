CREATE TABLE catalog_namespace_bindings (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL,
    identifier TEXT NOT NULL,
    namespace_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, provider_id, identifier)
) WITHOUT ROWID;

CREATE INDEX idx_catalog_namespace_provider
    ON catalog_namespace_bindings(workspace_id, provider_id, identifier);
