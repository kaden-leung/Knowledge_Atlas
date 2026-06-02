# Triage Decision Contract — Phase 4 Sub-phase 4D (Stage 2B)

**Track 2 · Task 3 · Phase 4**
**Author:** Kaden Leung
**Contract Version:** 1.0.0
**Last Updated:** 2026-05-31

---

## 1. System Summary

Stage 2B is the **choke point**. It takes every row that successfully reached `triage_stage='abstract_collected'` (from sub-phase 4B) and produces the first real ACCEPT / EDGE_CASE / REJECT decision for the pipeline. ACCEPT rows become Phase 5's PDF acquisition queue. EDGE_CASE rows are stored with a flag and exported to a human-readable JSON for review. REJECT rows are logged in `lifecycle_transitions` (never silently dropped). Rows already at `triage_decision='MISSING_ABSTRACT'` (from 4B) are skipped — the course rule is firm: a missing abstract is not the same as a reject.

The decision is a function of **two inputs per row**: classifier confidence (how on-topic is this paper for COGS-160?) and VOI score (how valuable is the gap this query was supposed to fill?). The decision matrix in §3 combines them.

This module is the last decision the pipeline makes before spending bandwidth and disk on a PDF. Every later phase (5+) reads `v_acquisition_queue`, which selects only `triage_decision='ACCEPT'` rows.

---

## 2. Inputs

### 2.1 From `article_references`

Each row where `triage_stage = 'abstract_collected'`:

| Column | Type | Used for |
|---|---|---|
| `reference_id` | TEXT | Identity + transition logging |
| `title_raw` | TEXT | Classifier input |
| `abstract_text` | TEXT | **Primary** classifier input (now available; was NULL during Stage 1) |
| `venue` | TEXT or NULL | Classifier input |
| `discovered_query` | TEXT or NULL | Key for VOI lookup against `query_results.json` |
| `doi` | TEXT or NULL | Used in audit JSON; not in decision logic |

### 2.2 From `query_results.json` (Task 2 output)

VOI map keyed by either the boolean query string or the query's display_id. Values are floats in `[0.0, 1.0]` from `score_voi()`.

### 2.3 Configuration

| Parameter | Default | Meaning |
|---|---|---|
| `db_path` | `Track 2/Task 3/task3_pipeline_lifecycle.db` | Local DB |
| `run_id` | required | Stamped on every transition row |
| `query_results_json` | `Track 2/Task 2/Phase 3/query_results.json` | Source of `voi_score` lookups |
| `classifier_on_topic` | `0.50` | Confidence ≥ this → "on-topic" |
| `classifier_off_topic` | `0.20` | Confidence < this → "off-topic" |
| `voi_high` | `0.70` | VOI ≥ this → "high" |
| `voi_medium` | `0.50` | VOI ≥ this → "medium" (else "low") |
| `voi_default` | `0.443` | Used when `discovered_query` has no matching VOI (e.g. PDF-extract rows) |
| `dry_run` | `False` | In-memory SQLite copy; no disk write |

### 2.4 External classifier

Same loader as Stage 1 (`stage1_metadata_triage.py:load_classifier`) — tries `HierarchicalClassifier` first, falls back to keyword classifier. Stage 2B passes the abstract in addition to title+venue, so even the keyword classifier produces a richer score than Stage 1's.

---

## 3. Decision matrix (Balanced — locked)

| Classifier confidence | VOI ≥ 0.70 (high) | 0.50 ≤ VOI < 0.70 (medium) | VOI < 0.50 (low) |
|---|---|---|---|
| **≥ 0.50** (on-topic) | **ACCEPT** | **ACCEPT** | **EDGE_CASE** |
| **0.20 – 0.49** (marginal) | **EDGE_CASE** | **EDGE_CASE** | **REJECT** |
| **< 0.20** (off-topic) | **REJECT** | **REJECT** | **REJECT** |

Rationale:
- **ACCEPT** = clearly on-topic AND at least medium-VOI. The paper is on the field and the gap it fills is worth filling.
- **EDGE_CASE** captures three patterns worth a human glance:
  - clearly on-topic but low VOI (paper is fine but the gap is already well-covered)
  - marginal classifier + good VOI (paper might be off but the gap matters)
  - marginal classifier + medium VOI
- **REJECT** = off-topic, or marginal + low VOI.

### `triage_reason` format

Always non-empty. Format:
- ACCEPT: `accept_topic_and_voi:clf=0.NN,voi=0.NN`
- EDGE_CASE: one of
  - `edge_on_topic_low_voi:clf=0.NN,voi=0.NN`
  - `edge_marginal_topic_high_voi:clf=0.NN,voi=0.NN`
  - `edge_marginal_topic_medium_voi:clf=0.NN,voi=0.NN`
- REJECT: one of
  - `reject_off_topic:clf=0.NN,voi=0.NN`
  - `reject_marginal_low_voi:clf=0.NN,voi=0.NN`

The reason string carries both signals so a downstream reviewer can recompute the decision without re-running anything.

---

## 4. Processing

For each row in `WHERE triage_stage = 'abstract_collected'`:

1. **Classify.** `classifier(title=title_raw, venue=venue, abstract=abstract_text)` → `(_, confidence)`. The decision token returned by the classifier is **not** used directly — Stage 2B uses only the confidence float. The decision matrix is authoritative.
2. **Look up VOI.** `voi_map.get(discovered_query, voi_default)`. PDF-extract rows (no `discovered_query`) get `voi_default = 0.443`.
3. **Apply matrix.** `_decide(confidence, voi)` → `(triage_decision, triage_reason)`.
4. **DB write** (one transaction per row):
   ```sql
   UPDATE article_references
      SET triage_decision = ?,
          triage_reason = ?,
          classifier_confidence = ?,
          voi_score = ?,
          triage_stage = 'triage_complete',
          updated_at = ?
    WHERE reference_id = ? AND triage_stage = 'abstract_collected';

   INSERT INTO lifecycle_transitions
     (reference_id, run_id, from_stage, to_stage, reason, created_by)
   VALUES (?, ?, 'abstract_collected', 'triage_complete', ?, 'abstract_triage');
   ```
5. **Accumulate report counts**, including the EDGE_CASE export.

Rows at `triage_stage='abstract_missing'` are **not selected** by the WHERE clause; their `triage_decision` is already `'MISSING_ABSTRACT'` from 4B. No re-classification, no re-scoring.

---

## 5. Outputs

### 5.1 DB updates per row

| Column | Set to |
|---|---|
| `triage_decision` | `ACCEPT` / `EDGE_CASE` / `REJECT` |
| `triage_reason` | Non-empty string (format in §3) |
| `classifier_confidence` | float in `[0.0, 1.0]` |
| `voi_score` | float in `[0.0, 1.0]` — may have been NULL before this stage |
| `triage_stage` | `triage_complete` (terminal for Phase 4) |
| `updated_at` | `YYYY-MM-DDTHH:MM:SSZ` |

### 5.2 `lifecycle_transitions`

One row per processed candidate. `created_by='abstract_triage'`. `from_stage='abstract_collected'`, `to_stage='triage_complete'`, `reason` = the `triage_reason` from §3.

### 5.3 `triage_results.json`

```json
{
  "schema_version": "1.0.0",
  "run_id": "RUN-...",
  "started_at": "2026-...Z",
  "ended_at": "2026-...Z",
  "candidates_processed": 200,
  "decisions": {
    "ACCEPT": 60,
    "EDGE_CASE": 45,
    "REJECT": 95
  },
  "classifier_mode": "hierarchical | keyword_fallback",
  "thresholds": {
    "classifier_on_topic": 0.50,
    "classifier_off_topic": 0.20,
    "voi_high": 0.70,
    "voi_medium": 0.50,
    "voi_default": 0.443
  },
  "voi_lookup_hits": 14,
  "voi_lookup_misses": 186,
  "errors": []
}
```

### 5.4 `edge_cases_for_review.json` (human-readable)

```json
{
  "schema_version": "1.0.0",
  "run_id": "RUN-...",
  "generated_at": "2026-...Z",
  "edge_cases": [
    {
      "reference_id": "REF-2026-05-30-000001",
      "title_raw": "Architectural affordances ...",
      "doi": "10.1073/pnas.1912264116",
      "venue": "Proceedings of the National Academy of Sciences",
      "abstract_text": "...",
      "triage_reason": "edge_marginal_topic_high_voi:clf=0.35,voi=0.85",
      "classifier_confidence": 0.35,
      "voi_score": 0.85
    }
  ]
}
```

The JSON contains the full abstract so a reviewer can decide without touching the DB. Stored in the Phase 4 directory; gitignored (runtime artifact).

### 5.5 `v_acquisition_queue` (Phase 5's read path)

Already enforced by the view DDL (`triage_decision = 'ACCEPT' AND acquired_paper_id IS NULL`). Stage 2B's only job is to set `triage_decision='ACCEPT'` on qualifying rows. SC-T4 confirms ACCEPT rows appear.

---

## 6. Invariants

- **I-1.** Every `abstract_collected` row reaches `triage_stage='triage_complete'` after a successful run. No row stuck at `abstract_collected`.
- **I-2.** Every triaged row has non-null `triage_decision` ∈ `{ACCEPT, EDGE_CASE, REJECT}` and non-empty `triage_reason`.
- **I-3.** `MISSING_ABSTRACT` rows (set by 4B) are not selected, not updated, not re-classified.
- **I-4.** Every paired `(UPDATE article_references, INSERT lifecycle_transitions)` happens in one transaction. Row counts must match.
- **I-5.** Every `lifecycle_transitions` row from this module has `created_by='abstract_triage'`.
- **I-6.** Rerunning Stage 2B on a row that is already `triage_complete` is a no-op (WHERE clause filter).
- **I-7.** `v_acquisition_queue` returns exactly the ACCEPT-rows-not-yet-acquired set after the run.
- **I-8.** Every emitted timestamp matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`.

---

## 7. Success Conditions

| SC | Statement | Test |
|---|---|---|
| SC-T1 | Every row in `abstract_collected` becomes one of `ACCEPT`/`EDGE_CASE`/`REJECT`; none left at NULL. | `test_every_row_gets_triage_decision` |
| SC-T2 | Every triaged row has a non-empty `triage_reason`. | `test_every_triage_reason_nonempty` |
| SC-T3 | `MISSING_ABSTRACT` rows are skipped — not re-classified, not re-scored. | `test_missing_abstract_skipped_not_rescored` |
| SC-T4 | ACCEPT rows reach `triage_stage='triage_complete'` with `triage_decision='ACCEPT'` and appear in `v_acquisition_queue`. | `test_accept_appears_in_v_acquisition_queue` |
| SC-T5 | EDGE_CASE rows are exported to `edge_cases_for_review.json` with full abstract. | `test_edge_case_exported_to_review_json` |
| SC-T6 | REJECT rows write a `lifecycle_transitions` row (never silently dropped). | `test_reject_logged_to_transitions` |
| SC-T7 | Post-triage, `classifier_confidence` and `voi_score` columns are populated. | `test_confidence_and_voi_columns_filled` |
| SC-T8 | The decision matrix is applied as documented (parametrized 3×3 = 9 cells). | `test_decision_matrix_per_cell` |
| SC-T9 | VOI lookup hits `query_results.json` by `discovered_query`; unmatched rows get `voi_default=0.443`. | `test_voi_lookup_with_fallback` |
| SC-T10 | Classifier falls back to keyword mode when `HierarchicalClassifier` is unavailable. | `test_classifier_fallback_when_centroids_missing` |
| SC-T11 | `--dry-run` writes nothing to the on-disk DB. | `test_dry_run_no_disk_writes` |
| SC-T12 | Re-running Stage 2B on rows already at `triage_complete` is a no-op. | `test_idempotent_on_triage_complete` |

---

## 8. Definitions

### 8.1 On-topic / marginal / off-topic
- `confidence ≥ 0.50` → on-topic
- `0.20 ≤ confidence < 0.50` → marginal
- `confidence < 0.20` → off-topic

### 8.2 High / medium / low VOI
- `voi ≥ 0.70` → high
- `0.50 ≤ voi < 0.70` → medium
- `voi < 0.50` → low (includes the default 0.443)

### 8.3 Choke point
The first place in the pipeline where a paper can be permanently rejected (besides Stage 1 metadata noise). Phase 5 will not consider any row absent from `v_acquisition_queue`, so a REJECT here is a final decision.

### 8.4 EDGE_CASE
A row the system can't confidently bucket. Stored in the DB with `triage_decision='EDGE_CASE'` AND exported to `edge_cases_for_review.json` for human review. Phase 5 does not auto-acquire these.

---

## 9. Non-Goals

- Does NOT fetch new abstracts (4B's job — and 4B has terminal MISSING_ABSTRACT for failures).
- Does NOT call `score_voi()` directly. `score_voi()` operates on extracted findings (Tier 3 nodes) which Phase 4 doesn't produce. Stage 2B uses query-level VOI as a proxy (PHASE_4_PLAN.md §6).
- Does NOT extract findings or build the Bayesian network (Phase 7).
- Does NOT acquire PDFs (Phase 5).
- Does NOT re-process rows that are already `triage_complete` (idempotency guard).

---

## 10. Known Limitations

1. **Query-level VOI is a proxy.** The "real" VOI per the Article_Eater design comes from `score_voi(findings)`. Phase 4 doesn't extract findings; we substitute the discovering query's VOI. This is correct for SerpAPI/scholarly/paperscraper rows and uses the `voi_default=0.443` for PDF-extract rows.
2. **Classifier confidence is mode-dependent.** A 0.50 from `HierarchicalClassifier` (centroid-based) is not the same as 0.50 from the keyword fallback. The `classifier_mode` field in the report distinguishes them.
3. **EDGE_CASE growth is unbounded by this contract.** If the matrix produces too many EDGE_CASEs, the review JSON becomes unwieldy. Mitigation: tune thresholds inward (e.g., make ACCEPT require both VOI≥0.70 and classifier≥0.50). Track via the `EDGE_CASE / candidates_processed` ratio in the report.
4. **No appeal path.** A REJECT is terminal — there's no mechanism to revisit. Future phases could add a "re-review" step but Phase 4 does not.
5. **PDF-extract rows always get the default VOI.** Their `discovered_query` is NULL because PDFs don't carry query provenance. This means PDF-derived candidates compete on a uniformly-low VOI floor with each other; only the classifier signal differentiates them.

---

## Change Log

- **1.0.0 (2026-05-31)** — Initial release. SC-T1 through SC-T12. Balanced strictness locked. Decision matrix: 2D over classifier (0.20 / 0.50 boundaries) and VOI (0.50 / 0.70 boundaries) → 4-way bucket. EDGE_CASE export separate. `created_by='abstract_triage'` for consistency with Stage 1.
