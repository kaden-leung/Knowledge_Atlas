# Track 2 Task 3 — Internal Pilot Runbook

**Status:** GO WITH CONTROLS → target GO after all acceptance criteria below are met.
**Audience:** Operators running the pipeline in the full COGS-160 workspace with supervision.

---

## 1. Workspace Layout

The pipeline requires four sibling checkouts under one common root (the COGS-160 directory):

```
COGS 160/
├── Knowledge_Atlas/          ← this repo; Track 2/Task 3 lives here
├── Article_Finder/           ← ae_corpus_dedupe, HierarchicalClassifier
├── Article_Eater/            ← paper_fetcher clients (S2/CrossRef/PubMed), voi_scoring
└── atlas_shared/             ← optional semantic classifier weights
    └── src/
```

If `atlas_shared` is absent, Stage 1 and Stage 2B fall back to the keyword classifier automatically.

---

## 2. Environment Setup

```bash
# 1. Clone or pull sibling repos if not present
# 2. Activate the full-workspace environment
source "../Article_Finder/.venv/bin/activate"
python -m pip install -r "Track 2/Task 3/requirements.txt"

# 3. Copy .env.example and fill in your keys
cp "Track 2/Task 3/.env.example" "Track 2/Task 3/.env"
# Edit .env: SERPAPI_KEY=<your-key>  NCBI_API_KEY=<optional>

# 4. Verify pr-only tier (no sibling repos needed)
python3 "Track 2/Task 3/setup_verify.py" --mode pr-only
# Expected: all PASS, exit 0

# 5. Verify full tier (requires sibling repos + packages)
python3 "Track 2/Task 3/setup_verify.py" --mode full
# Expected: all PASS or WARN on optional NCBI key only
```

---

## 3. Capacity and Credit Budget

| Resource | Limit | Notes |
|---|---|---|
| SerpAPI | 250 credits/month | 10 credits per full 10-query run; 25 full runs/month |
| SerpAPI per-run cap | 50 credits | Hard-coded in `search_runner.py` |
| scholarly | Unlimited | Rate-limited to ≥5 s/query |
| paperscraper | Unlimited | arXiv only; require `.jsonl` extension (post-fix adapter) |
| S2 abstract | ~3.1 s/request | Unauthenticated; 429 → 30 s wait |
| PubMed abstract | 0.34 s/request | With NCBI_API_KEY; 3 req/s without |
| Expected wall time | ~25 min | 10-query run with 300 abstract candidates |

---

## 4. Offline Verification (no API keys required)

Run from `Knowledge_Atlas/`:

```bash
# One-command evidence chain check
python3 "Track 2/Task 3/verify_track2_workflow.py"
# Expected: CHAIN: 10/10 checks passed

# Offline test suite
cd "Track 2/Task 3"
python3 -m pytest -q
# Expected: all offline suites pass; only the explicitly live network test skips

# Autograder
python3 160sp/autograders/t2_task3_grader.py "Track 2/Task 3" kaden-leung
# Expected: 68 / 75, Contract Gate: Passed
```

---

## 5. Safe Live Run Sequence

**Do this in order. Do not skip steps.**

```bash
cd "Track 2/Task 3"

# Step 0: create and migrate a runtime DB copy
cp task3_pipeline_lifecycle.db runtime-pilot.db
python3 "Phase 3/migrate.py" --db runtime-pilot.db

# Step 1: dry-run search (no credits spent, no DB writes)
python3 Phase\ 2/search_runner.py --dry-run
# Review planned query list; confirm SerpAPI credit estimate

# Step 2: live search (costs credits; use --confirm-live to permit)
python3 Phase\ 2/search_runner.py --confirm-live
# Output: Phase 2/search_results.json

# Step 3: load search results into DB
python3 Phase\ 3/db_loader.py \
  --search-results "Phase 2/search_results.json" \
  --db runtime-pilot.db

# Step 4: harvest PDF references (uses local PDFs, no network)
python3 Phase\ 3/reference_harvester.py --db runtime-pilot.db

# Step 5: Stage 1 triage
python3 Phase\ 4/stage1_metadata_triage.py --db runtime-pilot.db

# Step 6: abstract collection (network; slow ~25 min for 300 rows)
python3 Phase\ 4/abstract_collector.py --db runtime-pilot.db --live

# Step 7: Stage 2B triage decision
python3 Phase\ 4/stage2b_triage_decision.py --db runtime-pilot.db

# Step 8: HUMAN REVIEW (required before acquisition)
# Review all ACCEPT rows using the ACCEPT set in triage_results.json
# Create human_review_log.json (see §6 below) and policy_clearance.json

# Step 9: PDF acquisition (blocked by review gate until §6 is complete)
python3 Phase\ 5/pdf_acquirer.py \
  --db runtime-pilot.db \
  --run-id RUN-PILOT-YYYYMMDD-HHMMSS

# Step 10: AE handoff
python3 Phase\ 7/ae_handoff.py --db runtime-pilot.db
```

---

## 6. Human Review Gate

Before Phase 5 (PDF acquisition) can run on a live DB, two files must exist:

**`policy_clearance.json`** (in `Phase 5/`):
```json
{
  "human_reviewer_sign_off": true,
  "sign_off_date": "YYYY-MM-DD",
  "expires_on": "YYYY-MM-DD",
  "reviewer": "course-reviewer",
  "approved_run_id": "RUN-PILOT-YYYYMMDD-HHMMSS",
  "decision": "APPROVED",
  "reviewer_notes": "Reviewed the complete ACCEPT queue for this run."
}
```

**`human_review_log.json`** (in `Track 2/Task 3/`):
```json
{
  "reviewed_papers": [
    {
      "reference_id": "REF-2026-05-30-000006",
      "reviewer_verdict": "approved",
      "reviewer_notes": "Djebbara 2021 — core CNFA paper."
    },
    ...one entry per ACCEPT row...
  ]
}
```

The gate checks:
1. `human_reviewer_sign_off: true`
2. Reviewer, notes, decision, approved run ID, sign-off date, and expiration are valid
3. The sign-off is not future-dated or expired
4. Every ACCEPT row has an approved verdict with nonempty notes

If any condition fails, Phase 5 exits with code 1 before any network call or DB write.

---

## 7. DB Reset / Copy Procedure

**Never overwrite the committed evidence DB directly.** Use one of these patterns:

```bash
# Pattern A: work on a fresh copy for a new run
cp task3_pipeline_lifecycle.db runtime-pilot.db
python3 "Phase 3/migrate.py" --db runtime-pilot.db
# Point pipeline commands at the dated copy

# Pattern B: reset a working copy to the committed state
rm runtime-pilot.db runtime-pilot.db-shm runtime-pilot.db-wal 2>/dev/null || true
cp task3_pipeline_lifecycle.db runtime-pilot.db
python3 "Phase 3/migrate.py" --db runtime-pilot.db

# Pattern C: fresh DB from migrations (no prior data)
python3 Phase\ 3/migrate.py --db fresh_run.db
# Load fresh data using the run-sequence above
```

---

## 8. Known Limitations at Pilot Stage

| Limitation | Status | Impact |
|---|---|---|
| HierarchicalClassifier not present | Keyword fallback active | Precision ~50-70%; false positives from architecture-adjacent papers |
| 2/10 queries return zero API results | Documented in NULL_RESULTS_REPORT.md | 2 of 10 targeted gaps have no retrieval coverage |
| paperscraper: 0 live results in committed run | Bug fixed, no post-fix live evidence committed | Three sources claimed; two demonstrated |
| AE handoff: local stub only | Phase 7 validates schema locally | Not a real AE ingestion smoke test |
| Acquisition: 0 PDFs from evaluated ACCEPT set | DOIs are paywalled; scidownl gated off | Download path proven separately on known-OA DOI |

---

## 9. Pilot GO Acceptance Criteria

| Criterion | Status |
|---|---|
| `setup_verify.py --mode pr-only` exits 0 | ✅ Implemented |
| `setup_verify.py --mode full` passes (WARN on NCBI only) | ✅ Implemented |
| Human review gate blocks Phase 5 without sign-off | ✅ Implemented |
| `verify_track2_workflow.py` passes 10/10 | ✅ Confirmed |
| PILOT_RUNBOOK.md exists | ✅ This document |
| Null queries: 0/10 on production branch | ⬜ Pending query reformulation |
| Post-fix paperscraper evidence committed | ⬜ Pending live run |
| Classifier eval ≥ 50 labeled abstracts | ⬜ Pending (Phase 4) |
| CI workflow defined | ⬜ Pending (Phase 3C) |
