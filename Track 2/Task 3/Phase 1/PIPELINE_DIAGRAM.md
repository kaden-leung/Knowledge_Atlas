# Track 2 · Task 3 · Phase 1: Pipeline Diagram & Architecture

**Author:** Kaden Leung
**Date:** 2026-05-26 (v1.1 — added codebase file map, run-id concept, full lifecycle column list, harder priority-gap justification)

---

## Pipeline Overview

The Task 3 pipeline is a four-stage, evidence-gate funnel: harvest → candidate buffer → triage → acquire.
The cardinal rule is enforced by the funnel state machine: **never download a PDF to decide whether you want the paper**. Stage transitions are atomic — every change to `triage_stage` writes a row to `lifecycle_transitions` with the run_id, timestamp, from-state, to-state, and reason. The PRISMA dashboard is reconstructable from a single SQL `GROUP BY` over `article_references` joined to its run.

---

## Boxology Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     TASK 2 OUTPUTS (inputs here)                    │
│  gap_results.json (554 gaps, ranked by VOI)                         │
│  query_results.json (10 gap × 2 query pairs)                        │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ boolean_query (10 queries)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    HARVEST LAYER (Phase 2)                          │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐  │
│  │  SerpAPI     │  │  scholarly   │  │  paper-scraper          │  │
│  │  (primary)   │  │  (free GS    │  │  (arXiv, bioRxiv,       │  │
│  │  250/mo cap  │  │   fallback)  │  │   medRxiv, chemRxiv)    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬──────────────┘  │
│         │                 │                      │                  │
│         └─────────────────┴──────────────────────┘                 │
│                           │                                         │
│              discovered_via tag set per source                      │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ title + snippet + DOI (when available)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 CANDIDATE BUFFER (Phase 3)                          │
│              article_references  (SQLite table)                     │
│                                                                     │
│  Every harvested paper gets ONE row on insert:                      │
│    triage_stage = 'metadata_only'                                   │
│  Dedup on insert:                                                   │
│    DOI match  → UPDATE discovered_via, skip re-insert              │
│    Title fuzzy match in pdf_identity_inventory → triage_stage='dup' │
│                                                                     │
│  Duplicate counter feeds PRISMA "Duplicates removed" slot           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
           ┌────────────────▼────────────────┐
           │  STAGE 1: Metadata-only screen  │   ← Phase 4A
           │  atlas_shared classifier        │
           │  title + venue only, no API call│
           │  conf < 0.20 → REJECT           │
           │  triage_stage = 'rejected_at_   │
           │                  metadata'      │
           └────────────────┬────────────────┘
                            │ Stage-1 survivors (~50–70% of candidates)
           ┌────────────────▼────────────────┐
           │  STAGE 2A: Abstract collection  │   ← Phase 4B
           │  Fallback chain (in order):     │
           │   1. Semantic Scholar (DOI/title)│
           │   2. CrossRef (DOI)             │
           │   3. PubMed (title search)      │
           │   4. OpenAlex (DOI)             │
           │   ─ all fail → MISSING_ABSTRACT │
           │  abstract_source recorded       │
           └────────────────┬────────────────┘
                            │ abstracts collected
           ┌────────────────▼────────────────┐
           │  STAGE 2B: Triage decision      │   ← Phase 4C/4D
           │  atlas_shared classifier        │
           │    (abstract text, not title)   │
           │  + score_voi() on findings      │
           │                                 │
           │  ACCEPT       on-topic + VOI≥0.5│
           │  EDGE_CASE    on-topic + VOI<0.5│
           │               OR borderline     │
           │  REJECT       off-topic         │
           │  MISSING_ABS  no abstract found │
           │                                 │
           │  triage_reason set on every row │
           └────────────────┬────────────────┘
                            │ ACCEPT only
           ┌────────────────▼────────────────┐
           │  STAGE 3: PDF acquisition       │   ← Phase 5
           │  (reads from v_acquisition_queue│
           │   = ACCEPT rows, no PDF yet)    │
           │                                 │
           │  Cascade (in order):            │
           │   1. Unpaywall (always first)   │
           │   2. OpenAlex OA URL            │
           │   3. scidownl ──── POLICY GATE  │
           │      ├─ enable_paid_or_grey_    │
           │      │    sources: true         │
           │      ├─ policy_clearance.json   │
           │      │    countersigned         │
           │      ├─ Unpaywall failed        │
           │      └─ OpenAlex failed         │
           │                                 │
           │  Success → papers table insert  │
           │            acquired_paper_id set│
           └────────────────┬────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                   PRISMA DASHBOARD (Phase 6)                        │
│               ka_topic_proposer.html                                │
│                                                                     │
│  Reads counts with one GROUP-BY SQL on article_references:          │
│                                                                     │
│  Gaps targeted (Task 2)           10                                │
│  Queries executed (SerpAPI)       10                                │
│  Records returned                 N                                 │
│  Duplicates removed               N                                 │
│  Stage-1 survivors (not rej'd)    N                                 │
│  Abstracts collected              N                                 │
│  → MISSING_ABSTRACT               N                                 │
│  Screened by classifier           N                                 │
│  → ACCEPT (on-topic, VOI≥0.5)    N                                 │
│  → EDGE_CASE (borderline)         N                                 │
│  → REJECT (off-topic)             N                                 │
│  PDFs acquired                    N                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5 Priority Gaps (Top VOI from Task 2 query_results.json)

All 10 queries in `query_results.json` share VOI scores in the 0.443–0.478 range. They are all DIRECTION-type (competing mechanistic accounts), which carries the highest priority weight (1.0) in `GAP_TYPE_PRIORITY_WEIGHTS`. The narrow spread comes from `corpus_coverage` (dense vs. sparse) and `depth_tier` (A/B/C) modulation in the VOI formula. The top 5 by VOI:

| Rank | display_id | Template | Step | VOI | Gap type | Why this is high VOI |
|------|------------|----------|------|-----|----------|----------------------|
| 1 | SC3 | ARCH_PROMENADE_TEMPORAL_PE_001 | 3 | 0.478 | DIRECTION | Holl's threshold-emotion claim is testable via skin-conductance / arousal under predictive-processing framing — a discriminating empirical test exists, so an answer would actually move the panel |
| 2 | SC3 | ARCH_PROMENADE_TEMPORAL_PE_001 | 1 | 0.478 | DIRECTION | Competing accounts of place-cell remapping at architectural thresholds; resolvable by hippocampal-recording or spatial-navigation imaging studies |
| 3 | L3 | LIGHT_CIRCADIAN_003 | — | 0.458 | DIRECTION | ipRGC-mediated circadian effect vs. cognitive/affective alternative; melatonin/PVT data adjudicates directly |
| 4 | NM1 | NEUROMOD_STRESS_001 | — | 0.454 | DIRECTION | HPA-axis recovery vs. autonomic-recovery account of hippocampal-volume effects; clean cortisol-vs-HRV contrast in the data |
| 5 | NM7 | NEUROMOD_STRESS_007 | — | 0.454 | DIRECTION | HPA-axis vs. photic-arousal explanation of bright-light → cognition; existing fMRI + saliva paradigms can split them |

**Why DIRECTION dominates the top 5.** The VOI formula in `VOICalculator.calculate_voi()` combines four ordinal modulators with the priority weight:
> `voi = priority_weight · uncertainty · corpus_factor · depth_factor`

DIRECTION's weight (1.0) is twice MECHANISM's (0.5) and ~43% above VALIDATION's (0.7). Even at maximum uncertainty (confidence = 0.0) and most favorable corpus/depth multipliers, a MECHANISM gap caps near 0.40 and a VALIDATION gap near 0.55, so neither can break into the 0.44–0.48 band that the top DIRECTION gaps occupy. This is a property of the Task 2 panel-set policy, not a property of our pipeline, and the Task 3 search runner does not re-rank — it consumes Task 2's order verbatim.

**Implication for harvest budgeting.** SerpAPI's free tier is 250 searches/month. Ten DIRECTION queries × ~10 results each ≈ 100 candidate rows in `article_references`, leaving ~240 credits of headroom for retries, secondary queries from MECHANISM/VALIDATION gaps in a later run, and other tracks' searches. We do **not** expand beyond the 10 Task-2 queries in this run.

---

## Abstract Fallback Chain (Phase 4B detail)

```
SerpAPI result:  title + snippet (2–3 sentences, NOT full abstract) + optional DOI
                     │
                     ▼ extract DOI from link URL if possible
                     │
           ┌─────────▼──────────┐
           │ 1. Semantic Scholar │ fetch_by_doi(doi) or search(title)
           │    ≤20 req/min      │ → returns .abstract field
           └─────────┬──────────┘
                     │ miss
           ┌─────────▼──────────┐
           │ 2. CrossRef        │ fetch(doi) → abstract field
           └─────────┬──────────┘
                     │ miss
           ┌─────────▼──────────┐
           │ 3. PubMed          │ search(title) → abstract
           └─────────┬──────────┘
                     │ miss
           ┌─────────▼──────────┐
           │ 4. OpenAlex        │ GET /works/doi:XXX → abstract_inverted_index
           └─────────┬──────────┘
                     │ miss
                     ▼
             tag: MISSING_ABSTRACT
             stored in article_references with triage_decision=NULL
             counted in PRISMA funnel separately
```

---

## Deduplication Logic

| Match type | Source | Action |
|-----------|--------|--------|
| `doi_exact` | article_references | UPDATE discovered_via, skip INSERT |
| `title_fuzzy` ≥ threshold | pdf_identity_inventory | INSERT with triage_stage='duplicate' |
| SHA-256 match | probe-collection-pdf | INSERT with triage_stage='duplicate' |
| No match | — | INSERT with triage_stage='metadata_only' |

---

## scidownl Policy Gate (Phase 5 detail)

All four conditions must hold before a single scidownl call:

1. `config.enable_paid_or_grey_sources == true` (YAML, defaults to `false`)
2. `policy_clearance.json` exists in project root (instructor countersigned)
3. Both Unpaywall and OpenAlex OA have failed for this `reference_id` in current run
4. `triage_decision == 'ACCEPT'` exactly (EDGE_CASE rows excluded)

Every call writes `pdf_acquisition_last_source = 'scidownl'` and a row to `lifecycle_transitions`.

---

## article_references Column List (Phase 3 detail)

| Column | Purpose | When set |
|--------|---------|----------|
| `reference_id` (PK) | `REF-YYYY-MM-DD-NNNNNN` synthetic ID | On insert |
| `doi` (UNIQUE, nullable) | Normalised, lowercased, no URL prefix | On insert (when extractable) |
| `title_raw` | Title exactly as harvester returned it | On insert |
| `title_normalized` | Lowercase, punctuation-stripped for fuzzy match | On insert |
| `first_author_surname` | For dedup tiebreak | On insert (best effort) |
| `publication_year` | Integer | On insert |
| `venue` | Journal/conference string | On insert |
| `raw_citation` | Messy reference-list line if from PDF harvest | On insert (review-PDF harvester only) |
| `snippet` | SerpAPI snippet or abstract fragment | On insert |
| `discovered_via` | Enum (see below) | On insert; UPDATE-appended on dup hit |
| `discovered_from_paper_id` | FK to `papers` if extracted from existing PDF | On insert (review-PDF harvester only) |
| `discovered_query` | The boolean string used | On insert (search-runner only) |
| `discovery_run_id` | `RUN-YYYY-MM-DD-HHMMSS` | On insert |
| `discovered_at` | ISO 8601 UTC | On insert |
| `triage_stage` | State machine: `metadata_only` → `abstract_pending` → `abstract_collected` → `triaged` → `acquiring` → `acquired` or `rejected_at_*` or `duplicate` | Updated atomically; every change logs to `lifecycle_transitions` |
| `triage_decision` | `ACCEPT` / `EDGE_CASE` / `REJECT` / `MISSING_ABSTRACT` / NULL while pre-decision | Phase 4 (Stage 2B) |
| `triage_reason` | Human-readable, never empty when decision set | Phase 4 |
| `abstract_text` | Full abstract once collected | Phase 4 (Stage 2A) |
| `abstract_source` | `semantic_scholar` / `crossref` / `pubmed` / `openalex` | Phase 4 (Stage 2A) |
| `classifier_confidence` | atlas_shared topic score on abstract | Phase 4 |
| `voi_score` | Inherited from gap that produced this query | On insert (copied forward) |
| `pdf_acquisition_attempts` | Counter, increments per cascade attempt | Phase 5 |
| `pdf_acquisition_last_source` | `unpaywall` / `openalex_oa` / `scidownl` / NULL | Phase 5 |
| `acquired_paper_id` | FK to `papers` when PDF lands | Phase 5 success |

### `discovered_via` enum (open set; new tags require contract bump)

`serpapi_scholar` · `scholarly_search` · `paperscraper_search` · `review_pdf_extract` · `openalex_expansion` · `crossref_search` · `student_upload`

### `lifecycle_transitions` (audit log, not state)

| Column | Notes |
|--------|-------|
| `transition_id` (PK) | autoincrement |
| `reference_id` (FK) | which row |
| `run_id` | which run caused the transition |
| `from_stage` | nullable on first insert |
| `to_stage` | required |
| `reason` | short string (e.g., `classifier_below_threshold`, `abstract_collected:semantic_scholar`, `pdf_acquired:unpaywall`) |
| `at` | ISO 8601 UTC |

This is the audit table the grader inspects for "atomic transitions logged" — Phase 4's 12-point criterion.

---

## Codebase File Map (what we reuse, what we build)

### Reuse as-is (no edits)

| File | What it provides |
|------|-----------------|
| `Article_Eater/src/services/paper_fetcher.py` | `SemanticScholarClient` (L704–), `CrossRefClient` (L450–), `PubMedClient` (L552–), `UnpaywallClient` (L1186–), `PaperFetcher.search()` unified entry, `estimate_study_type()` |
| `Article_Eater/src/cmr/voi_scoring.py` | `score_voi()` over findings dicts |
| `atlas_shared/src/atlas_shared/classifier_system.py` | Topic classifier (already used in `Article_Finder/triage/question_relevance.py`) |
| `atlas_shared/src/atlas_shared/relevance.py` | `AdjudicationResult` for classifier confidence |
| `Article_Finder/ingest/pdf_downloader.py` | `UnpaywallClient` (mirror of AE) + download logic |
| `Article_Finder/ingest/doi_resolver.py` | DOI normalisation helper (use `normalize_doi`) |
| `Article_Finder/ingest/ae_waiting_room_probe.py` | `probe_pdf_against_article_eater()` for foolproof corpus dedup |
| `Article_Finder/core/database.py` | SQLite connection + migration framework |
| `Article_Finder/core/schema_registry.py` | `apply_pending_schema_migrations()` — we register our new migration here |

### Read for reference, do not call directly

| File | What it tells us |
|------|------------------|
| `Article_Finder/ingest/abstract_fetcher.py` | Existing single-source abstract fetch; our Stage 2A is the multi-source upgrade |
| `Article_Finder/triage/classifier.py` | `HierarchicalClassifier` over embedding centroids; available if atlas_shared classifier is insufficient |

### Build new (this task)

| File | Phase | What it does |
|------|-------|-------------|
| `Track 2/Task 3/Phase 2/SEARCH_RUNNER_CONTRACT.md` | 2 | Spec for the search runner |
| `Track 2/Task 3/Phase 2/search_runner.py` | 2 | Wraps SerpAPI + scholarly + paper-scraper; writes article_references rows + search_results.json |
| `Track 2/Task 3/Phase 2/search_results.json` | 2 | Canonical raw harvest output (one record per candidate) |
| `Track 2/Task 3/Phase 2/migrations/001_article_references.sql` | 3 | DDL for article_references + lifecycle_transitions + v_acquisition_queue (referenced from Phase 2, owned by Phase 3) |
| `Track 2/Task 3/Phase 3/REFERENCE_HARVESTER_CONTRACT.md` | 3 | Spec for the review-PDF reference extractor (companion writer to article_references) |
| `Track 2/Task 3/Phase 3/reference_harvester.py` | 3 | Wraps AE's `extract_neuro_key_review_references.py` |
| `Track 2/Task 3/Phase 4/ABSTRACT_COLLECTOR_CONTRACT.md` | 4 | Stage 2A spec |
| `Track 2/Task 3/Phase 4/abstract_collector.py` | 4 | Fallback chain S2 → CrossRef → PubMed → OpenAlex |
| `Track 2/Task 3/Phase 4/TRIAGE_CONTRACT.md` | 4 | Stage 2B spec |
| `Track 2/Task 3/Phase 4/abstract_triage.py` | 4 | Runs atlas_shared + score_voi; writes ACCEPT/EDGE_CASE/REJECT/MISSING_ABSTRACT |
| `Track 2/Task 3/Phase 4/triage_results.json` | 4 | Per-paper decisions + reasons |
| `Track 2/Task 3/Phase 5/ACQUISITION_CONTRACT.md` | 5 | Stage 3 cascade spec |
| `Track 2/Task 3/Phase 5/pdf_acquirer.py` | 5 | Unpaywall → OpenAlex OA → scidownl (gated) |
| `Track 2/Task 3/Phase 5/policy_clearance.json` | 5 | Defaults absent; gate file (must be countersigned to enable scidownl) |
| `Track 2/Task 3/Phase 6/ka_topic_proposer.html` | 6 | PRISMA dashboard (single-page, reads from one SQL group-by) |
| `Track 2/Task 3/Phase 6/prisma_query.sql` | 6 | The one SQL behind the dashboard |
| `Track 2/Task 3/Phase 7/END_TO_END_TRACE.md` | 7 | One paper traced gap → SerpAPI → abstract → triage → acquired |
| `Track 2/Task 3/Phase 7/NULL_RESULTS.md` | 7 | Gaps with zero harvest |
| `Track 2/Task 3/Phase 7/MISSING_ABSTRACT_REPORT.md` | 7 | Papers triage couldn't reach |
| `Track 2/Task 3/Phase 7/VERIFICATION.md` | 7 | Verification questions that caught real problems |

---

## Run-ID Concept (why every artifact carries one)

A single execution of the pipeline is a **run**, identified by `RUN-YYYY-MM-DD-HHMMSS`. Every artifact this task produces carries that run_id so the PRISMA dashboard can scope counts to "this run" rather than "all time": the search runner stamps every `article_references` row with `discovery_run_id`, every `lifecycle_transitions` row gets the same `run_id`, and the dashboard's `WHERE run_id = ?` filter is what makes the funnel reproducible. A re-run with the same query set produces a new run_id and a new funnel — never overwrites the prior run.

---

## What Task 3 changes vs. Tasks 1 & 2

| | Task 1 (intake) | Task 2 (gap targeting) | Task 3 (search) |
|--|----------------|------------------------|-----------------|
| Input | A PDF | PNU templates | Query pairs from Task 2 |
| Output | Atlas Shared classification + corpus admission | Ranked gaps + query pairs | `article_references` rows + PRISMA funnel |
| Dedup probe | Yes (corpus dedup before storing) | n/a | Yes (DOI + title fuzzy before insert) |
| Touches PDFs | Yes (one inbound) | No | Only after Stage 2B ACCEPT |
| Adds DB tables | No (uses existing intake) | No (template-only) | Yes: `article_references`, `lifecycle_transitions`, view `v_acquisition_queue` |
| External APIs | None | None | SerpAPI, Semantic Scholar, CrossRef, PubMed, OpenAlex, Unpaywall (and gated scidownl) |

The biggest conceptual shift from Task 2 is the move from **deterministic input** (template files on disk) to **non-deterministic input** (live web search). Every Task-3 artifact must carry the run_id so the funnel reconstructs.
