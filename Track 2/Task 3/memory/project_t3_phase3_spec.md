---
name: t3-phase3-course-spec
description: Course-issued spec for Task 3 Phase 3 — article_references table requirements, dedupe-on-insert protocol, harvester sources, grader's actual check
metadata:
  type: project
---

# Task 3 Phase 3 — Course Spec (verbatim from instructor)

## Grader's actual check
> "Every harvested candidate must be inserted (or deduplicated against an existing row) before any later phase touches it. Your grader checks for this. **Free-floating outputs do not count.**"

A reference list extracted into a JSON file that never lands in `article_references` is invisible to the rest of the pipeline. **The DB row is the deliverable, not `search_results.json`.**

## 3A — Required `article_references` columns on insert

**Identity:** `reference_id` (format `REF-YYYY-MM-DD-NNNNNN`), `doi` (normalised, lowercased, no URL prefix), `title_raw`, `title_normalized`, `first_author_surname`, `publication_year`, `venue`

**Provenance:** `discovered_via` (enum below), `discovered_from_paper_id` (FK to papers, when harvested out of an existing PDF), `discovered_query`, `discovery_run_id`

**Triage state (initial, on insert):** `triage_stage = 'metadata_only'`, `discovered_at = ISO 8601 timestamp`

**Raw evidence:** `raw_citation` (the messy reference-list line as captured), `snippet` (search snippet or abstract fragment)

### `discovered_via` enum (course-locked)

- `review_pdf_extract`
- `serpapi_scholar`
- `scholarly_search`
- `paperscraper_search`
- `openalex_expansion`
- `crossref_search`
- `student_upload`

Phase 3 only emits three of these (`serpapi_scholar`, `scholarly_search`, `paperscraper_search`, `review_pdf_extract`); DDL must accept the full enum.

## 3B — Dedupe-on-insert (do this before every INSERT)

1. Normalise the candidate's DOI with `normalize_doi()` from `build_neuro_review_acquisition_queue.py`.
2. If a row exists with the same `doi`: **do not insert**. UPDATE `discovered_via = discovered_via || ', ' || NEW.discovered_via` to preserve multi-channel provenance.
3. If no DOI but a fuzzy-matched `title_normalized` already exists in `pdf_identity_inventory` above the existing-corpus threshold: **INSERT** with `triage_stage = 'duplicate'` immediately (counts toward identified, removed at dedupe stage in PRISMA).

## 3C — Two harvesters, one table

Both writers go through the same dedupe path:
1. **Four-scraper search runner** (Phase 2 already built)
2. **Review-PDF reference harvester** — instructor says "largely already written for you":
   - `scripts/coordination/extract_neuro_key_review_references.py` — pdfplumber-based reference extraction
   - `scripts/coordination/build_neuro_review_acquisition_queue.py` — canonical `normalize_doi` + corpus dedupe filter

## Prototyping corpus referenced by instructor

- `/Users/davidusa/REPOS/_Collecting Articles/Neuro key articles/_atlas_inventory/latest_neuro_review_reference_harvest.json` — 46 review PDFs, `{doi: cite_count}` dict.

## Authoritative DDL reference

- `scripts/coordination/lifecycle/schema.sql` (per AF pipeline recon doc §3)

## Tensions with local machine state (must resolve before building)

1. **Course says `pipeline_lifecycle_full.db`; plan locked local DB.** The shared DB at `Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db` is 0 bytes on this machine. Plan §2 chose `Track 2/Task 3/task3_pipeline_lifecycle.db` for push-safety. **Open question for grader.**
2. **Course says "use the existing AE scripts."** None of `extract_neuro_key_review_references.py`, `build_neuro_review_acquisition_queue.py`, `lifecycle/schema.sql` exist on this machine. Plan §3 already addresses this — we build our own equivalents.
3. **Course says use the 46-PDF prototyping corpus.** That path is `/Users/davidusa/...` — not on this machine. Plan §3 substitutes `Part 2 Pdfs/` (5) + `Part_One_10pdfs/` (10) = 15 local PDFs.

These are documented limitations to surface in MANIFEST.md, not blockers.
