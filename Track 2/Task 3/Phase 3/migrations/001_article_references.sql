-- Migration 001 — article_references
-- The candidate buffer between harvesters and the triage funnel.
-- Every search hit and every PDF-extracted reference lives here as one row.

CREATE TABLE IF NOT EXISTS article_references (
    -- Identity
    reference_id              TEXT PRIMARY KEY,           -- REF-YYYY-MM-DD-NNNNNN
    doi                       TEXT,                        -- normalised, lowercased, no URL prefix; nullable
    title_raw                 TEXT NOT NULL,
    title_normalized          TEXT NOT NULL,
    first_author_surname      TEXT,
    publication_year          INTEGER,
    venue                     TEXT,

    -- Raw evidence
    raw_citation              TEXT,                        -- messy reference-list line (PDF harvester)
    snippet                   TEXT,                        -- SerpAPI snippet or abstract fragment

    -- Provenance
    discovered_via            TEXT NOT NULL,               -- comma-joined list of enum values; see SCHEMA_CONTRACT.md
    discovered_from_paper_id  TEXT,                        -- soft FK to papers (filename-derived ID); not enforced
    discovered_query          TEXT,                        -- the boolean query, if from search
    discovery_run_id          TEXT NOT NULL,
    discovered_at             TEXT NOT NULL,               -- ISO 8601 UTC, format "%Y-%m-%dT%H:%M:%SZ"

    -- Triage state (Phase 4 fills these in)
    triage_stage              TEXT NOT NULL DEFAULT 'metadata_only',
    triage_decision           TEXT,                        -- ACCEPT / EDGE_CASE / REJECT / MISSING_ABSTRACT / DUPLICATE
    triage_reason             TEXT,
    abstract_text             TEXT,
    abstract_source           TEXT,                        -- semantic_scholar / crossref / pubmed / openalex
    classifier_confidence     REAL,

    -- VOI passthrough from Task 2
    voi_score                 REAL,

    -- Acquisition state (Phase 5 fills these in)
    pdf_acquisition_attempts    INTEGER NOT NULL DEFAULT 0,
    pdf_acquisition_last_source TEXT,                       -- unpaywall / openalex_oa / scidownl
    acquired_paper_id           TEXT,                       -- soft FK to papers; not enforced

    -- Audit timestamps
    created_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- DOI uniqueness for non-null DOI only (SQLite partial unique index).
-- This is the SINGLE source of DOI uniqueness; no inline UNIQUE constraint.
CREATE UNIQUE INDEX IF NOT EXISTS idx_article_references_doi
    ON article_references(doi) WHERE doi IS NOT NULL AND doi != '';

CREATE INDEX IF NOT EXISTS idx_article_references_run
    ON article_references(discovery_run_id);
CREATE INDEX IF NOT EXISTS idx_article_references_stage
    ON article_references(triage_stage);
CREATE INDEX IF NOT EXISTS idx_article_references_decision
    ON article_references(triage_decision);
CREATE INDEX IF NOT EXISTS idx_article_references_title_norm
    ON article_references(title_normalized);
