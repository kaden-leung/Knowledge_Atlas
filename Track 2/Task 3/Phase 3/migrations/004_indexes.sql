-- Migration 004 — Phase-6 dashboard hot-path index
-- Kept separate so it can be added/removed without touching the core schema.
-- The PRISMA dashboard's central query is:
--   SELECT discovery_run_id, triage_stage, triage_decision, COUNT(*)
--   FROM article_references
--   GROUP BY discovery_run_id, triage_stage, triage_decision;
-- This composite index lets that GROUP BY scan only the index, never the table.

CREATE INDEX IF NOT EXISTS idx_article_references_funnel
    ON article_references(discovery_run_id, triage_stage, triage_decision);
