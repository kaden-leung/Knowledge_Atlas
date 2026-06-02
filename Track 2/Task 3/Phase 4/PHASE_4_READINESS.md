# Phase 4 Readiness — Reconciliation with Phase 3

**Author:** Kaden Leung
**Date:** 2026-05-28

PHASE_4_PLAN.md was drafted on 2026-05-27, before Phase 3 was built. This document audits the plan against the Phase 3 deliverables that actually shipped, surfaces small mismatches, and confirms what's ready to go.

---

## Compatibility check

| Phase 4 plan reference | Phase 3 ships | Status |
|---|---|---|
| `task3_pipeline_lifecycle.db` at `../../task3_pipeline_lifecycle.db` | Same path | ✓ |
| `article_references` table with 24 cols incl. `abstract_text`, `abstract_source`, `triage_decision`, `triage_reason`, `classifier_confidence`, `voi_score` | DDL has all these | ✓ |
| `lifecycle_transitions` audit log with `created_by` | Built; FK enforced ON DELETE CASCADE | ✓ |
| `insert_or_dedupe_reference()` only for INSERTs; Phase 4 only UPDATEs existing rows | Single mutation path doc'd in SCHEMA_CONTRACT §3, §8 | ✓ |
| `query_results.json` from Task 2 for VOI lookup | Path: `Track 2/Task 2/Phase 3/query_results.json` (also mirrored at root) | ✓ |
| Reuses `SemanticScholarClient`, `CrossRefClient`, `PubMedClient` from `Article_Eater/src/services/paper_fetcher.py` | Confirmed in Phase 1B review; clients import cleanly | ✓ |
| Reuses `HierarchicalClassifier` from `Article_Finder/triage/classifier.py` | File exists per plan §3C; need to confirm at execution time | To verify |

## Small mismatches to resolve at execution time

### 1. `created_by` enum naming

PHASE_4_PLAN.md §5 says Phase 4 transitions are written with `created_by='triage_engine'` (for Stage 1, Stage 2B) and `created_by='abstract_collector'` (for Stage 2A).

Phase 3 `dedupe.py:CREATED_BY_ENUM` allows:
- `db_loader`, `reference_harvester` (Phase 3 writers — used)
- `abstract_collector`, `abstract_triage`, `pdf_acquirer`, `manual_edit` (reserved for later phases)

**Action at Phase 4 execution:** either
- (a) rename Phase 4's `triage_engine` writer to `abstract_triage` to match the existing enum, or
- (b) add `triage_engine` to `CREATED_BY_ENUM` and update SCHEMA_CONTRACT.md §7.1.

Recommendation: **(a) use `abstract_triage`** — already in the enum; semantically clearer (it's the triage writer, distinct from the abstract collector).

### 2. New `triage_stage` values

PHASE_4_PLAN.md §4 introduces 5 new values not present in Phase 3:
- `stage1_screened` (after Stage 1 passes)
- `abstract_collected` (after Stage 2A succeeds)
- `abstract_missing` (after Stage 2A fails on all 4 sources)
- `triage_complete` (after Stage 2B)
- `rejected_stage1` (Stage 1 reject path)

Phase 3 DDL has no CHECK constraint on `triage_stage` — it's `TEXT NOT NULL DEFAULT 'metadata_only'`. Any string value writes successfully.

**Action at Phase 4 execution:** document the new values in `SCHEMA_CONTRACT.md §7.2` and `MANIFEST.md`. No DDL change required.

### 3. `triage_decision` values

PHASE_4_PLAN.md §4 uses `ACCEPT`, `EDGE_CASE`, `REJECT`, `MISSING_ABSTRACT`. Phase 3 SCHEMA_CONTRACT.md §4.1 already lists these as the expected values; no change needed.

### 4. `discovered_via` enum

Phase 4 only UPDATEs existing rows — does not write new `discovered_via` values. No enum change required.

---

## Live-run dependency

PHASE_4_PLAN.md §6 derives `voi_score` for each candidate from the discovering query in `query_results.json`. This is keyed by `discovered_query` string match. The 1110 rows currently in the DB (from the mock + harvester) include:

- 7 rows from `db_loader` with `discovered_query` set to the 10 boolean queries (we have 7 due to dedupe)
- 1103 rows from `reference_harvester` with `discovered_query = NULL` (PDFs don't carry query provenance)

So Phase 4's VOI lookup will find a match only for the ~7 SerpAPI/scholarly/paperscraper rows; the 1103 review-extract rows will fall through to the default VOI (`0.443`). This is consistent with PHASE_4_PLAN.md §6.

After the in-progress live Phase 2 run completes, the SerpAPI/scholarly/paperscraper row count may grow from 7 to a few dozen, and Phase 4's VOI lookup will hit more rows. The harvester rows still default.

---

## Test reuse opportunities

Phase 3's test patterns translate cleanly to Phase 4:
- `db` fixture from `test_schema.py` (apply migrations to tmp_path DB) → reuse
- Mocking the HTTP clients (`SemanticScholarClient.fetch_by_doi`, etc.) follows the same `unittest.mock.patch` pattern as `test_serpapi_retry_on_rate_limit` in Phase 2
- Linter test scanning for raw `INSERT INTO article_references` outside the dedupe path → already exists; Phase 4 writers only UPDATE, so the linter still applies

## Open questions for execution

1. **Heuristic Stage 1 rules.** The plan focuses on `empty_title` as the only Stage 1 reject. But our DEDUPE_SPOTCHECK surfaced JSTOR footers / CID artifacts / generic short titles as the dominant noise. Should Phase 4 Stage 1 add regex rejects for these? (Recommendation: yes; ~5 regex rules covering ~30 noisy rows.)
2. **Classifier centroids.** `Article_Finder/triage/.centroids.pkl` — does this file exist? If not, fall back to the keyword classifier per D-6.
3. **API auth keys.** `SEMANTIC_SCHOLAR_API_KEY` and `NCBI_API_KEY` — if available in `.env`, abstract collection will be ~3x faster.

These are execution-time decisions, not plan-revision decisions.

---

## Verdict

PHASE_4_PLAN.md is **ready to execute** with three minor adjustments to be made at execution time (rename `triage_engine` → `abstract_triage`, document new `triage_stage` values, decide Stage 1 heuristic rules). No structural revisions to the plan are needed.

Estimated effort: **~12 hr** (per plan §15) plus ~1 hr for the reconciliation items above.

Next step when you're ready: I'd start with `openalex_client.py` (smallest module, no DB writes) to validate the import path setup, then `abstract_collector.py`, then `triage_engine.py`.
