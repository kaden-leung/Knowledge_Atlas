-- Migration 002 — lifecycle_transitions
-- Audit log: every state change on an article_references row writes one row here.

CREATE TABLE IF NOT EXISTS lifecycle_transitions (
    transition_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_id     TEXT NOT NULL,
    run_id           TEXT NOT NULL,
    from_stage       TEXT,                                                -- nullable on initial insert
    to_stage         TEXT NOT NULL,
    reason           TEXT NOT NULL,                                       -- short token; see SCHEMA_CONTRACT.md §6
    created_by       TEXT NOT NULL,                                       -- writer name; see SCHEMA_CONTRACT.md §7
    at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (reference_id) REFERENCES article_references(reference_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_transitions_ref     ON lifecycle_transitions(reference_id);
CREATE INDEX IF NOT EXISTS idx_transitions_run     ON lifecycle_transitions(run_id);
CREATE INDEX IF NOT EXISTS idx_transitions_writer  ON lifecycle_transitions(created_by);
