CREATE TABLE catalog_asset_sensitivity (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, asset_id, version),
    FOREIGN KEY (workspace_id, asset_id)
        REFERENCES catalog_assets(workspace_id, asset_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_catalog_asset_sensitivity_latest
    ON catalog_asset_sensitivity(workspace_id, asset_id, version DESC);
