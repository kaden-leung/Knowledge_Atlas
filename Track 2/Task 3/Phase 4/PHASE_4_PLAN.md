# Track 2 · Task 3 · Phase 4 — Detailed Plan

**Author:** Kaden Leung
**Date:** 2026-05-27 (v1.0)
**Status:** Plan (no code written yet — awaiting approval before execution)
**Depends on:** Phase 3 (reads `task3_pipeline_lifecycle.db` populated by `db_loader.py` and `reference_harvester.py`)

---

## 0 · One-line summary

For every `metadata_only` row in `article_references`, collect an abstract via a 4-source fallback chain (Semantic Scholar → CrossRef → PubMed → OpenAlex), then run a 3-stage triage to produce a `triage_decision` of ACCEPT / EDGE_CASE / REJECT / MISSING_ABSTRACT, storing classifier confidence and query-derived VOI score.

---

## 1 · Scope & boundaries

### In scope for Phase 4

1. `openalex_client.py` — lightweight 4th abstract source using only `urllib` (no new packages).
2. `abstract_collector.py` — 4-source fallback chain: Semantic Scholar → CrossRef → PubMed → OpenAlex → MISSING_ABSTRACT. Imports real clients from `Article_Eater/src/services/paper_fetcher.py` via `sys.path.insert`.
3. `triage_engine.py` — 3-stage triage orchestrator:
   - Stage 1: metadata-only screen (skip duplicates, reject empty titles)
   - Stage 2A: abstract collection via `abstract_collector.py`
   - Stage 2B: triage decision using `HierarchicalClassifier.classify_paper()` from `Article_Finder/triage/classifier.py`
4. VOI score derivation from `query_results.json` keyed by `discovered_query`.
5. DB updates to `article_references` (abstract, triage fields) + `lifecycle_transitions` rows per stage.
6. Mock-mode (fixture abstracts, no network) and dry-run mode (in-memory SQLite).
7. `triage_results.json` output artifact.
8. Tests: 35 tests across 2 test files.

### Explicitly NOT in Phase 4

- PDF acquisition (`v_acquisition_queue` is read by Phase 5, not here).
- Fetching full-text (only abstract).
- Changing the DB schema (Phase 3 migrations are final).
- PRISMA dashboard (Phase 6).
- Any write to the Article Eater KB (Phase 7).

---

## 2 · File tree

```
Track 2/Task 3/Phase 4/
├── PHASE_4_PLAN.md              # this file
├── openalex_client.py           # lightweight OpenAlex abstract fetcher
├── abstract_collector.py        # 4-source fallback chain
├── triage_engine.py             # 3-stage triage orchestrator
├── fixtures/
│   ├── mock_s2_abstract.json         # single S2 paper response stub
│   ├── mock_crossref_abstract.json   # single CrossRef work stub
│   ├── mock_pubmed_abstract.json     # PubMed efetch XML stub
│   ├── mock_openalex_abstract.json   # OpenAlex /works item stub
│   └── triage_test_rows.json         # 10 article_references rows for tests
├── test_abstract_collector.py
├── test_triage_engine.py
└── triage_results.json          # written at runtime (not tracked in git)
```

**What is NOT in this directory (reused from other locations):**

| Symbol | Source path |
|---|---|
| `SemanticScholarClient` | `Article_Eater/src/services/paper_fetcher.py:704` |
| `CrossRefClient` | `Article_Eater/src/services/paper_fetcher.py:450` |
| `PubMedClient` | `Article_Eater/src/services/paper_fetcher.py:552` |
| `HierarchicalClassifier` | `Article_Finder/triage/classifier.py:51` |
| `normalize_doi` | `Article_Finder/core/ae_corpus_dedupe.py:38` |
| `normalize_title` | `Article_Finder/core/ae_corpus_dedupe.py:48` |
| `score_voi` | `Article_Eater/src/cmr/voi_scoring.py:58` (not called in Phase 4 — see §6) |

All imports via `sys.path.insert(0, str(Path(__file__).resolve().parents[N]))`.

---

## 3 · Module contracts

### 3A · `openalex_client.py`

OpenAlex exposes a free, unauthenticated REST API. No API key required; polite pool via `?mailto=` query parameter.

**Public interface:**

```python
class OpenAlexClient:
    BASE = "https://api.openalex.org"
    POLITE_EMAIL = "kadenleung00@gmail.com"

    def __init__(self) -> None:
        self._limiter = _RateLimiter(min_delay=0.12)   # ~8 req/s, polite pool

    def fetch_abstract_by_doi(self, doi: str) -> str | None:
        """GET /works/doi:{doi}  →  return abstract_inverted_index decoded or None."""

    def fetch_abstract_by_title_year(self, title: str, year: int | None) -> str | None:
        """GET /works?filter=title.search:{title},publication_year:{year}  →  first hit abstract or None."""

    def health_check(self) -> bool:
        """GET /works?filter=publication_year:2024&per-page=1  →  True if 200 OK."""
```

**OpenAlex abstract_inverted_index decoder:**

OpenAlex stores abstracts as inverted-index dicts `{"word": [pos, ...], ...}`. Decode by placing each word at each position and joining by space. Example:

```python
def _decode_inverted_index(d: dict[str, list[int]]) -> str:
    words: dict[int, str] = {}
    for word, positions in d.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words[i] for i in sorted(words))
```

**Rate limit:** 0.12s between calls (polite pool allows ~10 req/s; we stay under at ~8).

---

### 3B · `abstract_collector.py`

**Public interface:**

```python
@dataclass
class AbstractResult:
    abstract: str | None        # None only when status is MISSING_ABSTRACT
    source: str                 # one of: "semantic_scholar" | "crossref" | "pubmed" | "openalex" | "MISSING_ABSTRACT"
    doi_used: str | None        # normalised DOI actually sent to the source
    title_used: str | None      # title string used for title-search fallback

def collect_abstract(
    *,
    doi: str | None,
    title: str | None,
    year: int | None,
    mock: bool = False,
    mock_fixtures_dir: Path | None = None,
) -> AbstractResult:
    """
    Try sources in order: Semantic Scholar → CrossRef → PubMed → OpenAlex.
    Return the first non-empty abstract found, or MISSING_ABSTRACT if all fail.
    """
```

**Fallback chain pseudocode:**

```
function collect_abstract(doi, title, year, mock):
    if mock:
        return _load_mock_fixture(mock_fixtures_dir, doi, title)

    # Source 1: Semantic Scholar
    if doi:
        result = s2_client.fetch_by_doi(doi)
        if result.metadata and result.metadata.abstract:
            return AbstractResult(result.metadata.abstract, "semantic_scholar", doi, None)
    if title:
        s2_hits = s2_client.search(f"{title} {year or ''}", max_results=1)
        if s2_hits and s2_hits[0].abstract:
            return AbstractResult(s2_hits[0].abstract, "semantic_scholar", doi, title)

    # Source 2: CrossRef
    if doi:
        result = crossref_client.fetch(doi)
        if result.metadata and result.metadata.abstract:
            return AbstractResult(result.metadata.abstract, "crossref", doi, None)

    # Source 3: PubMed
    if doi:
        result = pubmed_client.fetch(doi)   # PubMedClient.fetch(doi) tries DOI lookup
        if result.metadata and result.metadata.abstract:
            return AbstractResult(result.metadata.abstract, "pubmed", doi, None)
    if title and year:
        result = pubmed_client.search(f"{title}[Title] {year}[PDAT]", max_results=1)
        if result and result[0].abstract:
            return AbstractResult(result[0].abstract, "pubmed", doi, title)

    # Source 4: OpenAlex
    if doi:
        abstract = openalex_client.fetch_abstract_by_doi(doi)
        if abstract:
            return AbstractResult(abstract, "openalex", doi, None)
    if title:
        abstract = openalex_client.fetch_abstract_by_title_year(title, year)
        if abstract:
            return AbstractResult(abstract, "openalex", doi, title)

    return AbstractResult(None, "MISSING_ABSTRACT", doi, title)
```

**Rate limit rules:**

| Source | Mechanism | Min delay | Notes |
|---|---|---|---|
| Semantic Scholar | `_RateLimiter` in client | 3.1s (no key), 1.1s (with key) | Inherited from existing client |
| CrossRef | `_RateLimiter` in client | 0.5s | Inherited from existing client |
| PubMed | `_RateLimiter` in client | 0.35s (no key), 0.12s (with key) | Inherited from existing client |
| OpenAlex | `_RateLimiter` in `openalex_client.py` | 0.12s | Built fresh |

**Retry policy:** one automatic retry on `urllib.error.HTTPError` with status 429 or 5xx, after a 10s sleep. No retry on 4xx (except 429). `AbstractResult` is still returned as `MISSING_ABSTRACT` if second attempt also fails.

---

### 3C · `triage_engine.py`

**Public interface:**

```python
@dataclass
class TriageRunConfig:
    db_path: Path
    query_results_json: Path            # Phase 2 query_results.json for VOI lookup
    run_id: str                         # propagated to lifecycle_transitions
    mock: bool = False
    mock_fixtures_dir: Path | None = None
    dry_run: bool = False               # in-memory SQLite, no writes to real DB

def run_triage(config: TriageRunConfig) -> dict:
    """
    Fetch all metadata_only rows from article_references.
    Run Stage 1 → Stage 2A → Stage 2B.
    Return a summary dict (also written to triage_results.json).
    """

def stage1_screen(conn, row: dict) -> str | None:
    """
    Return rejection reason string if row should be rejected, else None.
    Reasons: 'empty_title' | 'duplicate' | 'already_triaged'
    """

def stage2a_collect_abstract(conn, row: dict, config: TriageRunConfig) -> AbstractResult:
    """Collect abstract for one row; update article_references + log transition."""

def stage2b_decide(conn, row: dict, abstract_result: AbstractResult,
                   classifier, voi_map: dict) -> str:
    """Run classifier; update triage_decision/confidence/voi_score; log transition."""
```

**Classifier loading:**

```python
def _load_classifier() -> HierarchicalClassifier | None:
    """
    Import HierarchicalClassifier via sys.path.insert.
    Load centroids from Article_Finder/triage/.centroids.pkl if it exists.
    Return None (keyword-fallback) if sentence-transformers not available
    or centroids file absent.
    """

def _keyword_fallback(title: str, abstract: str | None) -> tuple[str, float]:
    """
    Keyword-based CNFA relevance check.
    ACCEPT if >=3 CNFA keywords found.  EDGE_CASE if 1-2.  REJECT if 0.
    Returns (decision, confidence) — confidence is always 0.5 for fallback.
    """
    CNFA_KEYWORDS = {
        "architecture", "spatial", "built environment", "building",
        "cognition", "cognitive", "arousal", "restoration", "attention",
        "wayfinding", "threshold", "façade", "cortisol", "stress",
        "psychophysiolog", "neural", "fMRI", "EEG", "EDA", "circadian",
    }
```

The keyword fallback ensures Phase 4 runs even without `sentence-transformers` installed in the execution environment. It is only used when the real classifier can't be loaded; it is never used in production when the centroids file is present.

---

## 4 · Triage decision mapping

| Classifier output | `triage_decision` | `triage_stage` after Stage 2B |
|---|---|---|
| `'send_to_eater'` | `ACCEPT` | `triage_complete` |
| `'review'` | `EDGE_CASE` | `triage_complete` |
| `'reject'` | `REJECT` | `triage_complete` |
| (no abstract found) | `MISSING_ABSTRACT` | `triage_complete` |
| (Stage 1: empty title) | `REJECT` | `rejected_stage1` |

**`triage_reason` values:**

| Decision path | `triage_reason` |
|---|---|
| Strong L3 match in classifier | `classifier_accept_l3:{node_id}` |
| Strong L2 match in classifier | `classifier_accept_l2:{node_id}` |
| Marginal / in-domain review | `classifier_edge_case_domain:{score:.2f}` |
| Low domain score | `classifier_reject_domain:{score:.2f}` |
| No abstract after all 4 sources | `abstract_missing_all_sources` |
| Keyword fallback (no centroids) | `keyword_fallback:accept|edge_case|reject` |
| Empty title | `insufficient_metadata:title_empty` |
| Row already triaged | `already_triaged` (logged as no-op) |

---

## 5 · Stage transitions logged to `lifecycle_transitions`

Every stage produces one row in `lifecycle_transitions`. `created_by` column tracks which module wrote it.

| Stage | `from_stage` | `to_stage` | `reason` | `created_by` |
|---|---|---|---|---|
| Stage 1 pass | `metadata_only` | `stage1_screened` | `metadata_screen_passed` | `triage_engine` |
| Stage 1 reject (empty title) | `metadata_only` | `rejected_stage1` | `insufficient_metadata:title_empty` | `triage_engine` |
| Stage 1 skip (duplicate) | `metadata_only` | `duplicate` | `already_duplicate` | `triage_engine` |
| Stage 2A success | `stage1_screened` | `abstract_collected` | `abstract_source:{source}` | `abstract_collector` |
| Stage 2A miss | `stage1_screened` | `abstract_missing` | `abstract_missing_all_sources` | `abstract_collector` |
| Stage 2B complete | `abstract_collected` | `triage_complete` | see §4 triage_reason table | `triage_engine` |
| Stage 2B (no abstract) | `abstract_missing` | `triage_complete` | `abstract_missing_all_sources` | `triage_engine` |

---

## 6 · VOI score derivation

`score_voi()` from `Article_Eater/src/cmr/voi_scoring.py` operates on extracted **findings** (Tier 3 nodes in the Bayesian network). At Phase 4, candidate papers have not been processed by the Eater — no findings have been extracted yet. Using `score_voi()` here would be a category error.

**Strategy:** derive `voi_score` from the discovering query's `voi_score` in `query_results.json`.

```python
def _build_voi_map(query_results_json: Path) -> dict[str, float]:
    """
    Returns mapping: normalised_query_text → voi_score.
    Also includes per-template_id mapping for cleaner key lookup.
    """
    data = json.loads(query_results_json.read_text())
    voi_map: dict[str, float] = {}
    for q in data.get("queries", []):
        key = str(q.get("ai_citation_query", "")).strip()
        if key:
            voi_map[key] = float(q["voi_score"])
        tid = str(q.get("template_id", "")).strip()
        if tid:
            voi_map[tid] = float(q["voi_score"])
    return voi_map
```

Lookup in `stage2b_decide`: `voi_map.get(row["discovered_query"], 0.443)`. The fallback `0.443` is the minimum observed VOI across the 10 queries.

**Note:** `voi_score` in `article_references` is marked as a Phase 4 provisional value. After the Eater processes the paper (Phase 7), the Eater may overwrite it with a findings-derived VOI.

---

## 7 · DB update contract

Phase 4 only updates existing rows — no INSERT to `article_references`. Both writers issue explicit `UPDATE ... WHERE reference_id = ?` to touch only the columns they own.

**Columns updated by `abstract_collector.py`:**

| Column | Set when |
|---|---|
| `abstract_text` | non-null abstract returned |
| `abstract_source` | always (including `MISSING_ABSTRACT`) |
| `triage_stage` | → `abstract_collected` or `abstract_missing` |
| `updated_at` | always |

**Columns updated by `triage_engine.py` (Stage 2B):**

| Column | Set when |
|---|---|
| `triage_decision` | always after Stage 2B |
| `triage_reason` | always after Stage 2B |
| `classifier_confidence` | when classifier ran (null for MISSING_ABSTRACT) |
| `voi_score` | always after Stage 2B (query-derived) |
| `triage_stage` | → `triage_complete` or `rejected_stage1` |
| `updated_at` | always |

---

## 8 · Mock-mode and dry-run

### Mock-mode (`--mock`)

When `mock=True`, `abstract_collector.py` reads from fixture JSON files instead of making network calls. No `SemanticScholarClient`, `CrossRefClient`, `PubMedClient`, or `OpenAlexClient` is instantiated. Fixture routing:

```
mock_fixtures_dir/
  mock_s2_abstract.json      → used when doi matches fixture["doi"]
  mock_crossref_abstract.json→ used when doi matches fixture["doi"]
  mock_pubmed_abstract.json  → used when doi matches fixture["doi"]
  mock_openalex_abstract.json→ used when doi matches fixture["doi"] or title substring match
```

A row that matches no fixture → `MISSING_ABSTRACT` (safe fallback, tests absence path).

### Dry-run (`--dry-run`)

When `dry_run=True`:
- `triage_engine.py` copies `task3_pipeline_lifecycle.db` to `":memory:"` at the start.
- All UPDATE and INSERT statements execute against in-memory copy.
- No changes to the on-disk DB.
- `triage_results.json` is written to a `phase4_dryrun/` subdirectory instead of overwriting the real output.

---

## 9 · `triage_results.json` schema v1.0.0

```jsonc
{
  "schema_version": "1.0.0",
  "run_id": "RUN-2026-05-27-143022",
  "generated_at": "2026-05-27T14:30:45Z",
  "db_path": "...",
  "total_rows_processed": 120,
  "stage1": {
    "passed": 108,
    "rejected_empty_title": 3,
    "skipped_duplicate": 9,
    "skipped_already_triaged": 0
  },
  "stage2a": {
    "abstract_collected": 95,
    "abstract_missing": 13,
    "source_breakdown": {
      "semantic_scholar": 52,
      "crossref": 21,
      "pubmed": 15,
      "openalex": 7,
      "MISSING_ABSTRACT": 13
    }
  },
  "stage2b": {
    "ACCEPT": 34,
    "EDGE_CASE": 28,
    "REJECT": 33,
    "MISSING_ABSTRACT": 13
  },
  "classifier_mode": "hierarchical | keyword_fallback",
  "voi_map_source": "path/to/query_results.json",
  "per_query_voi": {
    "ARCH_PROMENADE_TEMPORAL_PE_001": 0.478
  },
  "errors": []
}
```

**Enumerated `errors` items:**

```jsonc
{
  "reference_id": "REF-2026-05-27-000042",
  "stage": "stage2a",
  "source": "semantic_scholar",
  "error": "HTTPError 429: rate limit exceeded",
  "fallthrough": true   // true = continued to next source; false = bailed
}
```

---

## 10 · Success conditions (SC-1 through SC-18)

| # | Condition | Verified by |
|---|---|---|
| SC-1 | All `metadata_only` rows processed (or skipped idempotently) | `test_triage_engine.py::test_batch_processes_all_metadata_only_rows` |
| SC-2 | Stage 1 rejects rows with null or empty `title_raw` | `test_triage_engine.py::test_stage1_rejects_empty_title` |
| SC-3 | `duplicate` rows not processed through Stage 1 | `test_triage_engine.py::test_stage1_skips_duplicate_rows` |
| SC-4 | Abstract chain tries all 4 sources before returning MISSING_ABSTRACT | `test_abstract_collector.py::test_all_fail_returns_missing_abstract` |
| SC-5 | Semantic Scholar DOI lookup tried first when DOI is present | `test_abstract_collector.py::test_fallback_chain_s2_first` |
| SC-6 | CrossRef tried when Semantic Scholar returns no abstract | `test_abstract_collector.py::test_fallback_chain_skips_to_crossref_when_s2_none` |
| SC-7 | PubMed tried when CrossRef returns no abstract | `test_abstract_collector.py::test_fallback_chain_uses_pubmed_when_s2_crossref_none` |
| SC-8 | OpenAlex tried as 4th source before MISSING_ABSTRACT | `test_abstract_collector.py::test_fallback_chain_uses_openalex_last` |
| SC-9 | `abstract_source` column always set (including `MISSING_ABSTRACT`) | `test_triage_engine.py::test_abstract_source_always_set` |
| SC-10 | `abstract_text` stored in `article_references` when found | `test_triage_engine.py::test_abstract_text_stored` |
| SC-11 | Classifier maps `send_to_eater`→ACCEPT, `review`→EDGE_CASE, `reject`→REJECT | `test_triage_engine.py::test_classifier_decision_mapping` |
| SC-12 | `MISSING_ABSTRACT` rows receive `triage_decision='MISSING_ABSTRACT'` without classifier call | `test_triage_engine.py::test_missing_abstract_skips_classifier` |
| SC-13 | `classifier_confidence` stored from `best_confidence` / `domain_score` | `test_triage_engine.py::test_classifier_confidence_stored` |
| SC-14 | `voi_score` derived from `query_results.json` using `discovered_query` key | `test_triage_engine.py::test_voi_score_set_from_query_voi` |
| SC-15 | `lifecycle_transitions` row written per stage with correct `created_by` | `test_triage_engine.py::test_lifecycle_transitions_written_per_stage` |
| SC-16 | Dry-run makes no writes to real on-disk DB | `test_triage_engine.py::test_dry_run_no_db_writes` |
| SC-17 | `triage_results.json` written and schema-valid | `test_triage_engine.py::test_triage_results_schema_valid` |
| SC-18 | Re-running on already-triaged rows is a no-op (idempotent) | `test_triage_engine.py::test_idempotent_on_already_triaged_rows` |

---

## 11 · Test plan (35 tests across 2 files)

### `test_abstract_collector.py` (15 tests)

| Test | What it verifies |
|---|---|
| `test_s2_returns_abstract_by_doi` | S2 DOI lookup → abstract returned, source = "semantic_scholar" |
| `test_s2_returns_abstract_by_title_fallback` | S2 title search used when DOI absent |
| `test_crossref_returns_abstract` | CrossRef fetch returns abstract when S2 returns none |
| `test_pubmed_returns_abstract_by_doi` | PubMed fetch by DOI |
| `test_pubmed_returns_abstract_by_title_year` | PubMed search by title+year when DOI absent |
| `test_openalex_returns_abstract_by_doi` | OpenAlex DOI fetch; inverted-index decoded correctly |
| `test_openalex_returns_abstract_by_title` | OpenAlex title search fallback |
| `test_fallback_chain_s2_first` | S2 is first source attempted; mock S2 returns abstract → chain stops |
| `test_fallback_chain_skips_to_crossref_when_s2_none` | S2 returns None → CrossRef tried |
| `test_fallback_chain_uses_pubmed_when_s2_crossref_none` | S2+CrossRef None → PubMed tried |
| `test_fallback_chain_uses_openalex_last` | S2+CrossRef+PubMed None → OpenAlex tried |
| `test_all_fail_returns_missing_abstract` | All 4 None → AbstractResult.source == "MISSING_ABSTRACT" |
| `test_mock_mode_no_network_calls` | With mock=True, no HTTP clients are instantiated |
| `test_rate_limit_respected` | `_RateLimiter.wait()` called once per source attempt |
| `test_doi_normalised_before_lookup` | DOI with "https://doi.org/" prefix stripped before passing to S2/CrossRef |

### `test_triage_engine.py` (20 tests)

| Test | What it verifies |
|---|---|
| `test_stage1_rejects_empty_title` | Row with `title_raw=''` → `triage_decision=REJECT`, `triage_stage=rejected_stage1` |
| `test_stage1_skips_duplicate_rows` | Row with `triage_stage='duplicate'` not advanced |
| `test_stage1_passes_rows_with_title` | Row with non-empty title advances to `stage1_screened` |
| `test_stage2a_abstract_collected_logged` | After successful abstract → `triage_stage=abstract_collected`, transition logged |
| `test_stage2a_missing_abstract_logged` | All sources fail → `triage_stage=abstract_missing`, transition logged |
| `test_abstract_source_always_set` | `abstract_source` column never NULL after Stage 2A |
| `test_abstract_text_stored` | `abstract_text` stored when abstract found |
| `test_classifier_decision_mapping` | All 3 classifier outputs map to correct triage_decision |
| `test_missing_abstract_skips_classifier` | MISSING_ABSTRACT rows → no classifier call, `triage_decision=MISSING_ABSTRACT` |
| `test_voi_score_set_from_query_voi` | `voi_score` matches `voi_score` in query_results.json for matching query |
| `test_voi_score_default_when_query_not_found` | Unknown `discovered_query` → `voi_score=0.443` |
| `test_classifier_confidence_stored` | `classifier_confidence` non-null after Stage 2B (when classifier ran) |
| `test_lifecycle_transitions_written_per_stage` | 3 transition rows written for a row going through all 3 stages |
| `test_created_by_correct_for_each_transition` | S1/S2B transitions have `created_by=triage_engine`; S2A has `created_by=abstract_collector` |
| `test_idempotent_on_already_triaged_rows` | `triage_stage=triage_complete` rows not reprocessed |
| `test_dry_run_no_db_writes` | After dry-run, real DB file unchanged (compare checksums) |
| `test_mock_mode_fixture_abstracts_used` | mock=True → fixture abstracts loaded, no HTTP clients |
| `test_triage_results_json_written` | JSON output file exists after `run_triage()` |
| `test_triage_results_schema_valid` | Output JSON has all required keys and correct value types |
| `test_batch_processes_all_metadata_only_rows` | 10-row fixture with 8 `metadata_only` + 2 `duplicate` → exactly 8 processed |

---

## 12 · Locked decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D-1 | Abstract sources | S2 → CrossRef → PubMed → OpenAlex | S2 has highest abstract coverage in CNFA domain; CrossRef authoritative for DOI→metadata; PubMed covers biomedical overlap; OpenAlex is free and fast with good coverage for recent papers |
| D-2 | 4th source | OpenAlex (not Unpaywall) | Unpaywall (`UnpaywallClient` in paper_fetcher.py) returns OA PDF links, not abstracts. OpenAlex returns abstracts directly. |
| D-3 | Classifier | `HierarchicalClassifier.classify_paper()` from `Article_Finder/triage/classifier.py` | Reuses the centroid-based classifier already calibrated on CNFA taxonomy. Falls back to keyword classifier if centroids absent. |
| D-4 | VOI at Phase 4 | Query-level VOI from query_results.json (not `score_voi()`) | `score_voi()` operates on extracted findings, which don't exist for candidate papers. Query VOI is the best available proxy. |
| D-5 | Constitution gate | Not used in Phase 4 | `QuestionAwareTriageGate` requires a `QuestionConstitution` JSON file not present in the repo. The `HierarchicalClassifier` alone gives adequate triage signal. |
| D-6 | Classifier fallback | Keyword-based (see §3C) | Ensures Phase 4 runs in any environment, including one without `sentence-transformers`. Fallback confidence is always 0.5 to distinguish from centroid-derived scores. |

---

## 13 · CLI entry point

```
python triage_engine.py \
  --db          ../../task3_pipeline_lifecycle.db \
  --queries     ../../Phase 2/search_results/query_results.json \
  --run-id      RUN-2026-05-27-143022 \
  --output      triage_results.json \
  [--mock]      \
  [--dry-run]
```

Exit codes: `0` success, `1` unrecoverable error, `2` partial failure (some rows errored, rest processed).

---

## 14 · Dependency audit

| Package | Already installed? | Notes |
|---|---|---|
| `requests` / `urllib` | stdlib `urllib` used throughout | No new packages for HTTP |
| `sentence-transformers` | Present in Article_Finder `.venv` | Phase 4 code runs in Article_Finder venv or falls back to keyword classifier |
| `pdfplumber` | Used in Phase 3 | Not needed in Phase 4 |
| `atlas_shared` | Installed in Article_Finder `.venv` as `atlas_shared-0.3.0` | Imported by `classifier.py` but Phase 4 uses only `HierarchicalClassifier`, not `QuestionAwareTriageGate` |
| `numpy` | Required by `HierarchicalClassifier` | Present in Article_Finder `.venv` |

**No new `pip install` required** if running inside the Article_Finder `.venv`. If running standalone, only `numpy` is needed beyond stdlib.

---

## 15 · Effort estimate

| Sub-task | Hours |
|---|---|
| `openalex_client.py` (client + inverted-index decoder + tests) | 1.0 |
| `abstract_collector.py` (fallback chain + mock mode) | 2.5 |
| `triage_engine.py` (3 stages + DB updates + lifecycle transitions) | 3.0 |
| VOI map builder + query_results.json integration | 0.5 |
| Fixtures (5 JSON files) | 0.5 |
| `test_abstract_collector.py` (15 tests) | 1.5 |
| `test_triage_engine.py` (20 tests) | 2.0 |
| `triage_results.json` schema + writer | 0.5 |
| Integration smoke test (end-to-end with dry-run) | 0.5 |
| **Total** | **~12 hr** |
