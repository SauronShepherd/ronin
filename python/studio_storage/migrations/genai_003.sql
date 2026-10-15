CREATE TABLE genai_rag_evaluations (
    workspace_id TEXT NOT NULL,
    evaluation_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, evaluation_id)
) WITHOUT ROWID;
