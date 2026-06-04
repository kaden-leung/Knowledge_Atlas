# Track 2 · Task 3 · Phase 5 — Detailed Plan

**Author:** Kaden Leung
**Date:** 2026-05-27 (v1.0)
**Status:** Plan (no code written yet — awaiting approval before execution)
**Depends on:** Phase 4 (reads `triage_decision='ACCEPT'` rows from `article_references`)

---

## 0 · One-line summary

For every ACCEPT row in `v_acquisition_queue` (ordered by `voi_score DESC`), attempt PDF acquisition via a three-source cascade: Unpaywall → OpenAlex OA URL → scidownl (policy-gated). Record each attempt and outcome in `article_references` and `lifecycle_transitions`.

---

## 1 · Scope & boundaries

### In scope for Phase 5

1. `pdf_acquirer.py` — reads `v_acquisition_queue`, drives the three-source cascade per row.
2. `pdf_download_utils.py` — shared HTTP downloader that follows redirects, validates the response is actually a PDF (checks `Content-Type` and magic bytes), writes to disk.
3. `policy_clearance.json.example` — documented stub; must exist and be countersigned to enable scidownl.
4. PDF output directory: `Phase 5/acquired_pdfs/{reference_id}.pdf`.
5. DB updates: `pdf_acquisition_attempts`, `pdf_acquisition_last_source`, `acquired_paper_id`, `triage_stage → 'acquired'` or `'acquisition_failed'`.
6. `lifecycle_transitions` rows per cascade step.
7. `acquisition_results.json` output artifact.
8. Mock-mode (fixture PDF bytes, no HTTP) and dry-run (in-memory SQLite + skips disk writes).
9. Tests: 28 tests across 2 test files.

### Explicitly NOT in Phase 5

- AE corpus ingestion (Phase 7 will hand ACCEPT PDFs to the Eater; Phase 5 only acquires the file).
- `papers` table schema change — Phase 5 uses a synthetic `acquired_paper_id` (format `AQ-YYYY-MM-DD-NNNNNN`) stored as text; no FK enforcement until Phase 7.
- PRISMA dashboard (Phase 6).
- Re-attempting rows from previous runs that already have `acquired_paper_id` set.

---

## 2 · File tree

```
Track 2/Task 3/Phase 5/
├── PHASE_5_PLAN.md
├── pdf_acquirer.py           # cascade orchestrator
├── pdf_download_utils.py     # HTTP downloader + PDF validator
├── policy_clearance.json.example  # documented stub
├── acquired_pdfs/            # created at runtime, gitignored
├── fixtures/
│   ├── mock_pdf_bytes.pdf    # 3-page valid PDF fixture
│   ├── mock_unpaywall_oa.json
│   ├── mock_openalex_oa.json
│   └── acquisition_test_rows.json  # 8 article_references rows
├── test_pdf_acquirer.py
├── test_pdf_download_utils.py
└── acquisition_results.json  # written at runtime
```

---

## 3 · `v_acquisition_queue` contract (from Phase 3 migrations)

The view is defined in `Phase 3/migrations/003_v_acquisition_queue.sql`:

```sql
CREATE VIEW IF NOT EXISTS v_acquisition_queue AS
SELECT *
FROM article_references
WHERE triage_decision = 'ACCEPT'
  AND acquired_paper_id IS NULL
  AND pdf_acquisition_attempts < 3
ORDER BY COALESCE(voi_score, 0.0) DESC;
```

Phase 5 reads this view unmodified. The `pdf_acquisition_attempts < 3` guard limits retries.

---

## 4 · Cascade design

### Source 1: Unpaywall

```python
uw = UnpaywallClient(email="kaden-leung@users.noreply.github.com")  # imported from Article_Eater
result = uw.check_oa_status(doi)
if result["is_oa"] and result["best_oa_url"]:
    pdf_bytes = download_pdf(result["best_oa_url"])
    if pdf_bytes:
        return AcquisitionResult(source="unpaywall", pdf_bytes=pdf_bytes)
```

- **Precondition:** `doi` must be non-null (rows without DOI skip Unpaywall entirely).
- **Rate limit:** 0.5s polite delay built into `UnpaywallClient.check_oa_status()`.

### Source 2: OpenAlex OA URL

OpenAlex `/works/doi:{doi}` response contains `open_access.oa_url` (direct PDF link when available) and `open_access.any_repository_has_fulltext`. Reuse `OpenAlexClient` from Phase 4:

```python
# openalex_client.py gains one new method in Phase 5:
def fetch_oa_url(self, doi: str) -> str | None:
    """GET /works/doi:{doi}  →  open_access.oa_url or None."""
```

This is a one-line addition to the Phase 4 `OpenAlexClient`; it does not change the Phase 4 interface contract. Phase 5 imports `OpenAlexClient` from `Phase 4/openalex_client.py` via `sys.path.insert`.

- **Precondition:** `doi` non-null.
- **Rate limit:** 0.12s (inherited from Phase 4 `_RateLimiter`).

### Source 3: scidownl (policy-gated)

All four conditions must hold before a single scidownl call:

| Condition | Check location |
|---|---|
| `config.enable_paid_or_grey_sources == True` | `AcquirerConfig.enable_paid_or_grey_sources` (YAML / CLI flag) |
| `policy_clearance.json` present in `Phase 5/` | `Path("Phase 5/policy_clearance.json").exists()` |
| Both Unpaywall and OpenAlex OA failed for this row in current run | In-memory tracking during cascade |
| `triage_decision == 'ACCEPT'` (EDGE_CASE excluded) | Inherited from `v_acquisition_queue` definition |

```python
from scidownl import scihub_download   # pip3 install scidownl

scihub_download(doi, paper_type="doi", out=str(output_pdf_path))
# scidownl writes the file; we then validate it with is_valid_pdf()
```

If `policy_clearance.json` is absent: the cascade stops at OpenAlex and logs `policy_gate_blocked` in `lifecycle_transitions`. No error is raised; the row remains eligible for retry on a future run when the gate is opened.

---

## 5 · `pdf_download_utils.py` contract

```python
def download_pdf(url: str, *, timeout: int = 30) -> bytes | None:
    """
    Download URL, follow redirects, return bytes if Content-Type is PDF or
    magic bytes are %PDF, else return None.
    """

def is_valid_pdf(data: bytes) -> bool:
    """Return True if data starts with b'%PDF'."""

def save_pdf(pdf_bytes: bytes, dest: Path) -> None:
    """Write bytes to dest; create parent dirs; overwrite if exists."""
```

**Redirect handling:** `urllib.request.urlopen` with `timeout`; follows redirects automatically. Cap at 5 redirects (detect via manual loop if needed).

**PDF validation:** check first 4 bytes == `b'%PDF'`. Reject HTML error pages masquerading as PDFs (common with publisher paywalls returning a login page).

---

## 6 · DB update contract

**Columns updated per cascade attempt:**

| Column | Updated when |
|---|---|
| `pdf_acquisition_attempts` | incremented every time a source is tried (even if failed) |
| `pdf_acquisition_last_source` | set to the last source actually tried (`unpaywall` / `openalex_oa` / `scidownl`) |
| `triage_stage` | → `'acquired'` on success; → `'acquisition_failed'` after 3 failed attempts |
| `acquired_paper_id` | set to `AQ-YYYY-MM-DD-NNNNNN` on success |
| `updated_at` | always |

`pdf_acquisition_attempts` counts **cascade attempts** (one per source tried per run), not per-row run counts. A row that tries Unpaywall + OpenAlex OA in one run gets `pdf_acquisition_attempts = 2`.

**`lifecycle_transitions` rows per cascade:**

| Event | `from_stage` | `to_stage` | `reason` | `created_by` |
|---|---|---|---|---|
| Unpaywall success | `triage_complete` | `acquired` | `pdf_acquired:unpaywall` | `pdf_acquirer` |
| Unpaywall miss / no DOI | `triage_complete` | `acquisition_attempted` | `unpaywall_miss:{reason}` | `pdf_acquirer` |
| OpenAlex OA success | `acquisition_attempted` | `acquired` | `pdf_acquired:openalex_oa` | `pdf_acquirer` |
| OpenAlex OA miss | `acquisition_attempted` | `acquisition_attempted` | `openalex_oa_miss` | `pdf_acquirer` |
| scidownl success | `acquisition_attempted` | `acquired` | `pdf_acquired:scidownl` | `pdf_acquirer` |
| scidownl policy blocked | `acquisition_attempted` | `acquisition_attempted` | `policy_gate_blocked` | `pdf_acquirer` |
| All 3 failed | `acquisition_attempted` | `acquisition_failed` | `all_sources_failed` | `pdf_acquirer` |

---

## 7 · `AcquisitionResult` dataclass

```python
@dataclass
class AcquisitionResult:
    reference_id: str
    source: str | None        # "unpaywall" | "openalex_oa" | "scidownl" | None (failed)
    acquired_paper_id: str | None  # "AQ-YYYY-MM-DD-NNNNNN" on success
    pdf_path: Path | None     # absolute path to saved file
    attempts: int             # number of sources tried this run
    error: str | None         # last error message if failed
    success: bool
```

---

## 8 · `AcquirerConfig` dataclass

```python
@dataclass
class AcquirerConfig:
    db_path: Path
    output_dir: Path                     # where PDFs are saved
    run_id: str
    enable_paid_or_grey_sources: bool = False   # scidownl gate condition 1
    max_rows: int | None = None          # cap for testing; None = all queue rows
    mock: bool = False
    mock_fixtures_dir: Path | None = None
    dry_run: bool = False
```

---

## 9 · `acquisition_results.json` schema v1.0.0

```jsonc
{
  "schema_version": "1.0.0",
  "run_id": "RUN-2026-05-27-180000",
  "generated_at": "...",
  "queue_size": 34,
  "processed": 34,
  "acquired": 22,
  "failed": 12,
  "source_breakdown": {
    "unpaywall": 14,
    "openalex_oa": 6,
    "scidownl": 0,
    "policy_gate_blocked": 2,
    "all_sources_failed": 12
  },
  "doi_missing_skipped": 5,
  "errors": [
    {
      "reference_id": "REF-2026-05-27-000007",
      "source_attempted": "unpaywall",
      "error": "HTTP 404: DOI not found"
    }
  ]
}
```

---

## 10 · Success conditions (SC-1 through SC-14)

| # | Condition | Verified by |
|---|---|---|
| SC-1 | All rows in `v_acquisition_queue` processed (or skipped with DOI-missing note) | `test_pdf_acquirer.py::test_processes_all_queue_rows` |
| SC-2 | Unpaywall tried first; cascade stops if Unpaywall returns valid PDF | `test_pdf_acquirer.py::test_unpaywall_first_source` |
| SC-3 | Rows without DOI skip Unpaywall and OpenAlex OA; logged as `no_doi_skipped` | `test_pdf_acquirer.py::test_no_doi_skips_unpaywall` |
| SC-4 | OpenAlex OA tried when Unpaywall fails | `test_pdf_acquirer.py::test_openalex_oa_tried_when_unpaywall_fails` |
| SC-5 | scidownl NOT called unless all 4 policy conditions hold | `test_pdf_acquirer.py::test_scidownl_gate_requires_all_4_conditions` |
| SC-6 | scidownl blocked when `policy_clearance.json` absent; logs `policy_gate_blocked` | `test_pdf_acquirer.py::test_scidownl_blocked_without_policy_file` |
| SC-7 | Saved PDF validates as actual PDF (magic bytes `%PDF`) | `test_pdf_download_utils.py::test_validates_pdf_magic_bytes` |
| SC-8 | HTML error page (login page) rejected by PDF validator | `test_pdf_download_utils.py::test_rejects_html_response` |
| SC-9 | `acquired_paper_id` set with `AQ-` prefix on success | `test_pdf_acquirer.py::test_acquired_paper_id_format` |
| SC-10 | `pdf_acquisition_attempts` increments per source tried | `test_pdf_acquirer.py::test_attempt_counter_increments` |
| SC-11 | `lifecycle_transitions` row written per cascade event with correct `created_by` | `test_pdf_acquirer.py::test_lifecycle_transitions_per_event` |
| SC-12 | Row with `pdf_acquisition_attempts >= 3` skipped by `v_acquisition_queue` | `test_pdf_acquirer.py::test_exhausted_rows_not_requeued` |
| SC-13 | Dry-run makes no disk writes and no DB writes | `test_pdf_acquirer.py::test_dry_run_no_disk_writes` |
| SC-14 | `acquisition_results.json` written and schema-valid | `test_pdf_acquirer.py::test_acquisition_results_schema` |

---

## 11 · Test plan (28 tests across 2 files)

### `test_pdf_download_utils.py` (8 tests)

| Test | What it verifies |
|---|---|
| `test_download_returns_bytes_on_200` | Successful GET → bytes returned |
| `test_download_follows_redirect` | 302 → final URL → bytes returned |
| `test_download_returns_none_on_404` | 404 → None |
| `test_validates_pdf_magic_bytes` | `b'%PDF...'` → `is_valid_pdf = True` |
| `test_rejects_html_response` | `b'<!DOCTYPE html>'` → `is_valid_pdf = False` |
| `test_rejects_empty_bytes` | `b''` → `is_valid_pdf = False` |
| `test_save_pdf_creates_parent_dirs` | Nested path auto-created |
| `test_save_pdf_overwrites_existing` | Pre-existing file replaced silently |

### `test_pdf_acquirer.py` (20 tests)

| Test | What it verifies |
|---|---|
| `test_processes_all_queue_rows` | `v_acquisition_queue` rows all consumed |
| `test_unpaywall_first_source` | Unpaywall mock returns PDF → cascade stops |
| `test_openalex_oa_tried_when_unpaywall_fails` | Unpaywall miss → OpenAlex tried |
| `test_cascade_stops_when_openalex_oa_succeeds` | OpenAlex success → scidownl not called |
| `test_no_doi_skips_unpaywall` | NULL doi → Unpaywall and OpenAlex skipped; logged |
| `test_scidownl_gate_requires_all_4_conditions` | Missing any 1 of 4 conditions → scidownl not called |
| `test_scidownl_blocked_without_policy_file` | No `policy_clearance.json` → `policy_gate_blocked` logged |
| `test_scidownl_called_when_all_conditions_met` | All 4 conditions + mock scidownl → `pdf_acquired:scidownl` |
| `test_acquired_paper_id_format` | Success → `acquired_paper_id` starts with `AQ-` |
| `test_attempt_counter_increments` | 2 sources tried → `pdf_acquisition_attempts = 2` |
| `test_all_sources_failed_status` | All 3 miss → `triage_stage = 'acquisition_failed'` |
| `test_lifecycle_transitions_per_event` | Each cascade event writes a transition row |
| `test_created_by_is_pdf_acquirer` | All transitions have `created_by = 'pdf_acquirer'` |
| `test_exhausted_rows_not_requeued` | Row with `pdf_acquisition_attempts = 3` absent from queue |
| `test_idempotent_on_acquired_rows` | `acquired_paper_id` already set → row not in queue → not touched |
| `test_dry_run_no_disk_writes` | dry_run → `acquired_pdfs/` directory empty after run |
| `test_dry_run_no_db_writes` | dry_run → real DB unchanged |
| `test_mock_mode_fixture_pdf_used` | mock=True → fixture bytes written to disk |
| `test_acquisition_results_schema` | Output JSON has all required keys |
| `test_max_rows_caps_queue` | `max_rows=3` → at most 3 rows processed |

---

## 12 · CLI entry point

```
python pdf_acquirer.py \
  --db        ../../task3_pipeline_lifecycle.db \
  --output    Phase 5/acquired_pdfs \
  --run-id    RUN-2026-05-27-180000 \
  --results   acquisition_results.json \
  [--enable-grey-sources]   \
  [--max-rows 10]           \
  [--mock]                  \
  [--dry-run]
```

`--enable-grey-sources` sets `enable_paid_or_grey_sources=True` in `AcquirerConfig`; still requires `policy_clearance.json`.

---

## 13 · Dependency audit

| Package | Status | Notes |
|---|---|---|
| `scidownl` | NOT installed | `pip3 install scidownl` before Phase 5 execution |
| `urllib` | stdlib | HTTP download + Unpaywall |
| `UnpaywallClient` | `Article_Eater/src/services/paper_fetcher.py:1186` | Imported via `sys.path.insert` |
| `OpenAlexClient` | `Track 2/Task 3/Phase 4/openalex_client.py` | Imported via `sys.path.insert`; gains `fetch_oa_url()` |

---

## 14 · Effort estimate

| Sub-task | Hours |
|---|---|
| `pdf_download_utils.py` | 1.0 |
| `pdf_acquirer.py` (cascade + DB updates + policy gate) | 3.0 |
| `policy_clearance.json.example` + docs | 0.5 |
| Fixtures (4 files) | 0.5 |
| `test_pdf_download_utils.py` (8 tests) | 1.0 |
| `test_pdf_acquirer.py` (20 tests) | 2.0 |
| `acquisition_results.json` schema + writer | 0.5 |
| Integration smoke test (end-to-end, dry-run) | 0.5 |
| **Total** | **~9 hr** |
