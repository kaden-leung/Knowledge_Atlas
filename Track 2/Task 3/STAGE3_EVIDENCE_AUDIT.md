# Stage 3 Evidence Audit

**Date:** 2026-06-02  
**Scope:** Acquisition-readiness and acquisition evidence in the current repository snapshot  
**Purpose:** Distinguish what is implemented from what is actually demonstrated

## 1. Verdict

Stage 3 acquisition logic is implemented and dry-run evidenced, but it is **not live-demonstrated** in the current verified DB state.

That means the safe claim is:

- `ACCEPT` papers are queued and acquisition-ready
- Phase 5 acquisition code exists
- dry-run acquisition behavior has evidence
- no live acquisition transitions are currently recorded

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
| Lifecycle transitions with acquisition-style reasons | 0 | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| Phase 6 `acquisition_summary.in_queue` | 10 | [Phase 6/prisma_dashboard_data.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 6/prisma_dashboard_data.json>) |
| Phase 6 `acquisition_summary.acquired` | 0 | [Phase 6/prisma_dashboard_data.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 6/prisma_dashboard_data.json>) |
| Phase 6 `acquisition_summary.failed` | 0 | [Phase 6/prisma_dashboard_data.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 6/prisma_dashboard_data.json>) |
| Phase 5 dry-run `rows_processed` | 6 | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |
| Phase 5 dry-run predicted Unpaywall acquisitions | 4 | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |

## 4. Implemented vs demonstrated

| Component | Implemented | Demonstrated | Evidence |
|---|---|---|---|
| Queue formation from `ACCEPT` rows | Yes | Yes | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| Phase 5 acquisition logic | Yes | Yes, dry-run | [Phase 5/acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>) |
| Live acquisition attempt logging | Yes, in design | No | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| Live acquired PDF evidence | No verified evidence in current snapshot | No | [Phase 6/prisma_dashboard_data.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 6/prisma_dashboard_data.json>) |

## 5. What this means for grading

Safe interpretation:

- The system reaches acquisition readiness.
- The system proves that accepted papers can be queued.
- The system has dry-run evidence that the acquisition layer can evaluate candidate rows.

Unsafe interpretation:

- The repo does **not** currently prove that a live PDF was acquired during the verified run state.
- The repo does **not** currently prove downstream handoff beyond the local queue and evaluation artifacts.

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

## 7. Recommendation

If the rubric requires live acquisition evidence, run a tightly bounded live demonstration on 1-2 queued rows and log the result explicitly.

If the rubric does not require that, keep the current wording:

- acquisition-ready state is demonstrated
- dry-run acquisition evidence exists
- live acquisition remains unverified in the current snapshot
