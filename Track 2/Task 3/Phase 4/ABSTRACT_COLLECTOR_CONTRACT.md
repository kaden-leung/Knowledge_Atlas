# Abstract Collector Contract — Phase 4 Sub-phase 4B

**Track 2 · Task 3 · Phase 4**
**Author:** Kaden Leung
**Contract Version:** 1.0.0
**Last Updated:** 2026-05-31

---

## 1. System Summary

The abstract collector takes candidate papers that survived Stage 1 metadata triage and walks each one through a 4-source fallback chain — **Semantic Scholar → CrossRef → PubMed → OpenAlex** — until it finds a real abstract or every source comes up empty. Papers with no abstract from any source are tagged `MISSING_ABSTRACT` (never silently dropped). The collector writes results into the `article_references` table's `abstract_text`, `abstract_source`, and `study_type` columns, with one paired `lifecycle_transitions` row per attempted candidate.

SerpAPI gives titles and 2–3 sentence snippets, not full abstracts. The course spec is firm: snippets are not abstracts. This module fills that gap before Phase 4 Stage 2B can make a triage decision.

---

## 2. Inputs

### 2.1 From `article_references`

Each row where `triage_stage = 'abstract_pending'` is a candidate. The collector reads:

| Column | Type | Used for |
|---|---|---|
| `reference_id` | TEXT | Lookup + transition logging |
| `doi` | TEXT or NULL | Preferred lookup key — passed to S2/CrossRef/PubMed/OpenAlex first |
| `title_raw` | TEXT | Fallback search key when DOI is null or returns no abstract |
| `publication_year` | INTEGER or NULL | Disambiguator for title-search at PubMed and OpenAlex |
| `venue` | TEXT or NULL | Reserved; not used in 4B (Stage 2B may use it) |

### 2.2 From `query_results.json`

Not read in 4B. (4D / VOI derivation territory.)

### 2.3 Configuration

| Parameter | Default | Meaning |
|---|---|---|
| `db_path` | `Track 2/Task 3/task3_pipeline_lifecycle.db` | Local DB (source of truth) |
| `run_id` | required | Stamped on every `lifecycle_transitions` row |
| `max_candidates` | None (= all) | Process only the first N `abstract_pending` rows |
| `mock` | `False` | Read abstracts from fixture JSON instead of network |
| `mock_fixtures_dir` | `Phase 4/fixtures/` | Where to find `mock_*_abstract.json` files |
| `dry_run` | `False` | Plan to in-memory SQLite; no real DB write |

### 2.4 External clients (reused)

| Client | Path | Used for |
|---|---|---|
| `SemanticScholarClient` | `Article_Eater/src/services/paper_fetcher.py:704` | DOI lookup + title search |
| `CrossRefClient` | `Article_Eater/src/services/paper_fetcher.py:450` | DOI lookup |
| `PubMedClient` | `Article_Eater/src/services/paper_fetcher.py:552` | DOI/PMID fetch + title+year search |
| `OpenAlexClient` | **new — `Phase 4/openalex_client.py`** | DOI lookup + title+year search |
| `estimate_study_type` | `Article_Eater/src/services/paper_fetcher.py:1109` | Add `study_type` to every output |
| `normalize_doi`, `normalize_title` | `Article_Finder/core/ae_corpus_dedupe.py` | Pre-call normalization |

---

## 3. Processing

For each row in the input set:

1. **Normalize**. `doi_norm = normalize_doi(row.doi)` (returns `None` for empty/missing); `title_norm = normalize_title(row.title_raw)`.
2. **Walk the fallback chain.** Stop at the first source that returns a non-empty abstract.

   | Step | Condition | Source call |
   |---|---|---|
   | 1 | `doi_norm` is set | `s2.fetch_by_doi(doi_norm)` → check `.metadata.abstract` |
   | 2 | (no abstract yet) AND `title_raw` is set | `s2.search(title_raw)` → check first hit's `.abstract` |
   | 3 | (no abstract yet) AND `doi_norm` is set | `crossref.fetch(doi_norm)` → check `.metadata.abstract` |
   | 4 | (no abstract yet) AND `doi_norm` is set | `pubmed.fetch(doi_norm)` → check `.metadata.abstract` |
   | 5 | (no abstract yet) AND `title_raw` + `publication_year` are set | `pubmed.search(f"{title}[Title] {year}[PDAT]")` → check first hit's `.abstract` |
   | 6 | (no abstract yet) AND `doi_norm` is set | `openalex.fetch_abstract_by_doi(doi_norm)` |
   | 7 | (no abstract yet) AND `title_raw` is set | `openalex.fetch_abstract_by_title_year(title_raw, publication_year)` |
   | 8 | (no abstract yet) — terminal | Tag `MISSING_ABSTRACT` |

3. **Apply study-type estimate.** `study_type = estimate_study_type(abstract, title_raw)`. Always computed, even on `MISSING_ABSTRACT` (will return `None` when no text is available).
4. **Write back to DB** in a single per-row transaction:
   - On success: `UPDATE article_references SET abstract_text=?, abstract_source=?, study_type=?, triage_stage='abstract_collected', updated_at=? WHERE reference_id=?`
   - On MISSING_ABSTRACT: `UPDATE article_references SET abstract_text=NULL, abstract_source='MISSING_ABSTRACT', study_type=?, triage_stage='abstract_missing', triage_decision='MISSING_ABSTRACT', triage_reason='no_abstract_from_any_source', updated_at=? WHERE reference_id=?`
   - In both cases: `INSERT INTO lifecycle_transitions (...) VALUES (..., created_by='abstract_collector', reason='abstract_source:<source>')`
5. **Append to in-memory report** for the run-summary JSON.

---

## 4. Outputs

### 4.1 DB updates

Columns mutated per row:

| Column | Value when abstract found | Value on MISSING_ABSTRACT |
|---|---|---|
| `abstract_text` | full abstract string | `NULL` |
| `abstract_source` | one of `semantic_scholar` / `crossref` / `pubmed` / `openalex` | `MISSING_ABSTRACT` |
| `study_type` | from `estimate_study_type()` (e.g., `meta_analysis`, `rct`, `cross_sectional`, `review`) — may be `NULL` | `NULL` (unless title alone matches a study-type keyword) |
| `triage_stage` | `abstract_collected` | `abstract_missing` |
| `triage_decision` | unchanged (`NULL`; Stage 2B fills this in 4D) | `MISSING_ABSTRACT` (terminal) |
| `triage_reason` | unchanged | `no_abstract_from_any_source` |
| `updated_at` | UTC `YYYY-MM-DDTHH:MM:SSZ` | UTC `YYYY-MM-DDTHH:MM:SSZ` |

### 4.2 `lifecycle_transitions`

One row per processed candidate. `created_by='abstract_collector'`. `reason='abstract_source:<source>'` (success) or `reason='abstract_source:MISSING_ABSTRACT'` (terminal miss).

### 4.3 `abstract_collection_report.json`

Written at end of run. Schema:

```json
{
  "schema_version": "1.0.0",
  "run_id": "RUN-...",
  "started_at": "2026-...Z",
  "ended_at":   "2026-...Z",
  "candidates_processed": 600,
  "abstracts_found": 420,
  "missing_abstracts": 180,
  "hit_rate": 0.70,
  "hit_rate_doi_only": 0.85,
  "source_breakdown": {
    "semantic_scholar": 250,
    "crossref": 90,
    "pubmed": 50,
    "openalex": 30,
    "MISSING_ABSTRACT": 180
  },
  "study_type_breakdown": {
    "review": 80,
    "rct": 30,
    "experimental": 100,
    "cross_sectional": 40,
    "meta_analysis": 12,
    "qualitative": 8,
    "longitudinal": 5,
    "case_study": 5,
    "survey": 20,
    "systematic_review": 10,
    "(none)": 290
  },
  "errors": []
}
```

---

## 5. Rate-Limit Policy

Every source call goes through a `_RateLimiter`. The collector does **not** manage its own delays — it delegates to the per-client rate limiters that already exist in `paper_fetcher.py` and `openalex_client.py`.

| Source | Min delay (no API key) | Min delay (with API key) | Source file |
|---|---|---|---|
| Semantic Scholar | 3.1 s | 1.1 s | `paper_fetcher.py:704` |
| CrossRef | 0.5 s | n/a (polite pool via `mailto`) | `paper_fetcher.py:450` |
| PubMed | 0.35 s | 0.12 s (with `NCBI_API_KEY`) | `paper_fetcher.py:552` |
| OpenAlex | 0.12 s | n/a (polite pool via `mailto`) | `Phase 4/openalex_client.py` |

**Retry policy:** one retry on HTTP 429 or 5xx with a 10 s sleep, then advance to next source on second failure (never spin in retry).

**Tests must verify:** at least one `_RateLimiter.wait()` (or equivalent mock `sleep_fn`) call per source per candidate. See SC-RA.

---

## 6. Non-Goals

- **No new search.** This module reads from `article_references`; it does not call SerpAPI / scholarly / paperscraper.
- **No triage decision.** Setting `triage_decision` is Stage 2B (sub-phase 4D), except for the `MISSING_ABSTRACT` terminal case which is set here because Stage 2B cannot triage what doesn't exist.
- **No abstract-text cleaning** beyond what the source clients already do (CrossRef strips JATS XML; PubMed assembles structured `AbstractText` sections). The collector stores what the client returns.
- **No PDF download.** Phase 5.
- **No full-text retrieval.** Abstract only.

---

## 7. Definitions

### 7.1 Abstract
A multi-sentence block of text written by the paper's authors describing the study's purpose, methods, results, and conclusion. Distinct from a *snippet*.

### 7.2 Snippet
The 2–3 sentence fragment that SerpAPI returns. **Not** an abstract. Already stored in `article_references.snippet` from Phase 2; ignored by this module.

### 7.3 Source
One of `semantic_scholar`, `crossref`, `pubmed`, `openalex`. The string written to `abstract_source` identifies which source actually returned the abstract.

### 7.4 `MISSING_ABSTRACT`
Terminal state for a candidate where every fallback source returned no abstract. Written verbatim to `abstract_source`; also writes `triage_decision='MISSING_ABSTRACT'` so Stage 2B doesn't need to special-case it.

### 7.5 Hit rate
`abstracts_found / candidates_processed`. Reported overall and DOI-only. Acceptance target: ≥ 70 % overall; ≥ 85 % on DOI-bearing candidates (course spec).

### 7.6 Study type
A coarse label inferred from text by `estimate_study_type(abstract, title)` — values are `meta_analysis`, `systematic_review`, `rct`, `longitudinal`, `cross_sectional`, `case_study`, `review`, `experimental`, `survey`, `qualitative`, or `None`.

### 7.7 Ambiguous title match
When a title-search returns more than one candidate paper from a source. Policy: **take the first hit** (S2/PubMed/OpenAlex rank by relevance by default). Record `title_used` on the result for later audit.

---

## 8. Invariants

- **I-1.** Every candidate that enters the collector reaches one of two end states: `triage_stage='abstract_collected'` (with `abstract_text` non-null) or `triage_stage='abstract_missing'` (with `abstract_source='MISSING_ABSTRACT'`). No silent drops.
- **I-2.** `abstract_source` is non-null on every processed row. The four valid source tokens plus `MISSING_ABSTRACT` are the only legal values.
- **I-3.** Every `UPDATE article_references` is paired with an `INSERT INTO lifecycle_transitions` in the same per-row transaction. (Test verifies row counts match.)
- **I-4.** Every `lifecycle_transitions` row from this module has `created_by='abstract_collector'`.
- **I-5.** No HTTP request is issued in `mock=True` mode. No live client is instantiated.
- **I-6.** `_RateLimiter.wait()` (or equivalent) is invoked at least once per source per candidate, never zero times.
- **I-7.** Source calls are tried in order S2 → CrossRef → PubMed → OpenAlex. A successful earlier source short-circuits — later sources are not called for that candidate.
- **I-8.** Every emitted timestamp matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` (same format as Phase 2 SC-32 and Phase 3 SCHEMA_CONTRACT I-6).

---

## 9. Success Conditions

| SC | Statement | Test |
|---|---|---|
| SC-FB | The fallback chain attempts multiple sources, not just S2 — when S2 returns no abstract, CrossRef is tried; if that fails, PubMed; if that fails, OpenAlex. | `test_fallback_chain_uses_crossref_when_s2_empty`, `test_fallback_chain_uses_pubmed_when_crossref_empty`, `test_fallback_chain_uses_openalex_last` |
| SC-RA | Each source-call site sleeps via its `_RateLimiter` before issuing the HTTP request. Verified by counting `sleep_fn` invocations per source. | `test_rate_limit_observed_per_source` |
| SC-MA | The run report's `missing_abstracts` count equals the number of `abstract_source='MISSING_ABSTRACT'` rows after the run. | `test_missing_abstract_count_tracked_and_reported` |
| SC-AS | After processing, every candidate has a non-null `abstract_source` containing one of the 5 allowed tokens. | `test_abstract_source_field_set_on_every_row` |
| SC-ST | The output report includes a `study_type_breakdown` populated from `estimate_study_type()` calls. Every successful result has `study_type` recorded. | `test_study_type_in_output` |
| SC-HR | Hit rate on DOI-bearing candidates in the test fixture set is ≥ 70 %. (Tested against a curated 10-row DOI fixture where 8 sources succeed.) | `test_doi_hit_rate_meets_target` |
| SC-AT | When title-search returns 2+ candidates, the collector picks the first hit and records `title_used` for audit. | `test_ambiguous_title_takes_first_hit` |
| SC-DR | `--dry-run` writes nothing to the on-disk DB; the in-memory copy receives the planned updates. | `test_dry_run_no_disk_writes` |
| SC-MK | `mock=True` reads fixture JSON and instantiates **no** real HTTP clients. | `test_mock_mode_no_real_clients_instantiated` |
| SC-NR | DOI is normalized via `normalize_doi()` before each source call. URL-prefixed DOIs (`https://doi.org/...`) collapse to bare DOI form. | `test_doi_normalized_before_lookup` |
| SC-IT | One `INSERT INTO lifecycle_transitions` row per processed candidate; every row has `created_by='abstract_collector'`. | `test_one_transition_per_candidate` |
| SC-SC | When S2 returns an abstract on the first call, no other sources are queried. | `test_short_circuit_on_first_hit` |

---

## 10. Known Limitations

1. **First-hit policy for ambiguous title matches.** Title-search ranking is source-dependent and not deterministic. A different ranking on S2 vs CrossRef may pick different papers. The `title_used` field is recorded for later audit; no per-result similarity threshold is enforced.
2. **PubMed DOI fetch is best-effort.** `PubMedClient.fetch(doi)` calls `efetch.fcgi` with the DOI as if it were a PMID. PubMed handles this for some DOIs (returns the right article) but not all. We treat the call as "best-effort with cheap failure" rather than running a separate PMID-resolution step.
3. **OpenAlex abstract_inverted_index decode is lossy.** OpenAlex returns word positions; we reconstruct by space-joining positions in order. Punctuation may be misplaced (the index doesn't carry it). The reconstructed text is good enough for Stage 2B classification but not for verbatim quotation.
4. **CrossRef abstracts often have JATS XML tags.** The CrossRef client (`paper_fetcher.py:530`) already strips them via regex; we trust that step.
5. **No retry beyond one attempt.** Per source: one 10 s backoff retry on 429/5xx, then move to next source. We never spin trying the same source multiple times for the same candidate.
6. **Network errors fall through silently.** A `urllib.error.URLError` from any source is treated the same as "no abstract" — we advance to the next source and log the underlying error in the report's `errors` array. No exception escapes the collector.

---

## Change Log

- **1.0.0 (2026-05-31)** — Initial release. SC-FB, SC-RA, SC-MA, SC-AS, SC-ST, SC-HR, SC-AT, SC-DR, SC-MK, SC-NR, SC-IT, SC-SC. Aligned with PHASE_4_PLAN.md §3B (which it supersedes for contract-level statements). Adds OpenAlex as the 4th source; reuses S2/CrossRef/PubMed clients from `Article_Eater/src/services/paper_fetcher.py`.
