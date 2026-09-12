CREATE TABLE event_triggers (
    workspace_id TEXT NOT NULL,
    event_trigger_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    row_version INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workspace_id, event_trigger_id),
    FOREIGN KEY (workspace_id, workflow_id)
        REFERENCES workflows(workspace_id, workflow_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE TABLE scheduler_events (
    workspace_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source_ref TEXT,
    subject_ref TEXT,
    payload_digest TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, event_id)
) WITHOUT ROWID;

CREATE TABLE scheduler_event_deliveries (
    workspace_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_trigger_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    trigger_snapshot_json TEXT NOT NULL,
    workflow_run_id TEXT,
    state TEXT NOT NULL CHECK (state IN ('pending','delivered')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, event_id, event_trigger_id),
    FOREIGN KEY (workspace_id, event_id)
        REFERENCES scheduler_events(workspace_id, event_id) ON DELETE CASCADE,
    FOREIGN KEY (workspace_id, workflow_id)
        REFERENCES workflows(workspace_id, workflow_id) ON DELETE CASCADE
) WITHOUT ROWID;

CREATE INDEX idx_event_triggers_match
    ON event_triggers(workspace_id, workflow_id, event_trigger_id);
CREATE INDEX idx_scheduler_event_deliveries_pending
    ON scheduler_event_deliveries(workspace_id, state, created_at, event_id, event_trigger_id);
