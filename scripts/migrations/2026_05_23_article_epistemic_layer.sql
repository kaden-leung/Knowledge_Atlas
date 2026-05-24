-- ============================================================================
-- Article detail epistemic layer schema (Stage 1)
-- Date: 2026-05-23
-- Target: Knowledge Atlas lifecycle database, SQLite 3.x
--
-- Source authorities:
--   docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md   (controlling)
--   docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_SYNTHESIS_2026-05-23.md
--   docs/HANDOFF_EPISTEMIC_LAYER_IMPLEMENTATION_2026-05-23.md
--
-- Identity model (spec §3):
--   * record_id is the LOGICAL identity:
--       record_id = 'article_epistemic_layer.v1:' || paper_id
--   * Each rebuild produces a NEW physical row sharing the same record_id but
--     distinguished by build_run_id. Row identity is therefore
--     (record_id, build_run_id).
--   * At most one row may carry active=1 for any (paper_id, schema_version),
--     enforced by a partial unique index. Historical versions remain visible
--     via active=0 rows.
--
-- Safety:
--   * Additive only. No existing table is altered or dropped.
--   * Idempotent: every CREATE uses IF NOT EXISTS.
--   * Status vocabularies enforced via CHECK constraints (spec §4).
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------------------
-- 1. article_epistemic_support_sets
--    Defined first because components reference it.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_epistemic_support_sets (
  support_set_id    TEXT PRIMARY KEY,
  support_set_hash  TEXT NOT NULL,
  members_json      TEXT NOT NULL,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS ix_aess_hash
  ON article_epistemic_support_sets(support_set_hash);

-- ----------------------------------------------------------------------------
-- 2. article_epistemic_build_runs
--    Defined before records so records' build_run_id FK target exists.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_epistemic_build_runs (
  build_run_id         TEXT PRIMARY KEY,
  builder_version      TEXT NOT NULL,
  started_at           TEXT NOT NULL,
  finished_at          TEXT,
  input_snapshot_hash  TEXT,
  record_count         INTEGER NOT NULL DEFAULT 0,
  success_count        INTEGER NOT NULL DEFAULT 0,
  failure_count        INTEGER NOT NULL DEFAULT 0,
  repair_count         INTEGER NOT NULL DEFAULT 0,
  status               TEXT NOT NULL CHECK (status IN (
    'running', 'completed', 'failed', 'aborted'
  )),
  report_json          TEXT NOT NULL DEFAULT '{}'
);

-- ----------------------------------------------------------------------------
-- 3. article_epistemic_records
--    Composite PK (record_id, build_run_id). active=1 marks the current row.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_epistemic_records (
  record_id              TEXT NOT NULL,
  build_run_id           TEXT NOT NULL REFERENCES article_epistemic_build_runs(build_run_id),
  paper_id               TEXT NOT NULL,
  schema_version         TEXT NOT NULL,
  active                 INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
  extraction_status      TEXT NOT NULL CHECK (extraction_status IN (
    'absent', 'minimal', 'partial', 'complete', 'failed'
  )),
  enrichment_status      TEXT NOT NULL CHECK (enrichment_status IN (
    'none', 'deferred', 'draft', 'machine_checked', 'human_approved', 'rejected'
  )),
  freshness_status       TEXT NOT NULL CHECK (freshness_status IN (
    'fresh', 'stale', 'unknown'
  )),
  review_status          TEXT NOT NULL CHECK (review_status IN (
    'not_required', 'unreviewed', 'machine_verified',
    'human_review_required', 'human_approved', 'human_rejected'
  )),
  render_status          TEXT NOT NULL CHECK (render_status IN (
    'renderable', 'show_with_warning', 'hidden', 'block_article'
  )),
  release_eligible       INTEGER NOT NULL DEFAULT 0 CHECK (release_eligible IN (0, 1)),
  primary_claim_id       TEXT,
  input_fingerprint      TEXT NOT NULL,
  payload_hash           TEXT NOT NULL,
  blocking_failures_json TEXT NOT NULL DEFAULT '[]',
  created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  PRIMARY KEY (record_id, build_run_id)
);

CREATE INDEX IF NOT EXISTS ix_aer_paper_schema
  ON article_epistemic_records(paper_id, schema_version);

CREATE INDEX IF NOT EXISTS ix_aer_build_run
  ON article_epistemic_records(build_run_id);

-- Enforce: at most one active row per (paper_id, schema_version) (spec §3).
CREATE UNIQUE INDEX IF NOT EXISTS uq_aer_active_per_paper_schema
  ON article_epistemic_records(paper_id, schema_version)
  WHERE active = 1;

-- ----------------------------------------------------------------------------
-- 4. article_epistemic_components
--    Composite PK (component_id, build_run_id), composite FK to records.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_epistemic_components (
  component_id           TEXT NOT NULL,
  build_run_id           TEXT NOT NULL REFERENCES article_epistemic_build_runs(build_run_id),
  record_id              TEXT NOT NULL,
  paper_id               TEXT NOT NULL,
  component_type         TEXT NOT NULL CHECK (component_type IN (
    'primary_claim', 'claim_rows', 'evidence_strength', 'defeaters',
    'belief_network_context', 'answer_shape_status', 'provenance_summary'
  )),
  component_status       TEXT NOT NULL CHECK (component_status IN (
    'present', 'not_extracted', 'not_applicable', 'source_missing',
    'extraction_failed', 'stale', 'blocked', 'queued', 'withheld_low_confidence'
  )),
  source_mode            TEXT NOT NULL CHECK (source_mode IN (
    'extracted', 'deterministic_derived', 'llm_generated',
    'human_entered', 'missing'
  )),
  field_policy           TEXT NOT NULL CHECK (field_policy IN (
    'extracted_only', 'deterministic_only', 'llm_enrichable', 'human_only'
  )),
  review_status          TEXT NOT NULL CHECK (review_status IN (
    'not_required', 'unreviewed', 'machine_verified',
    'human_review_required', 'human_approved', 'human_rejected'
  )),
  freshness_status       TEXT NOT NULL CHECK (freshness_status IN (
    'fresh', 'stale', 'unknown'
  )),
  render_policy          TEXT NOT NULL CHECK (render_policy IN (
    'render', 'render_with_warning', 'hide', 'block'
  )),
  content_json           TEXT NOT NULL DEFAULT '{}',
  content_hash           TEXT NOT NULL,
  support_set_id         TEXT NOT NULL REFERENCES article_epistemic_support_sets(support_set_id),
  provenance_json        TEXT NOT NULL DEFAULT '{}',
  verification_json      TEXT NOT NULL DEFAULT '{}',
  created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  PRIMARY KEY (component_id, build_run_id),
  FOREIGN KEY (record_id, build_run_id)
    REFERENCES article_epistemic_records(record_id, build_run_id)
);

CREATE INDEX IF NOT EXISTS ix_aec_record_build
  ON article_epistemic_components(record_id, build_run_id);

CREATE INDEX IF NOT EXISTS ix_aec_paper_type
  ON article_epistemic_components(paper_id, component_type);

CREATE INDEX IF NOT EXISTS ix_aec_support_set
  ON article_epistemic_components(support_set_id);

-- Exactly one component per (record_id, build_run_id, component_type).
-- Stage 1 emits seven components per record; list-valued components carry
-- multiple items inside content_json rather than across rows.
CREATE UNIQUE INDEX IF NOT EXISTS uq_aec_record_build_type
  ON article_epistemic_components(record_id, build_run_id, component_type);

-- ----------------------------------------------------------------------------
-- 5. article_epistemic_completion_queue
--    Open repair / completion items. severity drives release-gate blocking.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_epistemic_completion_queue (
  queue_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  paper_id        TEXT NOT NULL,
  component_type  TEXT NOT NULL,
  reason          TEXT NOT NULL,
  severity        TEXT NOT NULL CHECK (severity IN (
    'info', 'warning', 'blocking'
  )),
  first_seen_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  last_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  attempt_count   INTEGER NOT NULL DEFAULT 0,
  next_action     TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN (
    'open', 'in_progress', 'resolved', 'waived', 'dismissed'
  )),
  assigned_to     TEXT,
  resolved_at     TEXT
);

CREATE INDEX IF NOT EXISTS ix_aecq_paper_component
  ON article_epistemic_completion_queue(paper_id, component_type);

CREATE INDEX IF NOT EXISTS ix_aecq_status
  ON article_epistemic_completion_queue(status);

-- Identity for an open repair item: at most one open row per
-- (paper_id, component_type, reason). On re-detection the builder/verifier
-- UPDATEs last_seen_at and attempt_count rather than inserting a duplicate.
CREATE UNIQUE INDEX IF NOT EXISTS uq_aecq_open_identity
  ON article_epistemic_completion_queue(paper_id, component_type, reason)
  WHERE status IN ('open', 'in_progress');

-- ----------------------------------------------------------------------------
-- 6. article_epistemic_verification_events
--    Strict-verifier outcomes per record per build run.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_epistemic_verification_events (
  event_id              INTEGER PRIMARY KEY AUTOINCREMENT,
  -- record_id is NULL for run-scoped (global) verification events such as
  -- forbidden-import or orphaned-row checks that aren't tied to one record.
  -- The composite FK below is satisfied automatically when record_id IS NULL
  -- under SQLite MATCH SIMPLE semantics.
  record_id             TEXT,
  build_run_id          TEXT NOT NULL REFERENCES article_epistemic_build_runs(build_run_id),
  verifier_name         TEXT NOT NULL,
  verifier_version      TEXT NOT NULL,
  status                TEXT NOT NULL CHECK (status IN (
    'pass', 'warn', 'fail'
  )),
  failures_json         TEXT NOT NULL DEFAULT '[]',
  repair_actions_json   TEXT NOT NULL DEFAULT '[]',
  created_at            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  FOREIGN KEY (record_id, build_run_id)
    REFERENCES article_epistemic_records(record_id, build_run_id)
);

CREATE INDEX IF NOT EXISTS ix_aeve_record_build
  ON article_epistemic_verification_events(record_id, build_run_id);

CREATE INDEX IF NOT EXISTS ix_aeve_build_run
  ON article_epistemic_verification_events(build_run_id);
