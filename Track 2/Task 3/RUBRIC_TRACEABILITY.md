# Rubric Traceability Matrix

This matrix maps major Track 2 requirements to concrete evidence in the repository.

| Rubric requirement | Evidence | File |
|---|---|---|
| Gap extraction | 554-gap output, contract, manifest | [Track 2/Task 2/Phase 2/gap_results.json](<../Task 2/Phase 2/gap_results.json>) |
| Query generation | 10 query pairs, contract, verification log | [Track 2/Task 2/Phase 3/query_results.json](<../Task 2/Phase 3/query_results.json>) |
| Verification questions | 17 caught problems in generator implementation | [Track 2/Task 2/Phase 4/VERIFICATION.md](<../Task 2/Phase 4/VERIFICATION.md>) |
| Retrieval pipeline | Live run over 10 Task 2 queries, 84 candidates after dedupe | [Track 2/Task 3/Phase 2/search_results.json](<Phase 2/search_results.json>) |
| DB candidate buffer | 1,193 rows in `article_references` | [task3_pipeline_lifecycle.db](task3_pipeline_lifecycle.db) |
| Reference harvesting | 20 PDFs harvested into shared DB buffer | [MANIFEST.md](MANIFEST.md) |
| Stage 1 triage | Metadata screening + lifecycle transitions | [MANIFEST.md](MANIFEST.md) |
| Stage 2A abstract collection | Fallback chain and collected abstracts | [HUMAN_VALIDATION.md](HUMAN_VALIDATION.md) |
| Stage 2B triage | ACCEPT decisions and queue population | [PROVEIT_WORKS.md](PROVEIT_WORKS.md) |
| Null results + `MISSING_ABSTRACT` | Documented as expected terminal states | [NULL_RESULTS_REPORT.md](NULL_RESULTS_REPORT.md) |
| Evaluation / benchmark | 30-paper benchmark, error taxonomy, ablation, baseline | [TRACK2_EVALUATION_REPORT.md](TRACK2_EVALUATION_REPORT.md) |
| Benchmark entry point | Alias that points to the single authoritative benchmark report | [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) |
| Human validation | Manual precision review of ACCEPT set | [HUMAN_VALIDATION.md](HUMAN_VALIDATION.md) |
| Reproducibility / setup verification | Environment check script | [setup_verify.py](setup_verify.py) |
| End-to-end validation command | Artifact and DB evidence checks | [verify_track2_workflow.py](verify_track2_workflow.py) |
| One-command evidence wrapper | Regenerates local handoff/dashboard evidence, then verifies chain | [run_pipeline.py](run_pipeline.py) |
| Acquisition stage | Implemented; ran live 2026-06-02 (9 transitions, 0 PDFs — paywalled DOIs) | [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>) |
| Downstream handoff validation | 9 exported artifacts, 9 validated, 1 skipped for missing abstract | [Phase 7 handoff_manifest.json](<Phase 7/handoff_outbox/handoff_manifest.json>) |
