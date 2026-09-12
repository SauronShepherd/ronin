CREATE TABLE data_contracts (
    workspace_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, asset_id, asset_version),
    FOREIGN KEY (workspace_id, asset_id, asset_version)
        REFERENCES catalog_asset_revisions(workspace_id, asset_id, version) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE TABLE quality_runs (
    workspace_id TEXT NOT NULL,
    quality_run_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    asset_version TEXT NOT NULL,
    status TEXT NOT NULL,
    run_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, quality_run_id),
    FOREIGN KEY (workspace_id, asset_id, asset_version)
        REFERENCES catalog_asset_revisions(workspace_id, asset_id, version) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_quality_runs_asset
    ON quality_runs(workspace_id, asset_id, asset_version, created_at, quality_run_id);
CREATE INDEX idx_quality_runs_status
    ON quality_runs(workspace_id, status, created_at, quality_run_id);
