CREATE TABLE ontologies (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    ontology_id TEXT NOT NULL,
    version TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, ontology_id, version)
) WITHOUT ROWID;

CREATE INDEX idx_ontologies_id ON ontologies(workspace_id, ontology_id, version);
