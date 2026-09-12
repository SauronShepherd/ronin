CREATE TABLE catalog_assets (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, asset_id)
) WITHOUT ROWID;

CREATE TABLE catalog_asset_revisions (
    workspace_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    version TEXT NOT NULL,
    revision_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, asset_id, version),
    FOREIGN KEY (workspace_id, asset_id)
        REFERENCES catalog_assets(workspace_id, asset_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE TABLE lineage_edges (
    workspace_id TEXT NOT NULL,
    edge_digest TEXT NOT NULL,
    source_asset_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    target_asset_id TEXT NOT NULL,
    target_version TEXT NOT NULL,
    edge_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, edge_digest)
) WITHOUT ROWID;

CREATE INDEX idx_catalog_assets_kind ON catalog_assets(workspace_id, kind, asset_id);
CREATE INDEX idx_catalog_assets_name ON catalog_assets(workspace_id, name, asset_id);
CREATE INDEX idx_lineage_source ON lineage_edges(workspace_id, source_asset_id, source_version);
CREATE INDEX idx_lineage_target ON lineage_edges(workspace_id, target_asset_id, target_version);
