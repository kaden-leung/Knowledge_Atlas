-- ============================================================================
-- Dependency overseer observability layer (post-panel pause)
-- Date: 2026-05-24
-- Target: Knowledge Atlas lifecycle database, SQLite 3.x
--
-- Source authorities:
--   docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md §5
--   docs/DEPENDENCY_OVERSEER_POST_PANEL_PAUSE_PLAN_2026-05-24.md §3
--   docs/DEPENDENCY_OVERSEER_RUTHLESS_PANEL_REVIEW_2026-05-24.md §7 (Majors)
--
-- Two new tables, both additive. Records every verifier run and every
-- reconciler-event-per-paper so the monitoring pages can ask high-cardinality
-- questions (time-series, action-distribution, drift detection) without
-- shipping new code per question.
--
-- Safety: idempotent (CREATE TABLE IF NOT EXISTS); no existing table altered.
-- ============================================================================

PRAGMA foreign_keys = ON;

BEGIN;

-- verifier_run_history: one row per verify_strict() invocation.
-- checks_json carries the full per-check report (name, passed, failures, description)
-- so the dashboard can reconstruct the entire run history without re-running.
CREATE TABLE IF NOT EXISTS verifier_run_history (
    run_id          TEXT    PRIMARY KEY,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT    NOT NULL,
    overall_passed  INTEGER NOT NULL CHECK (overall_passed IN (0, 1)),
    db_path         TEXT    NOT NULL,
    checks_json     TEXT    NOT NULL,
    triggered_by    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_verifier_run_history_time
    ON verifier_run_history(started_at);

CREATE INDEX IF NOT EXISTS idx_verifier_run_history_failed
    ON verifier_run_history(overall_passed, started_at)
    WHERE overall_passed = 0;


-- reconciler_event_log: one row per (AF paper, tick) pair.
-- tick_run_id groups all events from one tick together for cardinal queries
-- like "in tick X, how many papers had action=Y broken down by af_status?"
CREATE TABLE IF NOT EXISTS reconciler_event_log (
    event_id          TEXT NOT NULL PRIMARY KEY,
    tick_run_id       TEXT NOT NULL,
    occurred_at       TEXT NOT NULL,
    af_paper_id       TEXT NOT NULL,
    af_signature      TEXT NOT NULL,
    af_status         TEXT,
    ka_paper_id       TEXT NOT NULL,
    action            TEXT NOT NULL CHECK (action IN (
        'inserted_pending',
        'upgraded_to_matched',
        'flagged_unresolved',
        'skipped_already_matched',
        'noop'
    )),
    sync_event_id     TEXT,
    reason            TEXT
);

CREATE INDEX IF NOT EXISTS idx_reconciler_event_log_time
    ON reconciler_event_log(occurred_at);

CREATE INDEX IF NOT EXISTS idx_reconciler_event_log_action
    ON reconciler_event_log(action, occurred_at);

CREATE INDEX IF NOT EXISTS idx_reconciler_event_log_paper
    ON reconciler_event_log(ka_paper_id);

CREATE INDEX IF NOT EXISTS idx_reconciler_event_log_tick
    ON reconciler_event_log(tick_run_id);

COMMIT;
