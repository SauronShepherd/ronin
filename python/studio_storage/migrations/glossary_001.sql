CREATE TABLE glossary_terms (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    term_id TEXT NOT NULL, version TEXT NOT NULL, term_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, term_id, version)
) WITHOUT ROWID;
CREATE INDEX idx_glossary_terms_name ON glossary_terms(workspace_id, term_id, version);
