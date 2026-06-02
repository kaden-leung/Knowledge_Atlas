# Stage 1 Metadata Triage Contract — Phase 4 Sub-phase 4A

**Track 2 · Task 3 · Phase 4**
**Author:** Kaden Leung
**Contract Version:** 1.0.0
**Last Updated:** 2026-05-31

---

## 1. System Summary

Stage 1 metadata triage runs **before any abstract is fetched**. It walks each `triage_stage='metadata_only'` row in `article_references`, applies cheap-and-cheap-only rules to the row's metadata (title, venue, DOI presence), and rejects the rows that are obviously noise. Surviving rows advance to `triage_stage='abstract_pending'` and become inputs to Sub-phase 4B (abstract collection).

The course rule this stage enforces: **never download a PDF — and never even spend a Semantic Scholar request — to find out you don't want the paper.** The 30–50 % of harvested rows that are JSTOR footers, PDF font artifacts, generic short titles, or off-topic noise must die here, free, before any API quota is consumed.

---

## 2. Inputs

### 2.1 From `article_references`

Each row where `triage_stage = 'metadata_only'` is a candidate. The triage reads:

| Column | Type | Used for |
|---|---|---|
| `reference_id` | TEXT | Lookup + transition logging |
| `title_raw` | TEXT (may be `""`) | Noise-regex and classifier inputs |
| `doi` | TEXT or NULL | Tightens the "title too short" rule — having a DOI saves a short title from rejection |
| `venue` | TEXT or NULL | Reserved for classifier input |

### 2.2 Configuration

| Parameter | Default | Meaning |
|---|---|---|
| `db_path` | `Track 2/Task 3/task3_pipeline_lifecycle.db` | Local DB |
| `run_id` | required | Stamped on every transition row |
| `threshold` | `0.20` | Classifier confidence below this → REJECT (per course spec) |
| `dry_run` | `False` | Process in-memory copy of the DB only |

### 2.3 External classifier (reused, with fallback)

The classifier is loaded lazily:
1. Try to import `HierarchicalClassifier` from `Article_Finder/triage/classifier.py`
2. Try to load `Article_Finder/triage/.centroids.pkl`
3. Try to import `sentence-transformers` (the embedding backend)
4. If any step fails → fall back to a **keyword-based** classifier built into this module (CNFA keyword set)

The keyword fallback ensures Stage 1 runs in any Python environment, including those without `sentence-transformers`.

---

## 3. Processing

For each `metadata_only` row, in order:

### 3.1 Cheap noise-regex check (free, no classifier call)

The first rule that fires wins. All write `triage_decision='REJECT'`, `triage_stage='rejected_at_metadata'`.

| Rule | Reason token |
|---|---|
| `title_raw` is empty or whitespace-only | `noise:empty_title` |
| `title_raw` starts with `"This content downloaded from"` (case-insensitive) | `noise:jstor_footer` |
| `title_raw` matches `"All use subject to https://about.jstor.org/terms"` | `noise:jstor_terms` |
| `title_raw` contains `(cid:` (PDF font artifact) | `noise:pdf_cid_artifact` |
| `title_raw` has fewer than 4 significant words (≥ 3 chars each) AND `doi` is NULL | `noise:title_too_short_no_doi` |
| `title_raw` matches `^\d{1,3}\s*[-./]\s*\d{1,3}$` (page number ranges captured as titles) | `noise:page_range_artifact` |
| `title_raw` matches `^https?://\S+$` (URL-only line) | `noise:url_only` |

These six rules together should catch the dominant noise from Phase 3 DEDUPE_SPOTCHECK §"Follow-up for Phase 4".

### 3.2 Classifier check (only for survivors of §3.1)

```python
decision, confidence = classifier.classify_paper(title=title_raw, venue=venue, abstract=None)
```

- `confidence < 0.20` → `triage_decision='REJECT'`, `triage_stage='rejected_at_metadata'`, reason `classifier_below_threshold:{conf:.2f}`
- `confidence >= 0.20` → `triage_stage='abstract_pending'`, reason `stage1_passed:{conf:.2f}` (no triage_decision yet — Stage 2B decides)

### 3.3 Keyword fallback (when classifier unavailable)

The keyword check counts overlap with this CNFA keyword set:

```python
CNFA_KEYWORDS = {
    "architecture", "spatial", "built environment", "building", "buildings",
    "cognition", "cognitive", "arousal", "restoration", "attention",
    "wayfinding", "threshold", "façade", "facade", "cortisol", "stress",
    "psychophysiolog", "neural", "fMRI", "EEG", "EDA", "circadian",
    "navigation", "place", "memory", "emotion", "affect",
    "predictive", "coding", "interoception", "embodied", "multisensory",
}
```

Confidence policy:
- `0+ keywords` → REJECT (confidence=0.0) — though typically all rows have at least one match
- `1–2 keywords` → confidence=0.25 (just above threshold but flagged for Stage 2B review)
- `3+ keywords` → confidence=0.50 (clear pass)

This is intentionally conservative — the goal of Stage 1 is to *reject obvious noise*, not to *grade* candidates. Stage 2B does the real classification on the abstract.

### 3.4 DB write (per row, in one transaction)

```sql
UPDATE article_references
   SET triage_stage = ?,                  -- 'rejected_at_metadata' or 'abstract_pending'
       triage_decision = ?,               -- 'REJECT' or NULL (pass)
       triage_reason = ?,                 -- reason token
       classifier_confidence = ?,         -- 0.0 to 1.0 (NULL for noise-regex rejects that bypass classifier)
       updated_at = ?
 WHERE reference_id = ?
   AND triage_stage = 'metadata_only';    -- idempotency guard

INSERT INTO lifecycle_transitions
   (reference_id, run_id, from_stage, to_stage, reason, created_by)
   VALUES (?, ?, 'metadata_only', ?, ?, 'abstract_triage');
```

Idempotency: the `WHERE triage_stage = 'metadata_only'` clause means re-running Stage 1 on already-triaged rows is a no-op. Tests verify.

---

## 4. Outputs

### 4.1 DB updates (per candidate)

| Column | REJECT (noise-regex) | REJECT (classifier) | PASS |
|---|---|---|---|
| `triage_stage` | `rejected_at_metadata` | `rejected_at_metadata` | `abstract_pending` |
| `triage_decision` | `REJECT` | `REJECT` | unchanged (`NULL`; 4D will fill) |
| `triage_reason` | `noise:<token>` | `classifier_below_threshold:0.NN` | `stage1_passed:0.NN` |
| `classifier_confidence` | `NULL` | float | float |
| `updated_at` | UTC `YYYY-MM-DDTHH:MM:SSZ` | (same) | (same) |

### 4.2 `lifecycle_transitions`

One per processed row. `created_by='abstract_triage'`.

### 4.3 `stage1_triage_report.json`

```json
{
  "schema_version": "1.0.0",
  "run_id": "RUN-...",
  "started_at": "2026-...Z",
  "ended_at":   "2026-...Z",
  "candidates_processed": 1193,
  "passed_to_stage2a": 600,
  "rejected_total": 593,
  "rejection_rate": 0.497,
  "reject_reasons": {
    "noise:jstor_footer": 5,
    "noise:jstor_terms": 5,
    "noise:pdf_cid_artifact": 12,
    "noise:title_too_short_no_doi": 320,
    "noise:empty_title": 1,
    "noise:url_only": 8,
    "noise:page_range_artifact": 4,
    "classifier_below_threshold:0.00-0.19": 238
  },
  "classifier_mode": "hierarchical | keyword_fallback",
  "errors": []
}
```

---

## 5. Non-Goals

- **No abstract fetch.** Stage 1 makes zero network requests.
- **No PDF download.** Phase 5.
- **No `triage_decision='ACCEPT'`** writes here. Only `REJECT` (terminal) or leave NULL (passes to Stage 2A/B).
- **No `discovered_via` mutation.** Source provenance is set at insert time and never changed.
- **No new row inserts.** Stage 1 only UPDATEs.

---

## 6. Definitions

### 6.1 Significant word
A whitespace-delimited token of length ≥ 3 characters after stripping punctuation. Used by the "title too short" rule (§3.1 row 5).

### 6.2 Noise
Text that the PDF reference harvester captured as a reference but is actually PDF boilerplate (footers, page-numbers, URL-only lines, font artifacts). Identified by the 6 regex rules in §3.1.

### 6.3 CNFA keyword
A domain term tied to *Cognitive Neuroscience of Architecture* — the topic area COGS-160 indexes. Used by the keyword fallback when the real classifier is unavailable.

### 6.4 Pass / Reject
Per-candidate decision. `Pass` advances the row to `abstract_pending`; `Reject` is terminal and sets `triage_decision='REJECT'`.

---

## 7. Invariants

- **I-1.** Every `metadata_only` row in the input set reaches one of two end states: `rejected_at_metadata` (terminal) or `abstract_pending` (advances to 4B). No silent drops.
- **I-2.** Every UPDATE is paired with one `lifecycle_transitions` INSERT in the same transaction.
- **I-3.** Every `lifecycle_transitions` row from this module has `created_by='abstract_triage'`.
- **I-4.** No HTTP request is issued by this module.
- **I-5.** The `WHERE triage_stage='metadata_only'` clause on the UPDATE makes Stage 1 idempotent across reruns.
- **I-6.** Every emitted timestamp matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`.

---

## 8. Success Conditions

| SC | Statement | Test |
|---|---|---|
| SC-1 | Empty `title_raw` is rejected with reason `noise:empty_title`. | `test_empty_title_rejected` |
| SC-2 | "This content downloaded from …" is rejected with reason `noise:jstor_footer`. | `test_jstor_footer_rejected` |
| SC-3 | Title containing `(cid:` is rejected with reason `noise:pdf_cid_artifact`. | `test_cid_artifact_rejected` |
| SC-4 | Title with < 4 significant words AND `doi IS NULL` is rejected with reason `noise:title_too_short_no_doi`. | `test_short_title_no_doi_rejected` |
| SC-5 | Title with < 4 words BUT with a DOI is **not** rejected by the short-title rule. | `test_short_title_with_doi_kept` |
| SC-6 | Classifier confidence below 0.20 → REJECT with reason `classifier_below_threshold:*`. | `test_classifier_low_confidence_rejected` |
| SC-7 | Classifier confidence ≥ 0.20 → PASS, `triage_stage='abstract_pending'`. | `test_classifier_above_threshold_passes` |
| SC-8 | Keyword fallback is used when `HierarchicalClassifier` import fails. | `test_keyword_fallback_used_when_classifier_unavailable` |
| SC-9 | Re-running Stage 1 on already-triaged rows is a no-op (idempotency guard). | `test_idempotent_on_already_triaged` |
| SC-10 | `dry_run=True` makes no on-disk writes. | `test_dry_run_no_disk_writes` |
| SC-11 | Every processed candidate produces one `lifecycle_transitions` row with `created_by='abstract_triage'`. | `test_one_transition_per_candidate_correct_writer` |
| SC-12 | The `stage1_triage_report.json` `passed + rejected` equals `candidates_processed` (no silent drops). | `test_report_counts_balance` |

---

## 9. Known Limitations

1. **Keyword fallback is anglocentric.** Non-English titles get few CNFA keyword matches even if the paper is on-topic. They'll cluster around 0–2 keywords and either reject or barely pass.
2. **The "first-fire wins" rule in §3.1.** If a title hits multiple noise regexes, only the first one is recorded. Order matters: empty-title check fires first, then JSTOR-prefix, etc.
3. **DOI rescue for short titles.** A row with a 2-word title and a DOI is kept; it gets a chance at Stage 2B with the help of an abstract. This is intentional — DOI-bearing rows have higher prior probability of being a real paper.
4. **`classifier_confidence` is comparable across modes.** Both `HierarchicalClassifier` and the keyword fallback emit floats in `[0, 1]`. They are NOT cross-mode-calibrated — a 0.50 from keywords doesn't mean the same thing as a 0.50 from centroids. The `classifier_mode` field in the report distinguishes them.
5. **No retry on classifier failures.** If the classifier raises an exception on a row, that row's transition records `reason='classifier_error:<exc>'` and the row stays in `metadata_only` for retry on a later run.

---

## Change Log

- **1.0.0 (2026-05-31)** — Initial release. SC-1 through SC-12. Six noise-regex rules calibrated to Phase 3 DEDUPE_SPOTCHECK findings. Classifier threshold 0.20 per course spec.
