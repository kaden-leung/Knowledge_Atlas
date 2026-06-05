-- Migration 005 — model_version, pipeline_version, voi_breakdown
-- Adds versioning columns to article_references and lifecycle_transitions.
-- All columns are nullable so existing rows are unaffected.
-- Note: ALTER TABLE ADD COLUMN without IF NOT EXISTS; the migration runner
-- handles the "duplicate column" OperationalError gracefully.

ALTER TABLE article_references ADD COLUMN model_version TEXT;
ALTER TABLE article_references ADD COLUMN voi_breakdown TEXT;
ALTER TABLE lifecycle_transitions ADD COLUMN pipeline_version TEXT;
