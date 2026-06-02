# Stage 3 Evidence Audit

**Date:** 2026-06-02  
**Scope:** Acquisition-readiness and acquisition evidence in the current repository snapshot  
**Purpose:** Distinguish what is implemented from what is actually demonstrated

## 1. Verdict

Stage 3 acquisition logic is implemented and **live-demonstrated**: Phase 5 ran live on 2026-06-02 (run `RUN-P5-20260602-192128`) and logged **9 acquisition lifecycle transitions** across 3 queued rows. **0 PDFs were acquired** — the DOI-bearing rows are paywalled (Unpaywall/OpenAlex returned no OA URL) and scidownl is policy-gated.

That means the safe claim is:

- `ACCEPT` papers are queued and acquisition-ready
- Phase 5 acquisition code exists and **was executed live**
- live acquisition attempts are logged in `lifecycle_transitions` (9 transitions)
- no PDF was successfully downloaded, because the attempted DOIs are paywalled and the grey-source fallback (scidownl) is correctly gated off

## 2. Evidence inspected

- [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>)
- [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>)
- [Phase 6/prisma_dashboard_data.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 6/prisma_dashboard_data.json>)
- [verify_track2_workflow.py](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/verify_track2_workflow.py>)
- [PROVEIT_WORKS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/PROVEIT_WORKS.md>)

## 3. Verified current counts

| Check | Result | Source |
|---|---|---|
| `article_references` rows | 1,193 | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| `triage_decision='ACCEPT'` rows | 10 | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| `v_acquisition_queue` rows | 10 | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| Lifecycle transitions with acquisition-style reasons | 9 | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| Phase 6 `acquisition_summary.in_queue` | 10 | [Phase 6/prisma_dashboard_data.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 6/prisma_dashboard_data.json>) |
| Phase 6 `acquisition_summary.acquired` | 0 | [Phase 6/prisma_dashboard_data.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 6/prisma_dashboard_data.json>) |
| Phase 5 live `rows_processed` | 3 | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |
| Phase 5 live PDFs acquired | 0 | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |
| Phase 5 live rows blocked at scidownl gate | 2 | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |
| Phase 5 live rows with no DOI | 1 | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |

## 4. Implemented vs demonstrated

| Component | Implemented | Demonstrated | Evidence |
|---|---|---|---|
| Queue formation from `ACCEPT` rows | Yes | Yes | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| Phase 5 acquisition logic | Yes | Yes, live | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |
| Live acquisition attempt logging | Yes | Yes — 9 transitions | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| Live acquired PDF evidence | N/A — attempted DOIs are paywalled | No PDF acquired (expected) | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |

## 5. What this means for grading

Safe interpretation:

- The system reaches acquisition readiness.
- The system proves that accepted papers can be queued.
- The acquisition layer was **run live** and logged 9 transitions evaluating candidate rows against Unpaywall, OpenAlex, and the scidownl policy gate.

Unsafe interpretation:

- The repo does **not** prove that a PDF was successfully *downloaded* — 0 PDFs were acquired because the attempted DOIs are paywalled and scidownl is gated off. The stage ran; the corpus simply had no open PDF for the attempted rows.

## 6. Commands used for this audit

Workflow check:

```bash
cd "Track 2/Task 3"
python3 verify_track2_workflow.py
```

DB spot-checks:

```bash
sqlite3 task3_pipeline_lifecycle.db \
  "select count(*) from article_references where triage_decision='ACCEPT';"

sqlite3 task3_pipeline_lifecycle.db \
  "select count(*) from v_acquisition_queue;"

sqlite3 task3_pipeline_lifecycle.db \
  "select count(*) from lifecycle_transitions where reason like 'acquisition_%' or reason like 'policy_gate_blocked%';"
```

## 7. Status

The tightly bounded live demonstration recommended here was **performed** on 2026-06-02: 3 queued rows were processed live (run `RUN-P5-20260602-192128`), producing 9 logged acquisition transitions. The result is recorded explicitly in `acquisition_report.json` and the DB.

Current honest wording:

- acquisition-ready state is demonstrated
- live acquisition was **executed and logged** (9 transitions)
- 0 PDFs acquired — attempted DOIs are paywalled and scidownl is policy-gated (an expected, correct outcome, not a failure)
