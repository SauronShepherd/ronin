CREATE TABLE audit_events (
    workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    audit_event_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor_kind TEXT NOT NULL,
    actor_ref TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_kind TEXT NOT NULL,
    resource_ref TEXT NOT NULL,
    outcome TEXT NOT NULL,
    request_id TEXT,
    digest TEXT NOT NULL,
    event_json TEXT NOT NULL,
    PRIMARY KEY (workspace_id, audit_event_id)
) WITHOUT ROWID;

CREATE INDEX idx_audit_events_time
    ON audit_events(workspace_id, occurred_at, audit_event_id);
CREATE INDEX idx_audit_events_actor
    ON audit_events(workspace_id, actor_kind, actor_ref, occurred_at, audit_event_id);
CREATE INDEX idx_audit_events_resource
    ON audit_events(workspace_id, resource_kind, resource_ref, occurred_at, audit_event_id);
