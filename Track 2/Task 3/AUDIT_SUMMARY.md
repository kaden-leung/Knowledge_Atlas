# Track 2 Audit Summary

**Date:** 2026-06-02  
**Scope:** Repository-state audit for `Track 2/Task 3` (Task 2 is delivered as a separate submission, branch `track2/kaden-leung-task2`)  
**Method:** Verified against current files, current DB state, and current validation commands

## 1. Project thesis

Evaluation showed that retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.

This submission is strongest when presented as a gap-driven retrieval and evaluation system, not just a pipeline demo.

## 2. Verified current state

| Area | Verified state | Main evidence |
|---|---|---|
| Task 2 role | Task 2 supplies the search intent for Task 3 by converting epistemic gaps into Boolean queries; its query output is vendored here | [inputs/query_results.json](<inputs/query_results.json>), [TRACK2_ARCHITECTURE.md](TRACK2_ARCHITECTURE.md) |
| Task 2 reproducibility | Gap extraction wrapper and run guide ship with the Task 2 submission | Task 2 submission (separate PR, branch `track2/kaden-leung-task2`) |
| Retrieval | 10 queries ran, 84 candidates remained after dedupe, 2 queries returned zero results | [Phase 2/search_results.json](<Phase 2/search_results.json>), [NULL_RESULTS_REPORT.md](NULL_RESULTS_REPORT.md) |
| DB buffer | `article_references` currently contains 1,193 rows | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| Lifecycle logging | DB currently contains 2,748 lifecycle transitions, including 1,226 `abstract_triage` and 294 `abstract_collector` transitions | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| Triage outcome | 10 rows are `ACCEPT` and 10 rows appear in `v_acquisition_queue` | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db), [PROVEIT_WORKS.md](PROVEIT_WORKS.md) |
| Acquisition evidence | Phase 5 ran live 2026-06-02: 3 rows processed, 9 acquisition transitions in DB, 0 PDFs acquired (both DOI rows paywalled; scidownl gated) | [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>), [STAGE3_EVIDENCE_AUDIT.md](STAGE3_EVIDENCE_AUDIT.md) |
| Downstream handoff | 9 downstream-ready artifacts were exported and validated; 1 ACCEPT row was skipped for missing abstract | [Phase 7 handoff_manifest.json](<Phase 7/handoff_outbox/handoff_manifest.json>), [Phase 7 inbox_validation_report.json](<Phase 7/handoff_outbox/inbox_validation_report.json>) |
| Metric authority | `BENCHMARK_EVALUATION.md` is the single authoritative source for benchmark metric values | [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) |
| Methodology authority | The 30-paper evaluation report is authoritative for benchmark methodology and full analysis | [TRACK2_EVALUATION_REPORT.md](TRACK2_EVALUATION_REPORT.md) |
| One-command verification | The repo now has a canonical evidence-check command that passes on the current snapshot | [verify_track2_workflow.py](verify_track2_workflow.py) |
| One-command evidence wrapper | The repo now has a thin wrapper for regenerating local evidence and rerunning verification | [run_pipeline.py](run_pipeline.py) |

## 3. What is already strong

- Task 2 has a strong contract and verification story, and now has a cleaner run path.
- Task 3 has a strong end-to-end evidence story: retrieval, DB loading, Stage 1, Stage 2A, Stage 2B, evaluation, and lifecycle traceability.
- The benchmark and validation package is unusually strong for a class project because it includes human review, failure analysis, ablation, and an explicit dominant bottleneck finding.
- [LESSONS_LEARNED.md](LESSONS_LEARNED.md) now captures the evaluation-driven changes without duplicating benchmark metrics.
- The submission now has grader-facing navigation through [GRADER_GUIDE.md](GRADER_GUIDE.md), [TRACK2_ARCHITECTURE.md](TRACK2_ARCHITECTURE.md), and [RUBRIC_TRACEABILITY.md](RUBRIC_TRACEABILITY.md).

## 4. What is still limited

- Phase 5 acquisition stage ran live (2026-06-02): 9 transitions logged. No PDFs acquired — both DOI-bearing rows are paywalled and scidownl is policy-gated.
- The AE handoff layer now exists as a local validation path, not as an external integrated consumer.
- `run_pipeline.py` exists as a thin evidence wrapper; live search still requires an explicit `--confirm-live` gate.
- Task 2 still depends on the sibling `Article_Eater` checkout, so portability is improved but not fully self-contained.
- The repo contains multiple evaluation documents, but authority is unambiguous: `BENCHMARK_EVALUATION.md` owns metric values, `TRACK2_EVALUATION_REPORT.md` owns methodology, and `GRADER_GUIDE.md` is the entry point.

## 5. Claims that are safe to make

- The pipeline executes through retrieval, triage, queue formation, and evaluation on the current repo snapshot.
- The submission has verified `ACCEPT` rows and verified acquisition-ready rows in `v_acquisition_queue`.
- The submission has verified downstream handoff artifacts for 9 of the 10 current `ACCEPT` rows.
- Evaluation showed that retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.
- Phase 5 acquisition stage is live-demonstrated (9 DB transitions). No PDF was successfully downloaded because the candidate DOIs are paywalled.

## 6. Claims that should not be made

- Do not claim PDFs were successfully acquired — the acquisition stage ran live but downloaded nothing (paywalled DOIs + scidownl gated).
- Do not claim external production integration beyond the local handoff validation layer.
- Do not describe `EVALUATION_REPORT.md` and `TRACK2_EVALUATION_REPORT.md` as co-equal benchmark authorities.
- Do not imply Task 3 is a generic literature search pipeline; its intended value depends on Task 2 supplying the search intent.

## 7. Recommended execution order from here

1. Keep [GRADER_GUIDE.md](GRADER_GUIDE.md), [TRACK2_ARCHITECTURE.md](TRACK2_ARCHITECTURE.md), and [RUBRIC_TRACEABILITY.md](RUBRIC_TRACEABILITY.md) as the main grader path.
2. Treat [TRACK2_EVALUATION_REPORT.md](TRACK2_EVALUATION_REPORT.md) as the benchmark authority.
3. Use [STAGE3_EVIDENCE_AUDIT.md](STAGE3_EVIDENCE_AUDIT.md) to keep the acquisition claim honest and precise.
4. Only build downstream handoff artifacts if the rubric or grader value clearly justifies them.

## 8. Fresh-grader check

A fresh grader should now be able to:

- find the entry point from [GRADER_GUIDE.md](GRADER_GUIDE.md)
- understand Task 2 -> Task 3 flow from [TRACK2_ARCHITECTURE.md](TRACK2_ARCHITECTURE.md)
- locate benchmark evidence from [TRACK2_EVALUATION_REPORT.md](TRACK2_EVALUATION_REPORT.md)
- verify the chain with `python3 verify_track2_workflow.py`
- regenerate local evidence and verify it with `python3 run_pipeline.py --mode all-evidence`
- understand the acquisition limitation from [STAGE3_EVIDENCE_AUDIT.md](STAGE3_EVIDENCE_AUDIT.md)
