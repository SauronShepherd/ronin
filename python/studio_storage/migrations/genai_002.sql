CREATE TABLE genai_agent_runs (
    workspace_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, run_id)
) WITHOUT ROWID;

CREATE INDEX idx_genai_agent_runs_agent
ON genai_agent_runs(workspace_id, agent_id, run_id);
