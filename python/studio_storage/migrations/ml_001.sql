CREATE TABLE ml_experiments (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    experiment_id TEXT NOT NULL,
    experiment_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, experiment_id)
) WITHOUT ROWID;

CREATE TABLE ml_runs (
    workspace_id TEXT NOT NULL,
    ml_run_id TEXT NOT NULL,
    experiment_id TEXT NOT NULL,
    run_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, ml_run_id),
    FOREIGN KEY (workspace_id, experiment_id)
        REFERENCES ml_experiments(workspace_id, experiment_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE TABLE model_versions (
    workspace_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    version TEXT NOT NULL,
    source_ml_run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    model_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, model_id, version),
    FOREIGN KEY (workspace_id, source_ml_run_id)
        REFERENCES ml_runs(workspace_id, ml_run_id)
) WITHOUT ROWID;

CREATE TABLE model_evaluations (
    workspace_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    version TEXT NOT NULL,
    evaluation_digest TEXT NOT NULL,
    evaluation_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, model_id, version, evaluation_digest),
    FOREIGN KEY (workspace_id, model_id, version)
        REFERENCES model_versions(workspace_id, model_id, version) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_ml_runs_experiment ON ml_runs(workspace_id, experiment_id, created_at, ml_run_id);
CREATE INDEX idx_model_versions_stage ON model_versions(workspace_id, model_id, stage, version);
