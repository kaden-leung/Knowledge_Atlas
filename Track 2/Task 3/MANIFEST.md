# Track 2 · Task 3 — MANIFEST

**Author:** Kaden Leung
**Last Updated:** 2026-05-28
**Status:** Phases 1, 2, 3 complete. Phase 4 next.

This document is the single-page audit trail for the grader. For deep specs, see the linked contracts.

---

## Deliverables

### Phase 2 — Search Runner

- [Phase 2/SEARCH_RUNNER_CONTRACT.md](Phase%202/SEARCH_RUNNER_CONTRACT.md) — v1.2.0; SC-1 through SC-32
- [Phase 2/search_runner.py](Phase%202/search_runner.py) — CLI; `--mock-from`, `--dry-run`, `--confirm-live` gates
- [Phase 2/adapters/](Phase%202/adapters/) — SerpAPI (`engine=google_scholar`, 1 credit/call), scholarly (≥5 s rate limit), paperscraper, mock
- [Phase 2/schema/search_results.schema.json](Phase%202/schema/search_results.schema.json) — JSON Schema Draft 2020-12; authoritative output spec
- **Tests:** 40/40 passing

### Phase 3 — DB Loader + Reference Harvester

- [Phase 3/SCHEMA_CONTRACT.md](Phase%203/SCHEMA_CONTRACT.md) — v1.0.0; SC-1 through SC-13
- [Phase 3/REFERENCE_HARVESTER_CONTRACT.md](Phase%203/REFERENCE_HARVESTER_CONTRACT.md) — v1.0.0; SC-H1 through SC-H12
- [Phase 3/migrations/](Phase%203/migrations/) — 4 idempotent SQL files: `article_references`, `lifecycle_transitions`, `v_acquisition_queue`, funnel index
- [Phase 3/migrate.py](Phase%203/migrate.py) — migration runner
- [Phase 3/dedupe.py](Phase%203/dedupe.py) — `insert_or_dedupe_reference()` — single mutation path
- [Phase 3/db_loader.py](Phase%203/db_loader.py) — Phase 2 → DB writer (`created_by='db_loader'`)
- [Phase 3/reference_harvester.py](Phase%203/reference_harvester.py) — PDF reference extractor (`created_by='reference_harvester'`)
- [Phase 3/DEDUPE_SPOTCHECK.md](Phase%203/DEDUPE_SPOTCHECK.md) — manual review of 10 merge events; **PASS, 0 false positives**
- **Tests:** 51/51 passing

---

## Runtime DB state (as of 2026-05-28 run RUN-20260528-120000)

### `article_references`

| Metric | Value |
|---|---|
| Total rows | **1110** |
| Rows with non-null DOI | 5 (search runner only) |
| Rows with `discovered_via = 'serpapi_scholar'` (substring) | 5 |
| Rows with `discovered_via = 'scholarly_search'` (substring) | 3 |
| Rows with `discovered_via = 'paperscraper_search'` (substring) | 2 |
| Rows with `discovered_via = 'review_pdf_extract'` (substring) | 1103 |
| Rows with `triage_stage = 'metadata_only'` | 1110 |
| Rows with `triage_stage = 'duplicate'` | 0 (empty corpus stub) |
| Rows with `triage_decision IS NULL` | 1110 (Phase 4 will fill) |

### `lifecycle_transitions`

| Metric | Value |
|---|---|
| Total rows | **1144** |
| `created_by = 'db_loader'` | 7 |
| `created_by = 'reference_harvester'` | 1137 |
| `reason LIKE 'initial_insert:%'` | 1110 |
| `reason LIKE 'provenance_merge:%'` (DOI merges) | 18 |
| `reason LIKE 'provenance_merge_via_title:%'` (Jaccard merges) | 16 |
| `reason LIKE 'doi_enriched_via_%'` | 0 |
| `reason LIKE 'corpus_match:%'` | 0 |

### `v_acquisition_queue` rows

**0** — expected, since no row is `triage_decision='ACCEPT'` yet. Phase 4 will populate this when Stage 2 triage runs.

### Database paths and content hashes

| Path | Size | Content hash (sorted-row SHA-256) |
|---|---|---|
| `Track 2/Task 3/task3_pipeline_lifecycle.db` | 1.24 MB | `3075d06e4b3201bef0ab47414f70d9368f22a72febefd23490222e5570e31592` |
| `Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db` (snapshot via `VACUUM INTO`) | 1.24 MB | `3075d06e4b3201bef0ab47414f70d9368f22a72febefd23490222e5570e31592` |

**Content-equality verified.** Byte-level hashes differ because `VACUUM INTO` repacks pages; row content is identical.

---

## `v_acquisition_queue` SQL (Phase 5 will read this)

```sql
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
```

---

## Reproducing the Phase 3 run

```bash
cd "Track 2/Task 3/Phase 2"

# 1. Generate Phase 2 output in mock mode (no credits spent)
SERPAPI_KEY=mock_unused python3 search_runner.py \
    --mock-from fixtures \
    --run-id RUN-20260528-120000

cd "../Phase 3"

# 2. Apply migrations + load Phase 2 results
python3 db_loader.py \
    --search-results "../Phase 2/search_results.json" \
    --db "../task3_pipeline_lifecycle.db" \
    --no-snapshot

# 3. Harvest references from local PDFs (20 PDFs in two directories)
python3 reference_harvester.py \
    --db "../task3_pipeline_lifecycle.db" \
    --run-id RUN-20260528-120000

# 4. Materialize the shared-path snapshot via VACUUM INTO
python3 -c "
import sqlite3
src = sqlite3.connect('../task3_pipeline_lifecycle.db')
src.execute('VACUUM INTO ?', ('../../../Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db',))
src.commit(); src.close()
"

# 5. Run all tests
python3 -m pytest -v
```

---

## Path deviations from course spec

The course spec assumes a specific set of dependencies. Three substitutions documented (see [memory/project_t3_phase3_spec.md](memory/project_t3_phase3_spec.md) for the verbatim spec):

| Course spec | Local state | Substitution |
|---|---|---|
| Write rows to `pipeline_lifecycle_full.db` | File is 0 bytes on this machine | Write to local `task3_pipeline_lifecycle.db`; materialize shared snapshot via `VACUUM INTO` (Option C strict) |
| Use AE coordination scripts `extract_neuro_key_review_references.py`, `build_neuro_review_acquisition_queue.py` | Neither script exists locally | Built equivalents from scratch in `dedupe.py` + `reference_harvester.py` |
| Prototype against 46 review PDFs at `/Users/davidusa/...` | Path not on this machine | Used 20 local PDFs (`Part 2 Pdfs/` + `Part_One_10pdfs/`) |
| `pdf_identity_inventory/latest.csv` for corpus dedupe | File does not exist | Header-only stub at `Phase 3/pdf_identity_inventory_local.csv`; Branch B (corpus match) never fires until populated |

If the grader requires the literal course path, the materialized snapshot satisfies that — the DB at `Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db` is content-equal to the local source-of-truth.

---

## Active constraints

- Never push to bare `git push` — only `git push fork <branch>`; dry-run first
- Never commit `SERPAPI_KEY` — lives in `.env` (gitignored)
- Never call live adapter from tests — always use MockAdapter
- SerpAPI budget: 250 credits/month; 50-credit hard cap per run enforced in `search_runner.py`
- Local DB and JSON outputs are runtime artifacts — gitignored (see [.gitignore](.gitignore))
