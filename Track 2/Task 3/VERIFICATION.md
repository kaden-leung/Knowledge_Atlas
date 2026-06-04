# Task 3 Verification Findings

This file records the review findings that changed the Task 3 submission from a
working search pipeline into a defensible grading artifact. The current
evaluated state is intentionally preserved: 1,193 triaged rows, 10 ACCEPT rows,
21 EDGE_CASE rows, 222 MISSING_ABSTRACT rows, and 940 REJECT rows.

## Manual-Review Summary

Task 3 is not asking only whether a script runs. It asks whether search,
abstract collection, triage, null-result handling, and the handoff boundary are
traceable. The numbered findings below show what was checked, what failed, how
it was corrected or bounded, and where the committed evidence lives.

1. Architecture keyword miss changed a real decision

   The original keyword logic matched `architecture` but missed
   `architectural`. That mattered: Djebbara 2019 was a relevant embodied-space
   paper whose abstract used the adjective form. After review, the matcher was
   broadened and the paper moved into the ACCEPT set. This is the strongest
   example that verification found a measurable recall problem rather than a
   cosmetic wording issue.

   Evidence: [PIPELINE_ANALYSIS.md](PIPELINE_ANALYSIS.md),
   [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md),
   [triage_results.json](triage_results.json)

2. `paperscraper` `.json` versus `.jsonl` bug was caught before being trusted

   The live Phase 2 search run showed `paperscraper` returning failures when
   the wrapper expected the wrong output shape. The failure rate was 100% in
   that run, so the source could not be counted as reliable until the
   file-format boundary was fixed and isolated. The final Task 3 evidence keeps
   the original live-yield numbers honest while documenting the fixed adapter
   and tests.

   Evidence: [MANIFEST.md](MANIFEST.md),
   [Phase 2/adapters/paperscraper_adapter.py](<Phase 2/adapters/paperscraper_adapter.py>),
   [Phase 2/test_adapters.py](<Phase 2/test_adapters.py>)

3. Corrupted abstract detection proved plausibility validation is required

   Verification found that an abstract can be syntactically present while still
   belonging to the wrong paper or topic. The Djebbara 2019 review exposed a
   corrupted abstract case, which is why Task 3 now treats abstract plausibility
   as a first-class check instead of accepting any non-empty abstract text as
   valid evidence.

   Evidence: [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md),
   [NULL_RESULTS_REPORT.md](NULL_RESULTS_REPORT.md),
   [FAILURE_ANALYSIS.md](FAILURE_ANALYSIS.md)

4. Null-query detection identified 2 of 10 gaps with no retrieval coverage

   The review separated classifier misses from retrieval misses. Two of the ten
   reviewed gap queries had no usable retrieval coverage, which means their
   failure mode is not triage quality but upstream search coverage. This is why
   the null-results report is part of the primary grading evidence.

   Evidence: [NULL_RESULTS_REPORT.md](NULL_RESULTS_REPORT.md),
   [RETRIEVAL_ABLATION.md](RETRIEVAL_ABLATION.md),
   [MANUAL_REVIEW_PACKET.md](MANUAL_REVIEW_PACKET.md)

5. `MISSING_ABSTRACT` is an explicit terminal state, not a silent reject

   The final triage output uses `MISSING_ABSTRACT` for papers that were found
   but could not be assigned a usable abstract. This prevents the pipeline from
   pretending that missing evidence is negative evidence. The current evaluated
   DB has 222 `MISSING_ABSTRACT` rows and keeps those rows visible in the
   funnel.

   Evidence: [triage_results.json](triage_results.json),
   [ka_topic_proposer.html](ka_topic_proposer.html),
   [VERIFICATION_ANSWERS.md](VERIFICATION_ANSWERS.md)

6. DOI hit-rate ambiguity was resolved with one authoritative final metric

   Earlier notes contained an intermediate 67.9% DOI-only abstract hit-rate
   snapshot. The final benchmark is 73.2% DOI-only coverage, and
   [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) is the authoritative
   source for that metric. The older number is retained only as a historical
   snapshot where needed.

   Evidence: [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md),
   [NULL_RESULTS_REPORT.md](NULL_RESULTS_REPORT.md)

7. Acquisition readiness and acquisition execution are deliberately separated

   The current evaluated queue contains 10 ACCEPT rows ready for acquisition.
   The live Phase 5 sample processed 3 rows and logged 9 acquisition transitions.
   It did not acquire PDFs from those evaluated rows because the sample papers
   were paywalled or lacked DOI/open-access resolution. The successful download
   path is separately proven in the live acquisition proof fixture.

   Evidence: [MANIFEST.md](MANIFEST.md),
   [Phase 5/acquisition_report.json](<Phase 5/acquisition_report.json>),
   [Phase 5/live_acquisition_proof.json](<Phase 5/live_acquisition_proof.json>)

8. The stale lifecycle DB is documented as non-authoritative

   The reviewed pipeline state is `task3_pipeline_lifecycle.db`. Older lifecycle
   artifacts are retained only as historical evidence and are not used as the
   grading source of truth. This avoids rematerializing stale data while still
   preserving the audit trail.

   Evidence: [MANIFEST.md](MANIFEST.md),
   [verify_track2_workflow.py](verify_track2_workflow.py)

9. The 67-candidate expansion run is experiment-only

   `RUN-20260603-020713` produced 67 candidates after dedupe in
   [Phase 2/search_results_new_templates.json](<Phase 2/search_results_new_templates.json>)
   using 6 SerpAPI credits and 6 scholarly queries. It intentionally has 0 rows
   in the evaluated DB. The graded state remains the precision-reviewed
   10-ACCEPT pipeline rather than a late, unreviewed expansion.

   Evidence: [RETRIEVAL_ABLATION.md](RETRIEVAL_ABLATION.md),
   [MANIFEST.md](MANIFEST.md),
   [Phase 2/search_results_new_templates.json](<Phase 2/search_results_new_templates.json>)

10. Task 2 query handoff is mirrored rather than re-invented

    Task 3 uses the Task 2 query outputs as the search seed set. This keeps the
    search execution task connected to the prior class contract and avoids a
    hidden prompt drift between tasks.

    Evidence: [inputs/query_results.json](inputs/query_results.json),
    [verify_track2_workflow.py](verify_track2_workflow.py)

11. Dependency portability is bounded

    The pipeline uses local `atlas_shared` code where needed and documents the
    expected dependency boundary. The verification scripts check imports and
    skip or isolate optional paths rather than making every machine look like
    the original development environment.

    Evidence: [DEPENDENCY_PORTABILITY.md](DEPENDENCY_PORTABILITY.md),
    [setup_verify.py](setup_verify.py)

12. Test isolation protects the committed evidence

    The verifier and test files are written so review checks do not require
    rerunning paid live search. This preserves reproducibility while avoiding
    accidental SerpAPI spend or DB churn during grading.

    Evidence: [TEST_ISOLATION_NOTE.md](TEST_ISOLATION_NOTE.md),
    [verify_track2_workflow.py](verify_track2_workflow.py),
    [Phase 4/test_abstract_eval.py](<Phase 4/test_abstract_eval.py>)

13. Article Eater handoff is a local contract proof

    The Phase 7 handoff validates exported artifact shape and local handoff
    readiness. It does not claim that the downstream Article Eater production
    service ingested the artifacts.

    Evidence: [AE_HANDOFF_BOUNDARY.md](AE_HANDOFF_BOUNDARY.md),
    [MANIFEST.md](MANIFEST.md),
    [verify_track2_workflow.py](verify_track2_workflow.py)

14. VOI is reported honestly as a narrow-range signal

    VOI scoring exists and is checked, but the current benchmark found a narrow
    score range. The final review treats VOI as supporting evidence rather than
    claiming it was the primary driver of accept/reject decisions.

    Evidence: [VOI_COMPARISON_NOTE.md](VOI_COMPARISON_NOTE.md),
    [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md)

15. The PRISMA dashboard is a pipeline funnel, not a formal systematic review

    The dashboard gives the reviewer a transparent view of search, abstract
    collection, triage, and acquisition states. It is PRISMA-inspired evidence
    for the class pipeline, not a claim that the project completed a full
    clinical-style PRISMA review.

    Evidence: [ka_topic_proposer.html](ka_topic_proposer.html),
    [MANUAL_REVIEW_PACKET.md](MANUAL_REVIEW_PACKET.md)

## Current Verification Commands

Run these from `Knowledge_Atlas/Track 2/Task 3` unless noted otherwise:

```bash
python3 verify_track2_workflow.py
```

Expected result:

```text
CHAIN: 9/9 checks passed
```

Run this from `Knowledge_Atlas`:

```bash
python3 160sp/autograders/t2_task3_grader.py 'Track 2/Task 3' kaden-leung
```

Expected result:

```text
Score: 68 / 75
Contract Gate: Passed
```
