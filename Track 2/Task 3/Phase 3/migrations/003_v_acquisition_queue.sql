-- Migration 003 — v_acquisition_queue
-- The Phase 5 read path: rows that have been triaged ACCEPT and don't yet
-- have an acquired PDF, in VOI-priority order.

CREATE VIEW IF NOT EXISTS v_acquisition_queue AS
SELECT
    reference_id,
    doi,
    title_raw,
    voi_score,
    pdf_acquisition_attempts,
    pdf_acquisition_last_source,
    discovery_run_id
FROM article_references
WHERE triage_decision = 'ACCEPT'
  AND acquired_paper_id IS NULL
ORDER BY voi_score DESC NULLS LAST, created_at ASC;
