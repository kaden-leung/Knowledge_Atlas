# PDF Acquisition Contract — Phase 5

**Track 2 · Task 3 · Phase 5**
**Author:** Kaden Leung
**Contract Version:** 1.0.0
**Last Updated:** 2026-06-01

---

## 1. System Summary

Phase 5 is the final stage before the Knowledge Atlas receives a paper. It reads every row from `v_acquisition_queue` (ACCEPT + no PDF yet, sorted by VOI descending) and walks a strict 3-source cascade until it either downloads a valid PDF or exhausts all sources. It never downloads a PDF for a row that is not ACCEPT — the view enforces this. It never invokes scidownl without explicit human approval through a 4-condition policy gate.

Every attempt is recorded in `pdf_acquisition_attempts` (count) and `pdf_acquisition_last_source` (last source tried). On success, `acquired_paper_id` is stamped and the row leaves the queue. On failure through all sources, the row remains in the queue with attempts incremented for the dashboard's "wanted-but-unobtainable" bucket.

---

## 2. Source cascade

Tried in strict order. Stop at the first success.

| Step | Source | Notes |
|---|---|---|
| 1 | **Unpaywall** | Reuses `Article_Finder/ingest/pdf_downloader.py:UnpaywallClient`. Free, legal, license-clean. Always tried first. |
| 2 | **OpenAlex OA URL** | Uses `Phase 4/openalex_client.py:OpenAlexClient.get_oa_pdf_url()`. Free, license-clean. Tried only when Step 1 fails. |
| 3 | **scidownl** | Tried only when Steps 1+2 both fail **AND** the 4-condition policy gate in §5 passes. Last resort. |

---

## 3. Inputs

### 3.1 From `v_acquisition_queue`

Each row: `reference_id`, `doi`, `title_raw`, `voi_score`, `pdf_acquisition_attempts`, `pdf_acquisition_last_source`, `discovery_run_id`.

Only rows where `triage_decision = 'ACCEPT'` and `acquired_paper_id IS NULL` appear in this view. EDGE_CASE and REJECT rows never receive acquisition attempts.

### 3.2 Configuration (`phase5_config.yaml`)

| Key | Default | Meaning |
|---|---|---|
| `acquisition.email` | `kaden-leung@users.noreply.github.com` | Polite-pool email for Unpaywall and OpenAlex |
| `acquisition.output_dir` | `Phase 5/acquired_pdfs` | Where PDFs are saved (gitignored) |
| `acquisition.timeout_seconds` | `60` | Per-request download timeout |
| `enable_paid_or_grey_sources` | `false` | Must be `true` before scidownl is even considered |

### 3.3 Policy clearance file (`policy_clearance.json`)

Must exist **and be countersigned by the instructor** before scidownl can run (see §5). If the file is absent or `enable_paid_or_grey_sources=false`, scidownl is blocked unconditionally.

---

## 4. Processing

For each row in `v_acquisition_queue` (ordered by `voi_score DESC`, `created_at ASC`):

1. Increment `pdf_acquisition_attempts += 1`, set `pdf_acquisition_last_source = 'unpaywall'`.
2. Call `UnpaywallClient.get_pdf_url(doi)`. If URL found, attempt download.
3. If Unpaywall succeeds: verify PDF header (`%PDF`), save, stamp `acquired_paper_id`, log `acquisition_unpaywall:success`.
4. If Unpaywall fails: set `pdf_acquisition_last_source = 'openalex'`, call `OpenAlexClient.get_oa_pdf_url(doi)`. Attempt download if URL found.
5. If OpenAlex succeeds: verify, save, stamp, log `acquisition_openalex:success`.
6. If OpenAlex fails: check policy gate (§5). If gate passes, attempt scidownl.
7. If scidownl succeeds: verify, save, stamp, log `acquisition_scidownl:success`.
8. If all sources fail: log `acquisition_failed_all_sources`, leave row in queue.

PDF file naming: `{reference_id}.pdf` in `output_dir`. On collision (same reference_id re-tried): overwrite.

---

## 5. scidownl Policy Gate (4 conditions — ALL must be satisfied)

```python
def _scidownl_gate_passes(row, config, policy_clearance_path,
                          unpaywall_failed, openalex_failed):
    if not config.get("enable_paid_or_grey_sources", False):
        return False, "config:enable_paid_or_grey_sources is false"
    if not policy_clearance_path.exists():
        return False, "policy_clearance.json missing or not countersigned"
    if not (unpaywall_failed and openalex_failed):
        return False, "cascade not exhausted"
    if row["triage_decision"] != "ACCEPT":
        return False, f"row is {row['triage_decision']}, not ACCEPT"
    return True, "all four conditions met"
```

**Condition 1 (`enable_paid_or_grey_sources`):** Config file defaults to `false`. Must be manually flipped to `true`. Do not flip without instructor approval. Flipping without a countersigned clearance file still blocks scidownl (Condition 2 blocks independently).

**Condition 2 (policy clearance file):** `policy_clearance.json` must exist in the project directory and be countersigned. A TEMPLATE file is committed; the real signed file is never committed (gitignored). Talk to your instructor before obtaining the signed file.

**Condition 3 (cascade exhaustion):** scidownl is last-resort only. Both free sources must have been attempted and failed for this specific row in this run.

**Condition 4 (ACCEPT only):** EDGE_CASE rows are explicitly excluded from scidownl even if the other conditions are met. EDGE_CASE means uncertain triage; uncertain papers do not warrant policy-grey access.

---

## 6. Outputs

### 6.1 DB updates per row

| Column | On success | On failure |
|---|---|---|
| `pdf_acquisition_attempts` | incremented | incremented |
| `pdf_acquisition_last_source` | last source tried | last source tried |
| `acquired_paper_id` | `"{reference_id}-PDF"` | unchanged (NULL) |
| `updated_at` | UTC `YYYY-MM-DDTHH:MM:SSZ` | UTC `YYYY-MM-DDTHH:MM:SSZ` |

### 6.2 `lifecycle_transitions`

One row per attempt step (not per row). Reason format: `acquisition_{source}:{success|fail}`. `created_by='pdf_acquirer'`.

Examples:
- `acquisition_unpaywall:success`
- `acquisition_unpaywall:fail_no_oa_url`
- `acquisition_openalex:fail_http_403`
- `acquisition_scidownl:blocked_policy_gate`
- `acquisition_failed_all_sources`

### 6.3 `acquisition_report.json`

```json
{
  "schema_version": "1.0.0",
  "run_id": "RUN-P5-...",
  "started_at": "...",
  "ended_at": "...",
  "rows_processed": 6,
  "acquired": {"unpaywall": 0, "openalex": 0, "scidownl": 0},
  "failed_all_sources": 6,
  "scidownl_gate_blocked": 6,
  "errors": []
}
```

---

## 7. Invariants

- **I-1.** Only ACCEPT rows are processed (view enforces `triage_decision='ACCEPT'`).
- **I-2.** `pdf_acquisition_attempts` is incremented before any source is tried; it reflects total attempts including failures.
- **I-3.** `acquired_paper_id` is only set after a downloaded file passes the `%PDF` header check.
- **I-4.** scidownl is never called without all 4 gate conditions being satisfied. No code path bypasses the gate.
- **I-5.** Every source attempt writes a `lifecycle_transitions` row. No silent fallthrough.
- **I-6.** `--dry-run` writes nothing to disk (no PDF files, no DB changes).
- **I-7.** Rows that fail all sources remain in `v_acquisition_queue` and are surfaced by the dashboard as "wanted-but-unobtainable."

---

## 8. Success Conditions

| SC | Statement | Test |
|---|---|---|
| SC-P1 | Only ACCEPT rows processed; EDGE_CASE/REJECT ignored | `test_only_accept_rows_processed` |
| SC-P2 | Unpaywall tried first; OpenAlex tried second on Unpaywall miss | `test_unpaywall_miss_falls_through_to_openalex` |
| SC-P3 | Every attempt increments `pdf_acquisition_attempts` | `test_acquisition_attempts_incremented` |
| SC-P4 | `acquired_paper_id` only set after `%PDF` header verified | `test_corrupt_pdf_treated_as_failure` |
| SC-P5 | Failed rows stay in `v_acquisition_queue` | `test_failed_rows_remain_in_queue` |
| SC-P6 | scidownl never called when gate is false | `test_all_free_sources_fail_policy_gate_blocks` |
| SC-P7 | scidownl blocked when clearance file absent | `test_scidownl_blocked_without_clearance_file` |
| SC-P8 | scidownl blocked for EDGE_CASE rows | `test_scidownl_blocked_for_edge_case` |
| SC-P9 | scidownl called when all 4 gate conditions met | `test_scidownl_called_when_gate_passes` |
| SC-P10 | Every attempt writes `lifecycle_transitions` | `test_lifecycle_transitions_written_per_attempt` |
| SC-P11 | Unpaywall success → acquired_paper_id set, row leaves queue | `test_unpaywall_hit_acquires_pdf` |
| SC-P12 | `--dry-run` writes nothing | `test_dry_run_no_disk_writes` |

---

## 9. Non-Goals

- Does NOT run triage decisions (Phase 4).
- Does NOT extract text from PDFs (Phase 6+).
- Does NOT import PDFs into the Article Eater Knowledge Base (Phase 7).
- Does NOT attempt acquisition for EDGE_CASE rows, even if they are close to ACCEPT.
- Does NOT commit `policy_clearance.json` to git (gitignored; template only).
- Does NOT set `enable_paid_or_grey_sources=true` without explicit instructor sign-off.

---

## 10. Known Limitations

1. **No abstract-extracted DOIs for many PDF-extract rows.** Several ACCEPT rows come from the PDF reference harvester with `discovered_via='review_pdf_extract'` and lack DOIs (or have corrupt short DOIs already cleaned by the truncated-DOI fix). Unpaywall and OpenAlex both require a DOI; without one, both fail immediately and the row goes straight to the scidownl gate check (which also fails, since the gate is off by default). (This contract was written against the pre-fix 6-row queue; the queue now holds 10 ACCEPT rows. The bounded live run of 2026-06-02 processed 3 rows: 0 PDFs acquired — 2 DOI rows paywalled, 1 row no-DOI — see STAGE3_EVIDENCE_AUDIT.md.)
2. **scidownl availability.** Sci-Hub mirrors change URLs frequently. `scihub_download()` tries to auto-select a working mirror; this may fail silently. Always check the `lifecycle_transitions` record for the specific error.
3. **Unpaywall rate limit.** 10 req/sec; already enforced by `UnpaywallClient._rate_limit()`. Safe for a 6-row queue.

---

## Change Log

- **1.0.0 (2026-06-01)** — Initial release. SC-P1 through SC-P12. 3-source cascade: Unpaywall → OpenAlex OA → scidownl (gate-blocked). Aligned with course spec §5A–5C and scidownl 4-condition policy gate.
