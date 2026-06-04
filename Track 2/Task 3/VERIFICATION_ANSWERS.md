# Verification Answers — concise mapping for graders

Date: 2026-06-04

This file provides direct, short answers to common verification questions a grader will ask, with pointers to the exact evidence in the submission.

1) How are search results collected?
- Answer: The submission provides a root-level shim `search_runner.py` that delegates to the Phase 2 implementation and executes the Task 2 queries found in `inputs/query_results.json`.
- Evidence:
  - [Track 2/Task 3/search_runner.py](Track 2/Task 3/search_runner.py)
  - [Track 2/Task 3/Phase 2/search_runner.py](Track 2/Task 3/Phase 2/search_runner.py)
  - Query inputs: [Track 2/Task 3/inputs/query_results.json](Track 2/Task 3/inputs/query_results.json)
  - One-command verification: [Track 2/Task 3/GRADER_GUIDE.md](Track 2/Task 3/GRADER_GUIDE.md)

2) How are abstracts collected?
- Answer: The collector implements a fallback chain (Semantic Scholar → CrossRef → PubMed → OpenAlex) and is exposed via `abstract_collector.py` in the submission root which delegates to `Phase 4` code.
- Evidence:
  - Submission shim: [Track 2/Task 3/abstract_collector.py](Track 2/Task 3/abstract_collector.py)
  - Phase implementation: [Track 2/Task 3/Phase 4/abstract_collector.py](Track 2/Task 3/Phase 4/abstract_collector.py)
  - Fallback chain documented: [Track 2/Task 3/TRACK2_EVALUATION_REPORT.md](Track 2/Task 3/TRACK2_EVALUATION_REPORT.md#abstract-collection)

3) How are papers triaged and represented?
- Answer: Triage decisions are produced by the Stage 2B triage logic and written to `triage_results.json` (submission root). Decisions include `ACCEPT`, `EDGE_CASE`, `REJECT`, `MISSING_ABSTRACT`, and `DUPLICATE`.
- Evidence:
  - Triager output: [Track 2/Task 3/triage_results.json](Track 2/Task 3/triage_results.json)
  - Triage code: [Track 2/Task 3/Phase 4/stage2b_triage_decision.py](Track 2/Task 3/Phase 4/stage2b_triage_decision.py)
  - Autograder check: see the `Abstract triage` section of the autograder output (autograder run included in PR materials)

4) Where is the PRISMA funnel/dashboard?
- Answer: The PRISMA-inspired dashboard is exported as an HTML artifact named `ka_topic_proposer.html` under the Knowledge_Atlas apps path.
- Evidence:
  - Dashboard: [Knowledge_Atlas/160sp/apps/ka_topic_proposer.html](Knowledge_Atlas/160sp/apps/ka_topic_proposer.html)
  - Regeneration script: [Track 2/Task 3/Phase 6/generate_prisma_report.py](Track 2/Task 3/Phase 6/generate_prisma_report.py)

5) How are MISSING_ABSTRACT cases handled?
- Answer: Rows that cannot be resolved to an abstract are recorded with `triage_decision = 'MISSING_ABSTRACT'` and remain in `article_references` for later review; they are not treated as pipeline errors.
- Evidence:
  - Summary report: [Track 2/Task 3/NULL_RESULTS_REPORT.md](Track 2/Task 3/NULL_RESULTS_REPORT.md)
  - Lifecycle verifier: [Track 2/Task 3/verify_track2_workflow.py](Track 2/Task 3/verify_track2_workflow.py)
  - Example lifecycle rows: open the DB `Track 2/Task 3/task3_pipeline_lifecycle.db` (committed) and inspect the `lifecycle_transitions` table

6) How can a grader reproduce the one-command verification?
- Answer: From a clean checkout, run the single verifier that reads committed evidence (no network or API keys required):

```bash
cd "Track 2/Task 3"
python3 verify_track2_workflow.py    # → CHAIN: 9/9 checks passed
```

7) Where is the evidence for the two autograder manual-review items?
- Answer: Both manual-review topics are documented and cross-linked below.
  - Manual review packet: [Track 2/Task 3/MANUAL_REVIEW_PACKET.md](Track 2/Task 3/MANUAL_REVIEW_PACKET.md)
  - `Null results + MISSING_ABSTRACT` evidence: [Track 2/Task 3/NULL_RESULTS_REPORT.md](Track 2/Task 3/NULL_RESULTS_REPORT.md)
  - `Verification questions` / failure analysis: [Track 2/Task 3/FAILURE_ANALYSIS.md](Track 2/Task 3/FAILURE_ANALYSIS.md) and [Track 2/Task 3/TRACK2_EVALUATION_REPORT.md](Track 2/Task 3/TRACK2_EVALUATION_REPORT.md)

---

## Quick Missing-Abstracts summary (for graders)

- Stage 2A rows processed in this run: **289**
- Abstracts successfully collected in the current DB: **68**
- `MISSING_ABSTRACT` rows in the current DB: **222**
- DOI-bearing rows entering Stage 2A: **56**
- DOI rows with abstracts collected: **38**
- DOI-only abstract coverage (final measured): **73.2%** (see [BENCHMARK_EVALUATION.md](Track 2/Task 3/BENCHMARK_EVALUATION.md) — authoritative)

Primary reasons for `MISSING_ABSTRACT`:
- No DOI / noisy citation text (majority)
- Valid DOI but not indexed by fallback sources
- Truncated or malformed DOI strings
- API rate-limiting during collection attempts

See also: [Track 2/Task 3/NULL_RESULTS_REPORT.md](Track 2/Task 3/NULL_RESULTS_REPORT.md) (detailed breakdown)
