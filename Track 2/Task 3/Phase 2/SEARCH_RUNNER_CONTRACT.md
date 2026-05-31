# Search Runner Contract — Phase 2

**Track 2 · Task 3 · Phase 2**
**Author:** Kaden Leung
**Contract Version:** 1.2.0
**Last Updated:** 2026-05-28
**Output JSON Schema Version:** 1.1.0
**Machine-readable schema:** [`schema/search_results.schema.json`](schema/search_results.schema.json)

---

## 1. System Summary

The Phase 2 search runner takes the boolean queries produced by Task 2 and turns them into a single, deduplicated JSON file of candidate paper records harvested from three sources: SerpAPI's Google Scholar engine (paid, 1 credit per query), the `scholarly` Python package (free Google Scholar fallback, rate-limited), and `paperscraper` (free preprint-server channel for arXiv/bioRxiv/medRxiv/chemRxiv). The runner enforces a per-run credit cap, records queries that returned zero results, refuses to make live network calls without an explicit confirmation flag, and outputs three files: `search_results.json` (deduplicated candidates with provenance), `null_results.json` (queries with no hits across all sources), and `run_log.json` (per-source statistics for the run).

This contract is the single source of truth that downstream code (Phase 3 DB loader) and reviewers can rely on without reading the implementation.

---

## 2. Inputs

### 2.1 Query input file (`query_results.json` from Task 2)

The runner reads a JSON file with this top-level shape:

```json
{
  "queries": [
    {
      "boolean_query": "string — REQUIRED — the query string sent to each adapter",
      "display_id":    "string — REQUIRED — short ID like 'SC3', 'L4', 'NM1'",
      "step_number":   "int or null — OPTIONAL — substep within a query group",
      "voi_score":     "float or null — OPTIONAL — value-of-information score"
    }
  ]
}
```

**Required per row:** `boolean_query`, `display_id`. **Optional:** `step_number` (concatenated as `"{display_id}-step{step_number}"` when present), `voi_score` (passed through to each candidate as `source_voi_score`). **Other top-level keys ignored.**

### 2.2 Adapter configuration

The runner accepts a list of adapter instances satisfying the `HarvesterAdapter` protocol. Each adapter exposes:
- `name: str` — used to key per-source statistics
- `credit_cost_per_call: int` — used by the credit cap pre-check
- `search(query, num_results, *, run_id, query_display_id, voi_score) -> list[CandidateRecord]`

### 2.3 Runtime parameters

| Parameter | Default | Meaning |
|---|---|---|
| `max_queries` | None (= all) | Process only the first N query rows in input order |
| `num_results` | 10 | `num` parameter sent to each adapter |
| `max_credits` | 50 | Hard cap on credits consumed by a single run |
| `run_id` | auto-generated `RUN-YYYYMMDD-HHMMSS` | Provenance tag stamped on every record |
| `dry_run` | False | No network calls, no file writes |

---

## 3. Processing

The runner executes these stages in order, once per invocation:

1. **Load.** Read the query input file. If `max_queries` is set, slice to the first N rows.
2. **Per-query preflight.** For each query, check `len(query) <= 256`. Failures append to `skipped_queries` with `skip_reason: "query_too_long"`; no adapter is called.
3. **Fan out across adapters.** For each adapter in order:
   - If `credit_cost_per_call > 0` and serving this query would push `credits_used` past `max_credits`, skip with reason `credit_cap_reached`.
   - **Pre-deduct** the adapter's cost from the credit budget before issuing the call. The credit is counted as spent the moment we attempt the call — even if the call raises before returning. (See Invariant I-1.)
   - Call `adapter.search(...)`, accumulate raw result counts in `per_source_stats[adapter.name]`. Exceptions from the adapter are caught, logged to stderr, counted in `per_source_stats[adapter.name].errors`, and do not abort the run.
4. **Within-query dedupe** (cross-source, see §7.4).
5. **Across-query dedupe** (cross-query, see §7.5).
6. **Null-result recording.** If no adapter returned any candidate for this query, append an entry to `null_results`.
7. **Output write.** Write `search_results.json`, `null_results.json`, `run_log.json`. If `dry_run=True`, skip step 7 entirely.

### 3.1 Determinism & ordering

- Queries are processed in **input file order**. The runner does not re-sort by `voi_score` or any other field.
- Within `results`, records are emitted in the order they were first discovered (first by query, then by source within a query, then by `result_position` within a source's response).
- The `candidate_id` is assigned in emission order: `CAND-{run_id}-{idx:06d}`, idx starting at 1.
- These ordering guarantees hold across reruns **with identical input and identical fixture contents** in mock mode.

### 3.2 Idempotency

Two outputs from the same input are guaranteed to have identical `candidate_id` values for the same logical paper, provided the input file and any fixture files are identical. Phase 3 ingestion may treat `(run_id, candidate_id)` as a unique idempotency key.

> ⚠️ The `discovered_at`, `queried_at`, `started_at`, `ended_at`, and `generated_at` timestamp fields are **wall-clock** values and will differ between runs. Phase 3 must exclude these from any equality check.

---

## 4. Outputs

All output JSON files are validated against [`schema/search_results.schema.json`](schema/search_results.schema.json). The prose below describes the same shape; the JSON Schema is authoritative if the two disagree.

### 4.1 `search_results.json`

| Path | Type | Nullable | Meaning |
|---|---|---|---|
| `metadata.schema_version` | string | NOT NULL | Exactly `"1.1.0"` |
| `metadata.run_id` | string | NOT NULL | `RUN-YYYYMMDD-HHMMSS` |
| `metadata.generated_at` | string | NOT NULL | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ` |
| `metadata.input_query_count` | int | NOT NULL | Total queries in input file |
| `metadata.queries_processed` | int | NOT NULL | `len(queries) - sum(queries_skipped.values())` |
| `metadata.queries_skipped` | object | NOT NULL | Counter map: `{reason: int}` |
| `metadata.sources_enabled` | array<string> | NOT NULL | Adapter names enabled this run |
| `metadata.per_source_stats` | object | NOT NULL | See §4.1.1 |
| `metadata.credits_used` | int | NOT NULL | Total credits spent (see §5) |
| `metadata.credits_max` | int | NOT NULL | Hard cap for this run |
| `metadata.candidates_total_raw` | int | NOT NULL | Sum across sources before dedupe |
| `metadata.candidates_after_dedupe` | int | NOT NULL | Final unique candidate count |
| `metadata.null_result_queries` | int | NOT NULL | Count of queries with zero candidates |
| `metadata.mock_mode` | bool | NOT NULL | True iff any adapter is a `MockAdapter` |
| `metadata.serpapi_engine` | string | NOT NULL | Always `"google_scholar"` |
| `results` | array<object> | NOT NULL (may be empty) | See §4.1.2 |
| `null_results` | array<object> | NOT NULL (may be empty) | See §4.2 |
| `skipped_queries` | array<object> | NOT NULL (may be empty) | See §4.3 |

#### 4.1.1 `per_source_stats[adapter_name]`

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `queries_run` | int | NOT NULL | Times this adapter's `search()` was attempted |
| `results_raw` | int | NOT NULL | Records this adapter returned across all queries (successful calls only) |
| `retries` | int | NOT NULL | Currently always 0 — retries are internal to the adapter |
| `errors` | int | NOT NULL | Times this adapter raised an exception during a run |

#### 4.1.2 `results[i]` (per candidate)

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `candidate_id` | string | NOT NULL | `CAND-{run_id}-{idx:06d}`, stable across reruns with identical input |
| `discovery_run_id` | string | NOT NULL | The `run_id` of the run that found this paper |
| `discovered_via` | string | NOT NULL | The adapter tag (`serpapi_scholar`, `scholarly_search`, `paperscraper_search`) that first found this paper |
| `merged_from_sources` | array<string> | NOT NULL | Unique adapter tags that all surfaced this paper |
| `merged_from_queries` | array<string> | NOT NULL | Unique `display_key` values that all surfaced this paper |
| `discovered_query` | string | NOT NULL | The first boolean query that found this paper |
| `discovered_query_display_id` | string | NOT NULL | The first query's display_key |
| `source_voi_score` | float | NULLABLE | Verbatim copy of `voi_score` from the discovering query |
| `discovered_at` | string | NOT NULL | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ` |
| `result_position` | int | NOT NULL | Position in the source's response that first surfaced this paper (1-indexed, source-scoped, kept for provenance only — see §7.7) |
| `title_raw` | string | NOT NULL (may be `""`) | Verbatim title from the source |
| `title_normalized` | string | NOT NULL (may be `""`) | Lowercased, punctuation-stripped title used as a dedup key |
| `doi` | string | NULLABLE | Lowercased, prefix-stripped DOI (e.g. `10.1073/pnas.1912264116`) |
| `url` | string | NULLABLE | Landing-page URL |
| `snippet` | string | NULLABLE | 2–3 sentence fragment (**not** a full abstract) |
| `authors_raw` | string | NULLABLE | Comma-separated author string |
| `first_author_surname` | string | NULLABLE | Best-effort surname extraction — see §10.3 known limitation |
| `publication_year` | int | NULLABLE | Year of publication |
| `venue` | string | NULLABLE | Journal or venue name |
| `cited_by_count` | int | NULLABLE | Maximum citation count seen across all sources for this paper |
| `resource_pdf_url` | string | NULLABLE | PDF URL when the source provided one |

### 4.2 `null_results[i]`

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `discovered_query_display_id` | string | NOT NULL | e.g. `"SC3-step3"` |
| `discovered_query` | string | NOT NULL | The boolean query string |
| `source_voi_score` | float | NULLABLE | VOI score of the query that returned nothing |
| `reason` | string | NOT NULL | Always `"zero_results_across_all_sources"` |
| `queried_at` | string | NOT NULL | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ` |

The same array also appears as `search_results.json.null_results` and as the entire body of `null_results.json`.

### 4.3 `skipped_queries[i]`

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `discovered_query_display_id` | string | NOT NULL | The query's display_key |
| `discovered_query` | string | NOT NULL | The boolean query string |
| `skip_reason` | string | NOT NULL | `"query_too_long"` \| `"credit_cap_reached"` |
| `skipped_at` | string | NOT NULL | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ` |

### 4.4 `run_log.json`

| Field | Type | Nullable | Meaning |
|---|---|---|---|
| `run_id` | string | NOT NULL | The run's identifier |
| `started_at` | string | NOT NULL | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ` |
| `ended_at` | string | NOT NULL | UTC timestamp, `YYYY-MM-DDTHH:MM:SSZ` |
| `sources` | array<string> | NOT NULL | Enabled adapter names |
| `queries_processed` | int | NOT NULL | Count of input query rows walked |
| `credits_used` | int | NOT NULL | Total credits spent |
| `per_source_stats` | object | NOT NULL | Same shape as §4.1.1 |
| `null_result_queries` | int | NOT NULL | Count of null-result queries |
| `skipped_queries` | int | NOT NULL | Count (not the list) |

---

## 5. Credit Policy

The SerpAPI free tier allots **250 credits per calendar month**. Each call to the `google_scholar` engine costs exactly **1 credit**. The runner enforces three layers of protection:

1. **Pre-call accounting.** Credit is deducted from `credits_used` **before** the adapter call. If `adapter.search` raises after the network has already spent the credit, the spend is still recorded. This is intentionally pessimistic — we may over-report credit usage by 1 in the rare case the call fails before reaching SerpAPI, but we never under-report.
2. **Per-run hard cap.** `DEFAULT_MAX_CREDITS = 50`. The pre-check refuses any call that would push `credits_used` past `max_credits`. A single misconfigured run cannot consume more than `max_credits`.
3. **`--confirm-live` gate.** The CLI refuses to make any live network call unless invoked with `--confirm-live`. Without this flag (and without `--dry-run` or `--mock-from`), the program prints an error to stderr and exits with code 1 before any adapter is constructed.

`scholarly` and `paperscraper` adapters are free (`credit_cost_per_call = 0`) and never count against the credit budget.

---

## 6. Non-Goals

Deliberately **out of scope** for Phase 2:

- **No DB writes.** Phase 2 produces JSON files only. Phase 3 owns the `article_references` table DDL, migrations, and `db_loader.py`.
- **No abstract enrichment.** The `snippet` field contains the 2–3 sentence fragment SerpAPI returns; full abstracts via `SemanticScholarClient` / `CrossRefClient` / `PubMedClient` are a Phase 4 concern.
- **No triage / classification.** Phase 4 owns this.
- **No PDF download.** `resource_pdf_url` is recorded when SerpAPI provides it. Actual PDF retrieval (including `scidownl` policy gate) is Phase 5.
- **No corpus duplicate suppression.** Phase 3 calls `match_against_ae_corpus()` against the assembled candidate set.
- **No reference harvesting from PDFs.** Phase 3 owns the companion reference harvester.
- **No preprint↔published version clustering.** A bioRxiv preprint and the published Nature version are treated as distinct candidates if they have different DOIs. Phase 4 may add a version cluster step.
- **No checkpoint or resume.** If the runner is killed mid-execution, all in-progress work is lost. Credits already spent are not recoverable. Future hardening may add a journal file.

---

## 7. Definitions

### 7.1 Credit
A unit of API quota consumed by a single SerpAPI call. Each adapter declares its cost via `credit_cost_per_call`.

### 7.2 Transient error
An error expected to resolve on retry — network timeouts, connection drops, HTTP 429, generic 5xx. The SerpAPI adapter retries transient errors once after a backoff (30 s for rate-limit signals, 5 s otherwise).

### 7.3 Non-transient error
An error that will not resolve on retry — invalid API key, unauthorized, bad request, malformed query. The SerpAPI adapter raises `ValueError` immediately without retrying.

### 7.4 Cross-source dedupe
Within a single query's results, collapse duplicates across adapters using the **match policy** in §7.6. First-seen scalar fields are retained, except `cited_by_count` which takes the maximum non-null value across the merging records (citation counts grow monotonically). The `merged_from_sources` list takes the union of all matching records' `discovered_via` values, preserving order of first appearance.

### 7.5 Cross-query dedupe
Across queries within the same run, collapse candidates representing the same paper using the same match policy. The `merged_from_queries` list takes the union of all matching records' `discovered_query_display_id` values.

### 7.6 Match policy
Two candidates are considered the same paper when **either**:
- both have a non-empty `doi` and the normalized DOIs are equal, **or**
- both have `doi=None`, both have normalized titles that pass the §7.6.1 safety check, and the normalized titles are equal.

#### 7.6.1 Title safety check
A title may serve as a dedup key only if its normalized form contains at least **4 significant words** (each ≥ 3 characters). This prevents collapsing distinct papers that share generic titles like `"Introduction"`, `"Discussion"`, `"Editorial"`. Candidates that fail this check are kept as distinct records regardless of title overlap.

### 7.7 Result position
The 1-indexed position the source returned this paper at. After dedupe, the merged record retains the first-seen `result_position` — this is the position from the first adapter that surfaced the paper, **not** a global rank. Phase 3 should treat this field as provenance metadata, not as a ranking signal.

### 7.8 Null result
A query that returned zero candidates across **every** enabled adapter. Distinct from a query that was skipped (`skipped_queries`).

### 7.9 Candidate
A single row in `search_results.json.results`. One paper, with provenance, after both dedupe passes.

---

## 8. Invariants

These properties must hold for any successful (non-aborted) run:

- **I-1 (credit cap).** `credits_used <= max_credits` is **always** true. The pre-check rejects any call that would violate it. Because credit is deducted before the call, even a crash inside `adapter.search()` cannot violate I-1.
- **I-2 (provenance completeness).** Every record in `results` has non-empty `discovery_run_id`, `discovered_via`, `merged_from_sources` (length ≥ 1), `merged_from_queries` (length ≥ 1), and a non-empty `candidate_id`.
- **I-3 (uniqueness of match keys within run).** No two records share the same normalized DOI when both DOIs are non-null; no two records share a normalized title when both DOIs are null AND the title passes the §7.6.1 safety check.
- **I-4 (results_raw is the success counter).** `per_source_stats[name].results_raw` equals the sum of `len(results)` returned by **successful** calls to `adapter.search()` for that source. Failed calls (exceptions) do not contribute. Callers reconciling totals must use `queries_run = results-producing calls + errors`.
- **I-5 (input row reaches a recorded end state).** Every input query row reaches at least one of: `skipped_queries` (preflight failure or credit-cap halt on a paid adapter), `null_results` (zero hits across all attempted adapters), or `results` (one or more records list this query in `merged_from_queries`). A query may legally appear in **both** `skipped_queries` and `results` — for example, when SerpAPI was credit-capped but `scholarly` returned hits. Phase 3 must deduplicate query counts by `display_key` if it needs a single tally.
- **I-6 (live-call gating).** No HTTP request is issued unless either `--confirm-live` was passed or all configured adapters are `MockAdapter` instances.
- **I-7 (timestamp format).** Every timestamp emitted by the runner matches the regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$` (RFC 3339 UTC, second-precision, `Z`-terminated).

---

## 9. Success Conditions

Every SC below is verified by at least one test in `test_adapters.py` or `test_search_runner.py`.

### 9.1 Adapter layer

#### SC-1 — SerpAPI engine is always `google_scholar`
`SerpAPIAdapter.search()` passes `engine="google_scholar"` to every `GoogleSearch` call.
**Tested by:** `test_serpapi_engine_param`

#### SC-2 — SerpAPI parses one `CandidateRecord` per organic result
Given a SerpAPI JSON response with N entries in `organic_results`, `_parse()` produces exactly N `CandidateRecord` objects, in the same order, each carrying a non-empty `title_raw`.
**Tested by:** `test_serpapi_parse_titles`

#### SC-3 — DOI extracted from any URL containing a DOI path
The DOI regex `10\.\d{4,9}/[-._;()/:A-Za-z0-9]+` is applied to both `link` and `resources[].link`. Successful extraction populates `doi` with the normalized DOI (lowercased, prefixes stripped). At least three URL patterns are covered: bare `doi.org/`, publisher pages with DOI paths, and preprint server paths.
**Tested by:** `test_serpapi_doi_extraction`, `test_doi_extraction_regex_three_url_patterns`, `test_doi_normalized_lowercase`

#### SC-4 — PDF URL extracted from `resources` with `file_format="PDF"`
**Tested by:** `test_serpapi_pdf_extraction`

#### SC-5 — Transient rate-limit error triggers one retry with 30 s sleep
**Tested by:** `test_serpapi_retry_on_rate_limit`

#### SC-6 — Non-transient error raises `ValueError` immediately
**Tested by:** `test_serpapi_no_retry_on_400`

#### SC-7 — Missing API key raises `EnvironmentError` at construction
**Tested by:** `test_serpapi_missing_key_raises`

#### SC-8 — `scholarly` enforces ≥5 s rate limit between calls
**Tested by:** `test_scholarly_rate_limit_sleep`

#### SC-9 — Scholar block raises `RuntimeError`
When `scholarly.search_pubs()` signals that Google Scholar has blocked or throttled access, the adapter raises `RuntimeError` with `"blocked"` in the message.
**Tested by:** `test_scholarly_block_raises_runtime`

#### SC-10 — `scholarly` results map cleanly into `CandidateRecord`
**Tested by:** `test_scholarly_parse_fixture`

#### SC-11 — `paperscraper` venue is read from `journal` field when present; defaults to `"arXiv"` otherwise
**Tested by:** `test_paperscraper_parse_fixture`, `test_paperscraper_venue_defaults_to_arxiv`

#### SC-12 — `MockAdapter` reads the source-specific fixture file
**Tested by:** `test_mock_adapter_reads_fixture`

#### SC-13 — Credit cost per call: SerpAPI=1, scholarly=0, paperscraper=0
**Tested by:** `test_credit_cost_per_call`

### 9.2 Runner orchestration

#### SC-14 — Every query processed once per adapter (subject to caps and preflight)
**Tested by:** `test_every_query_processed_once_per_source`

#### SC-15 — `credits_used` equals paid adapter calls **attempted**, even when the call raises
Each paid adapter call increments `credits_used` by `credit_cost_per_call` **before** the call is issued. If the call subsequently raises, `credits_used` is not rolled back. With one paid adapter (SerpAPI, C=1) and N attempted calls, `report.credits_used == N`.
**Tested by:** `test_credits_equal_serpapi_calls`, `test_credit_counted_even_on_adapter_exception`

#### SC-16 — Credit cap halts further paid calls and records the skip
**Tested by:** `test_max_credits_skips_overflow`

#### SC-17 — Runner forwards `run_id` to each adapter call
**Tested by:** `test_every_record_has_run_provenance`

#### SC-18 — Zero-result queries recorded in `null_results`
**Tested by:** `test_zero_results_records_null`

#### SC-19 — Queries over 256 chars skipped with `query_too_long`
**Tested by:** `test_query_too_long_skipped`

#### SC-20 — Output JSON conforms to schema version 1.1.0
`search_results.json` has `metadata.schema_version == "1.1.0"`, all the metadata fields listed in §4.1, a `results` array, a `null_results` array, and a `skipped_queries` array.
**Tested by:** `test_output_validates_schema`

#### SC-21 — Cross-source dedupe merges same-DOI candidates
**Tested by:** `test_cross_source_dedupe_same_doi`

#### SC-22 — Cross-source dedupe merges same-title (no-DOI) candidates **only when the title is safe**
Two no-DOI candidates with identical `title_normalized` collapse to one record **only if** the normalized title contains ≥ 4 significant words (§7.6.1). Generic titles like `"introduction"` or `"discussion"` are kept as distinct records.
**Tested by:** `test_cross_source_dedupe_same_title_no_doi`, `test_short_titles_not_collapsed_by_dedup`

#### SC-23 — Cross-query dedupe merges same paper across queries
**Tested by:** `test_cross_query_dedupe_same_paper`

#### SC-24 — Merge precedence: first-seen wins for most scalars; `cited_by_count` takes the max
When two candidates merge (cross-source or cross-query), most scalar fields retain the first-seen value. `cited_by_count` is the exception: the merged record receives `max(existing.cited_by_count, incoming.cited_by_count)` (treating `None` as "no data"). This reflects the fact that citation counts grow over time and the higher value is the more recent indexing.
**Tested by:** `test_first_seen_wins_for_scalar_fields`, `test_cited_by_count_takes_max_on_merge`

#### SC-25 — All DOIs stored lowercase
**Tested by:** `test_doi_normalized_lowercase`

#### SC-26 — `dry_run=True` writes no files and calls no adapters
**Tested by:** `test_dry_run_no_writes_no_network`

#### SC-27 — Mock mode candidate count is deterministic across runs
Two mock-mode runs with identical input and identical fixture files produce identical `candidates_after_cross_query_dedupe` counts and identical `candidate_id` values for the same logical papers. (Wall-clock timestamps — `discovered_at`, `queried_at`, `generated_at` — are excluded from this guarantee; see §3.2.)
**Tested by:** `test_mock_mode_deterministic`

#### SC-28 — Smoke run against real Task 2 input completes without exception
**Tested by:** `test_smoke_run_real_queries_input`

#### SC-29 — `--confirm-live` is required to make live network calls
**Tested by:** `test_cli_refuses_live_without_confirm_flag`

#### SC-30 — `source_voi_score` passes through verbatim from input query to candidate record
The `voi_score` value on each input query row appears unchanged as `source_voi_score` on every candidate record that lists that query in its `merged_from_queries`.
**Tested by:** `test_voi_score_passes_through_to_candidate`

#### SC-31 — `metadata.mock_mode` reflects adapter type accurately
Output `metadata.mock_mode` is `true` when at least one adapter in the run is a `MockAdapter` and `false` otherwise.
**Tested by:** `test_mock_mode_flag_in_metadata`

#### SC-32 — All emitted timestamps end in `Z`
Every timestamp string anywhere in `search_results.json`, `null_results.json`, or `run_log.json` matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`.
**Tested by:** `test_timestamps_end_in_z`

---

## 10. Known Limitations

These are real shortcomings, deliberately documented (not silently shipped). They will be addressed in Phase 4 or later if Phase 3 surfaces them as blockers.

### 10.1 No partial-success recovery
If the runner is killed mid-execution (SIGKILL, OOM, exception in writer code), all output files are missing and any credits already spent are not recoverable. There is no checkpoint file. Mitigation: keep `max_credits` low; budget runs as units of work.

### 10.2 Exception swallowing has no rate ceiling
The runner catches `Exception` per-adapter and continues. A single broken adapter could log 10 errors to stderr without halting the run. There is no `max_consecutive_errors` cutoff. Mitigation: monitor `per_source_stats[name].errors` after the run.

### 10.3 `first_author_surname` is anglocentric
The extraction takes the last whitespace-separated token of the first comma-separated name. For East-Asian name order (e.g. `"Wang Wei"`), this returns the given name, not the surname. Phase 3 should not use this field as a join key without normalization.

### 10.4 `result_position` is per-source, not global
After dedup, the merged record retains the position from the first source that surfaced it. This is provenance, not a rank. See §7.7.

### 10.5 Citation count freshness
Even with §7.4's max-wins rule, `cited_by_count` is only as fresh as the most recent source query in the current run. Reruns will refresh.

---

## 11. Summary Table

| SC | Layer | Description | Test |
|----|-------|-------------|------|
| SC-1 | Adapter | engine=google_scholar | test_serpapi_engine_param |
| SC-2 | Adapter | SerpAPI: one record per organic_result | test_serpapi_parse_titles |
| SC-3 | Adapter | DOI regex matches 3 URL patterns | test_serpapi_doi_extraction, test_doi_extraction_regex_three_url_patterns, test_doi_normalized_lowercase |
| SC-4 | Adapter | PDF URL from resources[file_format=PDF] | test_serpapi_pdf_extraction |
| SC-5 | Adapter | Retry on rate-limit, sleep 30 s | test_serpapi_retry_on_rate_limit |
| SC-6 | Adapter | No retry on non-transient | test_serpapi_no_retry_on_400 |
| SC-7 | Adapter | Missing key → EnvironmentError | test_serpapi_missing_key_raises |
| SC-8 | Adapter | scholarly ≥5 s rate limit | test_scholarly_rate_limit_sleep |
| SC-9 | Adapter | Block → RuntimeError | test_scholarly_block_raises_runtime |
| SC-10 | Adapter | scholarly fields map to CandidateRecord | test_scholarly_parse_fixture |
| SC-11 | Adapter | paperscraper venue rule | test_paperscraper_parse_fixture, test_paperscraper_venue_defaults_to_arxiv |
| SC-12 | Adapter | MockAdapter fixture lookup | test_mock_adapter_reads_fixture |
| SC-13 | Adapter | Credit costs (1/0/0) | test_credit_cost_per_call |
| SC-14 | Runner | Once per query per adapter | test_every_query_processed_once_per_source |
| SC-15 | Runner | credits_used counts attempts (even on exception) | test_credits_equal_serpapi_calls, test_credit_counted_even_on_adapter_exception |
| SC-16 | Runner | Credit cap halts overflow | test_max_credits_skips_overflow |
| SC-17 | Runner | run_id forwarded to adapters | test_every_record_has_run_provenance |
| SC-18 | Runner | Zero results → null_results | test_zero_results_records_null |
| SC-19 | Runner | >256 chars → query_too_long | test_query_too_long_skipped |
| SC-20 | Runner | Output schema 1.1.0 | test_output_validates_schema |
| SC-21 | Runner | Cross-source dedupe by DOI | test_cross_source_dedupe_same_doi |
| SC-22 | Runner | Cross-source dedupe by title (≥ 4 sig words) | test_cross_source_dedupe_same_title_no_doi, test_short_titles_not_collapsed_by_dedup |
| SC-23 | Runner | Cross-query dedupe | test_cross_query_dedupe_same_paper |
| SC-24 | Runner | First-seen wins; cited_by_count = max | test_first_seen_wins_for_scalar_fields, test_cited_by_count_takes_max_on_merge |
| SC-25 | Runner | DOIs lowercase | test_doi_normalized_lowercase |
| SC-26 | Runner | dry_run → no files, no calls | test_dry_run_no_writes_no_network |
| SC-27 | Runner | Mock mode count deterministic | test_mock_mode_deterministic |
| SC-28 | Runner | Smoke run real input | test_smoke_run_real_queries_input |
| SC-29 | CLI | `--confirm-live` gate | test_cli_refuses_live_without_confirm_flag |
| SC-30 | Runner | voi_score passthrough | test_voi_score_passes_through_to_candidate |
| SC-31 | Runner | mock_mode flag accurate | test_mock_mode_flag_in_metadata |
| SC-32 | Runner | Timestamps end in Z | test_timestamps_end_in_z |

---

## Change Log

- **1.2.0 (2026-05-28)** — Added §3.1 ordering & determinism, §3.2 idempotency, §10 Known Limitations. Added NOT NULL / NULLABLE annotations to every output field (§4). Pinned timestamp format to `YYYY-MM-DDTHH:MM:SSZ` (new I-7, SC-32). Added pessimistic credit accounting (§5, SC-15 rewritten). Tightened title-only dedup with §7.6.1 safety check (SC-22, SC-30). Changed `cited_by_count` merge to max-wins (§7.4, SC-24). Fixed false invariant I-4 (now correctly says "successful calls only"). Fixed invariant I-5 (acknowledges mixed-state queries). Added SC-30 (voi_score passthrough), SC-31 (mock_mode flag), SC-32 (timestamp format). Linked to machine-readable [`schema/search_results.schema.json`](schema/search_results.schema.json). Bumped output JSON schema version 1.0.0 → 1.1.0.
- **1.1.0 (2026-05-28)** — Added §1 System Summary, §2 Inputs, §3 Processing, §4 Outputs, §5 Credit Policy, §6 Non-Goals, §7 Definitions, §8 Invariants. Rewrote SC-2/SC-10/SC-11 to describe behaviors. Broadened SC-3. De-leaked SC-9. Added SC-24 (first-seen wins) and SC-29 (`--confirm-live`). Versioned.
- **1.0.0 (initial)** — Flat list of SC-1 through SC-28; no inputs/processing/outputs/policy sections.
