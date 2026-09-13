CREATE TABLE scheduler_leader_lease (
    scope TEXT PRIMARY KEY CHECK (scope = 'scheduler'),
    owner TEXT NOT NULL,
    lease_token TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    acquired_at TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
) WITHOUT ROWID;
