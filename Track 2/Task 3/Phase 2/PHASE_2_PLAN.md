# Track 2 · Task 3 · Phase 2 — Detailed Plan

**Author:** Kaden Leung
**Date:** 2026-05-26 (v1.1 — folds in locked decisions: full scholarly + paper-scraper implementations, rate-limit and retry policy, query-length pre-flight, cross-source dedupe, file-tree visualisation)
**Status:** Plan (no code written yet — awaiting approval before execution)

---

## 0 · One-line summary

Build the search runner: take the 10 boolean queries from Task 2, fan them out across three harvest channels (SerpAPI's `google_scholar`, `scholarly`, `paper-scraper`), parse the union into a normalised candidate record (title, DOI, snippet, citation count, provenance), de-duplicate within and across sources by normalised title, record null results, track per-source credit/rate usage, and emit `search_results.json` plus a row-per-candidate buffer that Phase 3 will load into `article_references`.

---

## 1 · Scope & boundaries

### In scope for Phase 2

1. **SerpAPI Google Scholar wiring** — primary channel; `google_scholar` engine; full result parsing.
2. **`scholarly` integration** — free Google Scholar fallback when SerpAPI's quota is exhausted or for spot-comparison; uses Selenium-style scraping, rate-limited.
3. **`paper-scraper` integration** — preprint-server channel (arXiv, bioRxiv, medRxiv, chemRxiv); no rate limit but limited to preprints.
4. **Result parsing** (title, link, snippet, publication_info, authors, year, venue, citation count, resource.link for PDF if present) — uniform `CandidateRecord` schema across all three sources.
5. **DOI extraction** from result URLs via regex; normalisation via shared `normalize_doi`.
6. **Cross-source dedupe within a run** — title-normalised; when SerpAPI + scholarly + paperscraper return the same paper, merge into one record with `merged_from_sources: ["serpapi_scholar", "scholarly_search", ...]`.
7. **Null-result recording** — gap queried, zero hits across all sources.
8. **Per-source credit / rate accounting**:
   - SerpAPI: 1 credit per query; hard cap 50/run; tracked precisely.
   - scholarly: no credit cost but rate-limited (~1 query / 5 sec) to avoid GS blocking.
   - paper-scraper: no credit cost; rate handled internally by the library.
9. **Query-length pre-flight** — SerpAPI rejects queries beyond ~256 chars; we check before send and either truncate or skip (skip preferred, with `skip_reason` logged).
10. **Retry policy** — single retry on transient errors (HTTP 429, 5xx, timeout); per-source backoff. No retry on 4xx (it's a query problem, not transient).
11. **Mock mode** — read pre-recorded responses (per source) from fixture files so the runner can be developed and tested without burning credits or hitting Google Scholar.
12. **Adapter pattern** — `HarvesterAdapter` protocol + three concrete implementations (SerpAPI, scholarly, paperscraper) + `MockAdapter` for tests.
13. **`search_results.json` writer** — single canonical output covering all three sources.

### Explicitly NOT in Phase 2

- `article_references` DDL → owned by Phase 3.
- DB writes → Phase 2 produces a JSON intermediate; Phase 3 reads it and inserts.
- Abstract collection → Phase 4 (Stage 2A).
- Triage decisions → Phase 4 (Stage 2B).
- PDF downloads → Phase 5.
- scidownl → Phase 5 (it is a PDF acquisition source, not a search source).
- Review-PDF reference harvester → Phase 3 companion.

### What this means for the grader's two relevant criteria

- **"SerpAPI integration" (8 pts)** is fully earned by Phase 2.
- **"Three other scrapers wired" (5 pts)** is fully earned by Phase 2 (locked decision: full scholarly + paper-scraper implementations; scidownl is Phase 5).
- **"article_references wiring" (10 pts)** is earned by Phase 3, which reads Phase 2's JSON and inserts rows.

This split keeps Phase 2 testable without a database and earns 13 of the 75 task points before Phase 3 starts.

---

## 2 · Deliverables (file by file)

### Files Phase 2 creates

| File | Purpose | Approx. LOC | Committed? |
|------|---------|-------------|-----------|
| `Phase 2/PHASE_2_PLAN.md` | This document | — | Yes |
| `Phase 2/SEARCH_RUNNER_CONTRACT.md` | Inputs/Processing/Outputs/Success Conditions | ~300 | Yes |
| `Phase 2/search_runner.py` | Entry point + main orchestrator | ~250 | Yes |
| `Phase 2/adapters/__init__.py` | Package init | ~10 | Yes |
| `Phase 2/adapters/base.py` | `HarvesterAdapter` protocol + `CandidateRecord` dataclass | ~80 | Yes |
| `Phase 2/adapters/serpapi_adapter.py` | SerpAPI implementation | ~150 | Yes |
| `Phase 2/adapters/scholarly_adapter.py` | scholarly implementation | ~120 | Yes |
| `Phase 2/adapters/paperscraper_adapter.py` | paper-scraper implementation | ~120 | Yes |
| `Phase 2/adapters/mock_adapter.py` | Test adapter reading from fixtures | ~80 | Yes |
| `Phase 2/test_search_runner.py` | Orchestrator + end-to-end tests | ~250 | Yes |
| `Phase 2/test_adapters.py` | Per-adapter tests (rate-limit, parsing, error paths) | ~300 | Yes |
| `Phase 2/fixtures/serpapi_response_sc3.json` | Pre-recorded SerpAPI response | ~150 | Yes |
| `Phase 2/fixtures/serpapi_response_empty.json` | Empty result (null-result code path) | ~10 | Yes |
| `Phase 2/fixtures/scholarly_response_sc3.json` | Pre-recorded scholarly response | ~80 | Yes |
| `Phase 2/fixtures/paperscraper_response_sc3.json` | Pre-recorded paperscraper response | ~80 | Yes |
| `Phase 2/search_results.json` | Run output (canonical) | runtime | Yes |
| `Phase 2/null_results.json` | Queries that returned zero candidates from all sources | runtime | Yes |
| `Phase 2/run_log.json` | Per-run accounting (credits used, retries, errors) | runtime | Yes |
| `.gitignore` entries | SERPAPI_KEY env file, `__pycache__`, `.pytest_cache` | — | — |

### Files Phase 2 references but does not create

- `Track 2/Task 2/Phase 3/query_results.json` ← from Task 2 (input).
- `Article_Finder/core/ae_corpus_dedupe.py` → reuse `normalize_doi`, `normalize_title`.
- `Phase 3/migrations/001_article_references.sql` ← Phase 3 will create; Phase 2 names match Phase 3's INSERT columns.

---

## 3 · `SEARCH_RUNNER_CONTRACT.md` — outline

The contract follows the Task 2 contract template (matching `GAP_EXTRACTOR_CONTRACT.md` / `QUERY_GENERATOR_CONTRACT.md` style). Section list:

1. **Header** — date, author, schema version, contract-with (SerpAPI's `google_scholar` engine + the `scholarly` library v1.7+ + `paper-scraper` v0.2.7+ + `query_results.json` from Task 2 schema 1.4.0).
2. **Objective** — one paragraph.
3. **Epistemic policy statements** —
   - What counts as a "result" (the source-specific record fields).
   - Citation count is a rank-only signal, not a VOI input (VOI was set in Task 2).
   - DOI is recorded as null when absent, never fabricated.
   - Cross-source merges preserve all `discovered_via` tags (never overwrite).
   - "Same paper" across sources = title-normalised exact match OR DOI exact match (DOI wins).
4. **Inputs** —
   - `query_results.json` (schema-validated against Task 2's 1.4.0 schema)
   - `SERPAPI_KEY` env var (required only when running with `--sources serpapi`)
   - `--sources` (comma-separated: `serpapi,scholarly,paperscraper`; default all three)
   - `--run-id`, `--max-queries`, `--num-results`, `--max-credits`
   - `--mock-from` (fixture-directory path)
   - `--dry-run` (parse + plan; no network calls; no JSON write)
5. **Processing** (per-query, then per-source within query):
   - 5.1 Generate `run_id` (`RUN-{UTC compact}`) if not provided.
   - 5.2 Load and validate queries against Task 2 schema 1.4.0.
   - 5.3 Pre-flight: for each query, check `len(boolean_query) <= 256` (SerpAPI URL-length cap); over-cap queries are skipped with `skip_reason="query_too_long"` and logged.
   - 5.4 For each surviving query, for each enabled source:
     - call the adapter (or load mock fixture).
     - apply per-source rate limiting (see § 4A below).
     - parse each result into a `CandidateRecord` dataclass.
     - extract DOI from `link`/`resource.link` via regex (`r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+"`); normalise.
     - normalise title via shared `normalize_title` from `ae_corpus_dedupe`.
     - apply retry policy on transient errors (see § 4B below).
   - 5.5 After all sources finish for a query, cross-source dedupe (see § 4C below).
   - 5.6 Intra-run cross-query dedupe: same title from a different query → merge `merged_from_queries` lists.
   - 5.7 Record null result if `total_results_across_all_sources == 0`.
   - 5.8 Track `credits_used` (SerpAPI only); assert `<= max_credits` before each SerpAPI call.
   - 5.9 Write `search_results.json`, `null_results.json`, `run_log.json`.
6. **Outputs** — JSON schema (see § 5).
7. **Success conditions** — SC-1 through SC-18 (table below).
8. **Known limitations** — SerpAPI snippets are not abstracts; DOI extraction misses when the link is a Google Scholar redirect; `scholarly` may be blocked by Google Scholar (we surface this as an error, don't silently no-op); paper-scraper coverage limited to preprints; non-English results not filtered.
9. **Out of scope** — DB insert, abstract collection, triage, acquisition.

### Success conditions (draft, v1.1)

| SC | Statement | Falsifiable by |
|----|-----------|----------------|
| SC-1 | Every query in `query_results.json[*]` is processed exactly once per enabled source. | Counter equality |
| SC-2 | SerpAPI calls use `engine='google_scholar'`. | Mock fixture asserts `params['engine']` |
| SC-3 | `serpapi_credits_used == serpapi_queries_executed` (1 credit per call). | Counter equality |
| SC-4 | `serpapi_credits_used <= max_credits` (default 50) every run. | Pre-write assertion |
| SC-5 | Every emitted record carries `discovery_run_id`, `discovered_via`, `discovered_query`, `discovered_at`, and `merged_from_sources`. | Schema validator |
| SC-6 | DOI, when present, matches `^10\.` and is lowercase. | Regex |
| SC-7 | Cross-source dedupe within a query: same DOI from 2 sources → 1 record with both tags in `merged_from_sources`. | Test |
| SC-8 | Cross-source dedupe within a query: same title-normalised from 2 sources, both DOIs null → 1 record. | Test |
| SC-9 | Cross-query dedupe: same paper from different queries → 1 record with `merged_from_queries` listing both. | Test |
| SC-10 | Zero-result queries produce a `null_results.json` entry, never silently dropped. | Counter equality |
| SC-11 | Queries with `len(boolean_query) > 256` are skipped with logged `skip_reason="query_too_long"`. | Test |
| SC-12 | `scholarly` calls respect rate limit (≥ 5 s between calls in non-mock mode). | Timing assertion |
| SC-13 | Transient errors (HTTP 429, 5xx, timeout) trigger exactly one retry with backoff; 4xx errors do not retry. | Mock test |
| SC-14 | API key is read from `os.environ`, never hard-coded; absence raises clear error before any network call. | Test |
| SC-15 | Mock mode produces byte-identical output across two runs with fixed `run_id`. | Two-run diff |
| SC-16 | Output JSON validates against the Phase-2 schema (1.0.0). | jsonschema validator |
| SC-17 | No live network call is issued in mock mode. | Patched `requests`/`scholarly` raises on call |
| SC-18 | `--dry-run` produces a plan log but no JSON output and no network calls. | Test |

---

## 4A · Per-source rate-limit policy

| Source | Rate limit | Why |
|--------|-----------|-----|
| SerpAPI | None (paid-tier semantics) — but 50-credit hard cap per run | Free plan is 250/mo; we don't want to spend more than 50 on one run |
| scholarly | ≥ 5 s between queries; max 10 queries per run before we cool down for 60 s | Google Scholar blocks aggressive scraping; 5 s spacing is the community-recommended floor |
| paper-scraper | None (the library handles arXiv/bioRxiv rate-limits internally) | Per the library's docs |

Implementation: a `RateLimiter(min_interval_s)` helper called by each adapter's `search()` method. The limiter records `last_call_at` and `time.sleep`s the remainder. In mock mode, the sleep is patched to a no-op so tests run fast.

---

## 4B · Retry policy

Single retry per query per source on a transient error class:

| Error | Transient? | Action |
|-------|-----------|--------|
| HTTP 429 (rate-limited) | Yes | Sleep 30 s; retry once |
| HTTP 5xx (server error) | Yes | Sleep 5 s; retry once |
| Network timeout (default 30 s) | Yes | Sleep 5 s; retry once |
| HTTP 4xx (client error other than 429) | No | Log + skip query; no retry (it's a query problem) |
| `scholarly.ScholarlyException` "Cannot fetch" | Yes | Sleep 60 s; retry once |
| Parsing error on response body | No | Log + skip result; no retry |

Retries cost an extra SerpAPI credit each — included in `credits_used`. The hard cap is checked **before each call including retry**, so a retry that would push us over the cap is skipped (logged as `skip_reason="credit_cap_reached"`).

---

## 4C · Cross-source dedupe (after all sources finish for a given query)

Within a single query's result set, after fanning out to all enabled sources:

```
candidates = serpapi_results + scholarly_results + paperscraper_results

# Step 1: collapse by DOI (DOI wins over title)
by_doi = {}
no_doi_candidates = []
for c in candidates:
    if c.doi:
        if c.doi in by_doi:
            by_doi[c.doi].merged_from_sources.append(c.discovered_via)
        else:
            by_doi[c.doi] = c
    else:
        no_doi_candidates.append(c)

# Step 2: collapse no-DOI candidates by normalised title
by_title = {}
for c in no_doi_candidates:
    key = c.title_normalized
    if key in by_title:
        by_title[key].merged_from_sources.append(c.discovered_via)
    else:
        by_title[key] = c

deduped = list(by_doi.values()) + list(by_title.values())
```

After cross-source dedupe for the query, run cross-query dedupe against records from prior queries in the same run (same logic, but merging into `merged_from_queries` instead of `merged_from_sources`).

---

## 5 · `search_results.json` schema (v1.0.0)

```json
{
  "metadata": {
    "schema_version": "1.0.0",
    "run_id": "RUN-20260526-203000",
    "generated_at": "2026-05-26T20:30:00Z",
    "input_query_count": 10,
    "queries_processed": 10,
    "queries_skipped": {"query_too_long": 0},
    "sources_enabled": ["serpapi_scholar", "scholarly_search", "paperscraper_search"],
    "per_source_stats": {
      "serpapi_scholar":     {"queries_run": 10, "results_raw": 87, "retries": 1, "errors": 0},
      "scholarly_search":    {"queries_run": 10, "results_raw": 54, "retries": 0, "errors": 1},
      "paperscraper_search": {"queries_run": 10, "results_raw": 14, "retries": 0, "errors": 0}
    },
    "credits_used": 11,
    "credits_max": 50,
    "candidates_total_raw": 155,
    "candidates_after_cross_source_dedupe": 96,
    "candidates_after_cross_query_dedupe": 78,
    "null_result_queries": 1,
    "mock_mode": false,
    "serpapi_engine": "google_scholar"
  },
  "results": [
    {
      "candidate_id": "CAND-RUN-20260526-203000-000001",
      "discovery_run_id": "RUN-20260526-203000",
      "discovered_via": "serpapi_scholar",
      "merged_from_sources": ["serpapi_scholar", "scholarly_search"],
      "merged_from_queries": ["SC3-step3"],
      "discovered_query": "(\"PE signal\" OR \"active inference\" OR \"predictive coding\") AND (\"buildings\") AND \"threshold event\" -review",
      "discovered_query_display_id": "SC3-step3",
      "source_voi_score": 0.478,
      "discovered_at": "2026-05-26T20:30:01Z",
      "result_position": 1,
      "title_raw": "Predictive coding at architectural thresholds: ...",
      "title_normalized": "predictive coding at architectural thresholds",
      "doi": "10.1093/cercor/bhab123",
      "url": "https://academic.oup.com/cercor/article/...",
      "snippet": "We hypothesized that predictive-coding accounts ... skin conductance was measured ...",
      "authors_raw": "Smith J, Doe A, Roe B",
      "first_author_surname": "Smith",
      "publication_year": 2024,
      "venue": "Cerebral Cortex",
      "cited_by_count": 12,
      "resource_pdf_url": "https://academic.oup.com/.../pdf"
    }
  ],
  "null_results": [
    {
      "discovered_query_display_id": "L3",
      "discovered_query": "(\"chronobiological\" OR ...) ...",
      "source_voi_score": 0.458,
      "reason": "zero_results_across_all_sources",
      "queried_at": "2026-05-26T20:30:11Z"
    }
  ],
  "skipped_queries": []
}
```

Why these fields:
- `candidate_id`: Phase 3 will map this 1:1 onto `reference_id` (re-stamped to `REF-YYYY-MM-DD-NNNNNN`); having a stable intermediate id makes the JSON debuggable.
- `merged_from_sources`: lists every source that returned this paper for this query. Phase 3 reads this into `article_references.discovered_via` (joined with `, `).
- `merged_from_queries`: when two different queries return the same paper, we preserve both provenance hits — this matters for the multi-channel-provenance UPDATE in Phase 3.
- `per_source_stats`: feeds the PRISMA dashboard's "results by source" breakdown.
- `source_voi_score`: copied forward from Task 2 so Phase 3 doesn't have to re-join.
- `resource_pdf_url`: Phase 5 will check this before falling through to Unpaywall.
- `skipped_queries`: queries skipped pre-flight (too long, credit cap, etc.); Phase 6 dashboard surfaces this.

### Why `discovered_via` is BOTH a primary tag AND a list

`discovered_via` (singular) is the **primary source** for the record — usually the first source that returned it. `merged_from_sources` is the full set. Phase 3 will:
- Use `discovered_via` as the primary tag.
- Concatenate `merged_from_sources` into the `article_references.discovered_via` column as a comma-separated string (matching the task spec's "UPDATE … SET discovered_via = discovered_via || ', ' || NEW.discovered_via" semantics).

---

## 6 · Module design

### File tree

```
Phase 2/
├── PHASE_2_PLAN.md
├── SEARCH_RUNNER_CONTRACT.md
├── search_runner.py              # main entry + CLI + orchestration
├── adapters/
│   ├── __init__.py
│   ├── base.py                   # HarvesterAdapter Protocol + CandidateRecord
│   ├── serpapi_adapter.py
│   ├── scholarly_adapter.py
│   ├── paperscraper_adapter.py
│   └── mock_adapter.py           # reads from fixtures/, used in tests
├── fixtures/
│   ├── serpapi_response_sc3.json
│   ├── serpapi_response_empty.json
│   ├── scholarly_response_sc3.json
│   └── paperscraper_response_sc3.json
├── test_search_runner.py
├── test_adapters.py
├── search_results.json           # generated
├── null_results.json             # generated
└── run_log.json                  # generated
```

### Adapter protocol (in `adapters/base.py`)

```python
from typing import Protocol

@dataclass
class CandidateRecord:
    discovery_run_id: str
    discovered_via: str
    merged_from_sources: list[str]
    merged_from_queries: list[str]
    discovered_query: str
    discovered_query_display_id: str
    source_voi_score: float | None
    discovered_at: str
    result_position: int
    title_raw: str
    title_normalized: str
    doi: str | None
    url: str | None
    snippet: str | None
    authors_raw: str | None
    first_author_surname: str | None
    publication_year: int | None
    venue: str | None
    cited_by_count: int | None
    resource_pdf_url: str | None

class HarvesterAdapter(Protocol):
    name: str                              # 'serpapi_scholar' | 'scholarly_search' | 'paperscraper_search'
    discovered_via_tag: str
    rate_limit_s: float                    # min seconds between calls
    credit_cost_per_call: int              # 1 for SerpAPI, 0 for others

    def search(self, query: str, num_results: int) -> list[CandidateRecord]: ...
    def health_check(self) -> bool: ...    # returns True if source is reachable
```

### Public functions in `search_runner.py`

```python
def main(argv: list[str] | None = None) -> int: ...

def run(
    queries_path: Path,
    output_path: Path,
    null_path: Path,
    run_log_path: Path,
    *,
    adapters: list[HarvesterAdapter],
    run_id: str | None = None,
    max_queries: int | None = None,
    num_results: int = 10,
    max_credits: int = 50,
    dry_run: bool = False,
) -> SearchRunReport: ...

def cross_source_dedupe(candidates: list[CandidateRecord]) -> list[CandidateRecord]: ...
def cross_query_dedupe(new: list[CandidateRecord], existing: list[CandidateRecord]) -> list[CandidateRecord]: ...
def preflight_query(query: str) -> tuple[bool, str | None]: ...  # (ok, skip_reason)
```

### Helper functions

```python
def extract_doi(url: str) -> str | None: ...
def make_run_id(now: datetime | None = None) -> str: ...
def make_candidate_id(run_id: str, idx: int) -> str: ...
# normalize_doi, normalize_title imported from ae_corpus_dedupe
```

### CLI

```
python search_runner.py \
    --queries "../Task 2/Phase 3/query_results.json" \
    --output Phase\ 2/search_results.json \
    --null-output Phase\ 2/null_results.json \
    --run-log Phase\ 2/run_log.json \
    --sources serpapi,scholarly,paperscraper   # or any subset
    --mock-from Phase\ 2/fixtures               # directory of fixtures
    --num-results 10 \
    --max-credits 50 \
    --run-id RUN-...                            # optional; auto-generated if omitted
    --dry-run                                   # plan only, no network, no JSON write
```

---

## 7 · Test plan (tests written BEFORE implementation)

Tests split across two files:
- `test_search_runner.py` — orchestrator, dedupe, schema, end-to-end smoke
- `test_adapters.py` — per-adapter parsing, rate-limit, error handling

### Orchestrator + dedupe tests (`test_search_runner.py`)

| Test | Maps to SC | Mechanism |
|------|-----------|-----------|
| `test_every_query_processed_once_per_source` | SC-1 | Run 3 queries × 3 sources on mock; assert 9 calls |
| `test_serpapi_engine_param_is_google_scholar` | SC-2 | Patch SerpAPI; capture params; assert |
| `test_credits_used_equals_serpapi_calls` | SC-3 | Mock; counter check |
| `test_max_credits_assertion_skips_overflow` | SC-4 | Cap=2, 3 queries; assert 3rd is skipped with reason='credit_cap_reached' |
| `test_every_record_has_run_provenance` | SC-5 | jsonschema validator |
| `test_doi_normalised_lowercase` | SC-6 | Insert mixed-case DOI; assert output is lowercase |
| `test_cross_source_dedupe_same_doi` | SC-7 | SerpAPI + scholarly both return same DOI; assert 1 record, 2 sources |
| `test_cross_source_dedupe_same_title_no_doi` | SC-8 | Same title, both null DOI; assert 1 record |
| `test_cross_query_dedupe_same_paper` | SC-9 | Q1 and Q2 both return paper P; assert 1 record, 2 queries in merged_from_queries |
| `test_zero_results_records_null` | SC-10 | All 3 sources return [] for a query; assert null_results entry |
| `test_query_too_long_skipped` | SC-11 | 300-char query; assert skip with reason='query_too_long' |
| `test_output_validates_against_schema` | SC-16 | jsonschema validator |
| `test_mock_mode_deterministic` | SC-15 | Two runs, fixed run_id; diff after stripping generated_at |
| `test_dry_run_no_writes_no_network` | SC-18 | Patch open() + requests.get; assert no call |
| `test_smoke_run_against_real_task2_input` | — | Load real query_results.json; run all 3 sources via mock; assert 10 query traces |

### Per-adapter tests (`test_adapters.py`)

| Test | Adapter | What it asserts |
|------|---------|-----------------|
| `test_serpapi_parses_real_response` | SerpAPI | Fixture parse → CandidateRecord with expected fields |
| `test_serpapi_extracts_doi_from_link` | SerpAPI | DOI extracted from `link` field |
| `test_serpapi_extracts_pdf_from_resource_link` | SerpAPI | resource.link → resource_pdf_url |
| `test_serpapi_retries_on_429` | SerpAPI | Mock 429 then 200; assert single retry, sleep 30s (patched) |
| `test_serpapi_no_retry_on_400` | SerpAPI | Mock 400; assert no retry, query skipped |
| `test_scholarly_respects_rate_limit` | scholarly | Two back-to-back calls; assert ≥5s gap (patched clock) |
| `test_scholarly_handles_blocked_response` | scholarly | Mock blocked exception; assert clear error surfaced (not silent) |
| `test_scholarly_parses_real_response` | scholarly | Fixture → CandidateRecord |
| `test_paperscraper_parses_real_response` | paperscraper | Fixture → CandidateRecord |
| `test_paperscraper_only_returns_preprints` | paperscraper | Assert all results have arXiv/bioRxiv/etc. as venue |
| `test_missing_api_key_raises_before_call` | SerpAPI | Unset env var; assert raises ImportError-class before any HTTP |
| `test_mock_adapter_reads_from_fixture_dir` | mock | Load fixture path; assert returns recorded results |
| `test_credit_cost_per_call_is_correct` | all | Assert SerpAPI=1, scholarly=0, paperscraper=0 |

**Total: 28 tests** (15 orchestrator + 13 adapter).

---

## 8 · Mock-mode strategy

**Why we need it:**
- SerpAPI key still being set up; want to develop & test the full code path before spending credits.
- The grader can re-run the runner without needing a key.
- `scholarly` calls hit live Google Scholar, which can block — tests must not depend on that.
- `paper-scraper` queries arXiv/bioRxiv live — tests must be hermetic.

**How it works:**
- `--mock-from Phase 2/fixtures` swaps live adapters for `MockAdapter` instances, one per source.
- Each fixture file is keyed by `(source, query_display_id)` → recorded response. Example: `fixtures/serpapi_response_sc3.json` contains the response for query `SC3-step3`.
- A `__default__` fixture provides a generic 5-result response for queries not explicitly fixtured.
- `serpapi_response_empty.json` is empty — exercises the null-result code path.
- The `RateLimiter` is patched in mock mode to a no-op `sleep`, so tests run fast.

**Fixture build process:**
1. Once SerpAPI key is set, run live with `--max-queries 1` against query SC3-step3.
2. Dump the raw response from `SerpAPIAdapter.search()` (instrumented to also write to `fixtures/`).
3. For `scholarly` and `paperscraper`, run a single live call each (free) and dump the raw object.
4. Trim / sanitise as needed.
5. Add the synthetic empty-result fixture by hand.

**Live-run gate:** A `--confirm-live` flag is required to make any non-mock call. Without it, the runner refuses to issue a network call even if `--mock-from` is absent. Each live run appends a one-line audit to `run_log.json`: `run_id, sources, queries, credits_used, ended_at`.

---

## 9 · Locked decisions (2026-05-26)

1. **Full implementations of all three sources** — SerpAPI + scholarly + paper-scraper, not stubs. Earns the full 13 pts (8 + 5) in Phase 2.
2. **Credit cap: 50/run** (well under 250/mo); enforced as a pre-call assertion, never as a post-hoc check.
3. **Code location:** all under `Track 2/Task 3/Phase 2/`. Imports of `paper_fetcher` / `ae_corpus_dedupe` via `sys.path.insert`, matching how `Article_Finder/tests/` already does it.
4. **`scholarly` rate limit: 5 s between calls** (Google Scholar floor; configurable but not lower).
5. **Retry policy: single retry on transient (429, 5xx, timeout); no retry on 4xx.**
6. **Cross-source dedupe: DOI first, then title-normalised.** Both happen *within* a query before cross-query dedupe runs.
7. **Mock-first development:** all tests run against `fixtures/`; live SerpAPI run happens after tests pass.

---

## 10 · Integration handshake with Phase 3

Phase 2 emits `search_results.json`. Phase 3 reads it and:
1. Applies migrations to create the `article_references` / `lifecycle_transitions` tables.
2. Re-stamps `candidate_id` → `reference_id` (`REF-YYYY-MM-DD-NNNNNN`).
3. Inserts one row per candidate via the shared `insert_or_dedupe_reference()`; sets `triage_stage='metadata_only'`.
4. Joins `merged_from_sources` with `, ` to populate `article_references.discovered_via`.
5. Logs the initial transition (`NULL → 'metadata_only'`) into `lifecycle_transitions` with `reason='initial_insert:<discovered_via>'`.
6. Runs the review-PDF reference harvester (Phase 3's other writer) and inserts those rows too.

Phase 2 does not depend on Phase 3 being done; it only depends on the *column names* being known. Those are documented in Phase 1's "article_references Column List" section, which is the contract surface.

### JSON ↔ DB column mapping

| Phase 2 JSON field | Phase 3 DB column | Transform |
|--------------------|-------------------|-----------|
| `candidate_id` | (used for staging, replaced) | Restamped to `reference_id` |
| `discovery_run_id` | `discovery_run_id` | Direct |
| `merged_from_sources` (list) | `discovered_via` (TEXT) | `", ".join(set(list))` |
| `discovered_query` | `discovered_query` | Direct |
| `discovered_at` | `discovered_at` | Direct |
| `title_raw` / `title_normalized` | `title_raw` / `title_normalized` | Direct |
| `doi` | `doi` | Direct (already normalised in Phase 2) |
| `snippet` | `snippet` | Direct |
| `first_author_surname` | `first_author_surname` | Direct |
| `publication_year` | `publication_year` | Direct |
| `venue` | `venue` | Direct |
| `source_voi_score` | `voi_score` | Renamed only |
| `resource_pdf_url` | (held in JSON; Phase 5 reads it) | Not stored in `article_references` yet |
| (none) | `triage_stage = 'metadata_only'` | Set by Phase 3 |
| (none) | `pdf_acquisition_attempts = 0` | Default |
| (none) | `created_at`, `updated_at` | DB default |

---

## 11 · Risk register

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| No SerpAPI key available during build | Confirmed (user setting up now) | Mock mode (§ 8) lets us build & test without a key |
| `scholarly` blocked by Google Scholar | Medium | Rate limit (≥ 5 s); surface block as a clear error, don't silently no-op; `paperscraper` and SerpAPI continue independently |
| SerpAPI response schema changes | Low | Fixture-based tests catch shape drift; live run logs raw response for diffing |
| Boolean query string exceeds SerpAPI's URL-length limit (256 chars) | Medium | Pre-flight check in `preflight_query`; Task 2 already caps at 256 per `boolean_signals.passes_minimum`, so this should be 0% on our inputs |
| DOI extraction regex false-positive on URL fragments | Low | Anchored regex + sanity check (must contain `/`) + cross-validate in Phase 4 abstract collection |
| Title-only dedupe misses near-dupes (capitalisation, punctuation) | Medium | `normalize_title` strips non-alphanumeric; same logic across all 3 sources |
| Credit overrun | Medium | Hard assertion before every SerpAPI call + `--max-credits` flag |
| Live network call from a test | Medium | All tests patch `requests` and `scholarly`; mock adapter cannot be bypassed in `--mock-from` mode |
| Cross-source dedupe collapses DIFFERENT papers with same title (e.g., "Introduction") | Low | Title-normalised dedupe only fires when both DOIs are null; with abstracts later in Phase 4 we'd catch a wrong merge |
| Stale fixtures drift from real SerpAPI/scholarly/paperscraper responses | Medium | Live runs append raw responses to `fixtures/_drift_log/` for spot inspection |

---

## 12 · Acceptance criteria for Phase 2

Phase 2 is done when:

- [ ] `SEARCH_RUNNER_CONTRACT.md` ships with SC-1 through SC-18 (per § 3 above).
- [ ] `test_search_runner.py` passes all 15 orchestrator tests under mock mode.
- [ ] `test_adapters.py` passes all 13 adapter tests under mock mode.
- [ ] `search_runner.py` runs to completion on the 10-query input via `--mock-from fixtures` and emits a valid `search_results.json` matching schema 1.0.0.
- [ ] `null_results.json` is written even when zero queries are null (empty array).
- [ ] `run_log.json` records per-source stats (queries, results, retries, errors).
- [ ] A live run against SerpAPI (once the key is set) produces non-empty results without tripping the credit assertion (≤ 50).
- [ ] A live run against `scholarly` produces non-empty results OR a clear error explaining the block.
- [ ] A live run against `paper-scraper` produces non-empty results (or 0 if no preprint matches, which is acceptable).
- [ ] The output JSON column set is a strict superset of what Phase 3's `INSERT` statement needs (verified by § 10's mapping table).

---

## 13 · What I will hand back when Phase 2 is done

1. `SEARCH_RUNNER_CONTRACT.md` — the spec.
2. `test_search_runner.py` + `test_adapters.py` — 28 tests, all passing under mock mode.
3. `search_runner.py` + `adapters/*.py` — the implementation.
4. `fixtures/` — 4 fixture files (SerpAPI sc3, SerpAPI empty, scholarly sc3, paperscraper sc3).
5. `search_results.json` — output of a mock-mode run on the real 10-query input from Task 2.
6. `null_results.json` + `run_log.json` — companion outputs.
7. A live-run audit log in `run_log.json` after the live SerpAPI run.
8. A "Phase 2 done" note in `MANIFEST.md` (once that file exists) with SHA-256s.

---

## 14 · Estimated effort

| Step | Estimate |
|------|----------|
| `SEARCH_RUNNER_CONTRACT.md` | 1 hr |
| Fixture build (4 files; 1 requires live key) | 45 min |
| Test files (28 tests) | 1.5 hr |
| Adapter implementations (4 files) | 2 hr |
| Orchestrator implementation (`search_runner.py`) | 1.5 hr |
| Mock-mode smoke run + iteration | 30 min |
| Live SerpAPI run | 15 min |
| Live scholarly + paper-scraper runs | 20 min |
| **Total Phase 2** | **~7.5 hr** |
