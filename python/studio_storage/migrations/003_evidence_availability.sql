ALTER TABLE evidence_refs RENAME TO evidence_refs_v2;

CREATE TABLE evidence_refs (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    cell_id TEXT,
    role TEXT NOT NULL,
    digest_algorithm TEXT,
    digest TEXT,
    media_type TEXT,
    size_bytes INTEGER,
    storage_ref TEXT,
    availability TEXT NOT NULL DEFAULT 'available',
    unavailable_reason TEXT,
    CHECK (availability IN ('available', 'missing', 'tombstoned', 'unavailable')),
    CHECK (
        (availability = 'unavailable'
            AND digest_algorithm IS NULL
            AND digest IS NULL
            AND size_bytes IS NULL
            AND storage_ref IS NULL
            AND unavailable_reason IS NOT NULL)
        OR
        (availability <> 'unavailable'
            AND digest_algorithm IS NOT NULL
            AND digest IS NOT NULL
            AND size_bytes IS NOT NULL
            AND unavailable_reason IS NULL)
    )
);

INSERT INTO evidence_refs(
    run_id,
    cell_id,
    role,
    digest_algorithm,
    digest,
    media_type,
    size_bytes,
    storage_ref,
    availability,
    unavailable_reason
)
SELECT
    run_id,
    cell_id,
    role,
    digest_algorithm,
    digest,
    media_type,
    size_bytes,
    storage_ref,
    'available',
    NULL
FROM evidence_refs_v2;

DROP TABLE evidence_refs_v2;

CREATE UNIQUE INDEX idx_evidence_refs_identity
ON evidence_refs(run_id, IFNULL(cell_id, ''), role, digest_algorithm, digest)
WHERE digest IS NOT NULL;

CREATE UNIQUE INDEX idx_evidence_refs_unavailable
ON evidence_refs(run_id, IFNULL(cell_id, ''), role, unavailable_reason)
WHERE availability = 'unavailable';
