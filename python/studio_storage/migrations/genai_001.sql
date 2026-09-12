CREATE TABLE genai_providers (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL,
    provider_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, provider_id)
) WITHOUT ROWID;

CREATE TABLE prompt_versions (
    workspace_id TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    version TEXT NOT NULL,
    prompt_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, prompt_id, version)
) WITHOUT ROWID;

CREATE TABLE vector_indexes (
    workspace_id TEXT NOT NULL,
    vector_index_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, vector_index_id)
) WITHOUT ROWID;

CREATE TABLE genai_tools (
    workspace_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, tool_id)
) WITHOUT ROWID;

CREATE TABLE genai_agents (
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, agent_id)
) WITHOUT ROWID;
