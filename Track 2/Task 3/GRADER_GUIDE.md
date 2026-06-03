# Track 2 Grader Guide

**Start here.** This guide is the fastest path through the submission.

---

## 1. What this project is

This submission is a gap-driven literature discovery pipeline for the cognitive neuroscience of architecture (CNFA).

Task 2 supplies the search intent: it extracts epistemic gaps from the upstream knowledge system and converts them into targeted Boolean and AI-Citation queries. Task 3 then executes those queries, triages the results, and hands off accepted papers to a downstream consumer.

The central finding supported by the evaluation:

**Retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.**

---

**If you have 5 minutes:**
1. Read this file — architecture, navigation, one-command verification
2. Read [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) — all key metrics, error taxonomy, per-paper precision assessment
3. Read [PROVEIT_WORKS.md](PROVEIT_WORKS.md) — one paper traced through all 10 lifecycle stages

Those three documents capture the architecture, evaluation, validation, and limitations of the project. Everything else is supporting detail.

---

## 2. Pipeline architecture

```text
TASK 2 — Gap Extraction + Query Generation
  Article_Eater knowledge base (CNFA frameworks)
      |
      v  [gap_extractor.py]
  Identified epistemic gaps (VOI-scored, gap-typed, fingerprinted)
      |
      v  [query_generator.py]
  Boolean + AI-Citation queries  →  query_results.json

TASK 3 — Literature Discovery Pipeline
  query_results.json
      |
      v  [search_runner.py]
  SerpAPI / scholarly / paperscraper  →  search_results.json
      |
      v  [db_loader.py + reference_harvester.py]
  article_references  (1,193 candidates, incl. PDF-harvested)
      |
      v  [stage1_metadata_triage.py]
  Stage 1 metadata screen  (904 rejected; 289 to Stage 2A)
      |
      v  [abstract_collector.py]
  Stage 2A abstract collection  S2 → CrossRef → PubMed → OpenAlex
      |
      v  [stage2b_triage_decision.py]
  Stage 2B triage decision  (10 ACCEPT, 21 EDGE_CASE, 36 REJECT)
      |
      v  [pdf_acquirer.py]
  v_acquisition_queue  →  Unpaywall → OpenAlex OA → scidownl (gated)
      |
      v  [ae_handoff.py]
  handoff_outbox/*.json  (9 artifacts exported)
      |
      v  [ae_inbox_stub.py]
  AE validation  →  9/9 valid, 0 invalid
```

All stages log atomic transitions to `lifecycle_transitions`. Every row in `article_references` can be traced from first discovery through final decision.

---

## 3. One-command verification

```bash
cd "Track 2/Task 3"
python3 verify_track2_workflow.py
```

Expected output: `CHAIN: 9/9 checks passed` (verified from a clean checkout — the DB and evidence files it reads are committed).

**Authoritative database:** the committed `Track 2/Task 3/task3_pipeline_lifecycle.db` is the single source of truth for verification. (A separate `Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db` exists as a course-path placeholder but is an earlier, stale materialization — it is not used here. See [MANIFEST.md](MANIFEST.md) → "Authoritative database for Task 3 verification".)

**The committed database is a reproducibility artifact used by verification; it is not meant to be regenerated during grading.** No live run, API key, or SerpAPI credit is needed to verify — `verify_track2_workflow.py` reads the committed evidence and passes 9/9 as-is. The `run_pipeline.py` regeneration command below is optional and only for re-deriving evidence from a fresh pipeline run.

To regenerate all evidence artifacts:

```bash
python3 run_pipeline.py --mode all-evidence
```

Task 2 (gap extraction + query generation) is delivered as a **separate submission**
(branch `track2/kaden-leung-task2`). Task 3 consumes only Task 2's query output, which is
vendored here as a committed input at [inputs/query_results.json](<inputs/query_results.json>)
— see [inputs/QUERY_PROVENANCE.md](<inputs/QUERY_PROVENANCE.md>). Task 3 therefore verifies
self-contained, with no dependency on a sibling Task 2 directory.

---

## 4. Fastest document review path

Three documents cover the full submission:

1. This file — architecture, navigation, one-command verification
2. [TRACK2_EVALUATION_REPORT.md](TRACK2_EVALUATION_REPORT.md) — benchmark, recall, precision, error taxonomy, ablation, retrieval-bottleneck finding
3. [PROVEIT_WORKS.md](PROVEIT_WORKS.md) — one paper traced end-to-end through all 10 lifecycle stages including AE handoff

Supporting references:

- [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) — authoritative metric table (cite this for all numbers; full methodology in TRACK2_EVALUATION_REPORT.md)
- [FAILURE_ANALYSIS.md](FAILURE_ANALYSIS.md) — failure modes connected into one measurement → discovery → action story
- [LESSONS_LEARNED.md](LESSONS_LEARNED.md) — what evaluation changed about the project
- [HUMAN_VALIDATION.md](HUMAN_VALIDATION.md) — manual precision review and threshold sensitivity
- [NULL_RESULTS_REPORT.md](NULL_RESULTS_REPORT.md) — 2 null queries and 225 MISSING_ABSTRACT rows, documented
- [MANIFEST.md](MANIFEST.md) — single-page audit trail for Task 3
- Task 2 deliverables and autograder result — in the separate Task 2 submission (branch `track2/kaden-leung-task2`)
- [Phase 7/handoff_outbox/handoff_manifest.json](<Phase 7/handoff_outbox/handoff_manifest.json>) — downstream-ready export evidence

---

## 5. Implemented vs demonstrated

| Component | Implemented | Demonstrated | Evidence |
|---|---|---|---|
| Task 2 gap extraction | Yes | Yes | Task 2 submission (separate PR) |
| Task 2 query generation | Yes | Yes | [inputs/query_results.json](<inputs/query_results.json>) (vendored) |
| Retrieval pipeline | Yes | Yes | [search_results.json](<Phase 2/search_results.json>) |
| DB buffer + lifecycle logging | Yes | Yes | task3_pipeline_lifecycle.db |
| Stage 1 triage | Yes | Yes | [MANIFEST.md](MANIFEST.md) |
| Stage 2A abstract collection | Yes | Yes | [HUMAN_VALIDATION.md](HUMAN_VALIDATION.md) |
| Stage 2B triage | Yes | Yes | [PROVEIT_WORKS.md](PROVEIT_WORKS.md) |
| PDF acquisition logic | Yes | Ran live — 9 transitions, 0 PDFs from the evaluated set (paywalled); **download path proven on a known-OA DOI** (734 KB PLOS PDF, %PDF-validated, SHA-256) | [STAGE3_EVIDENCE_AUDIT.md §8](STAGE3_EVIDENCE_AUDIT.md) |
| AE handoff layer | Yes | Yes, local validation | [handoff_manifest.json](<Phase 7/handoff_outbox/handoff_manifest.json>) |
| One-command wrapper | Yes | Yes | [run_pipeline.py](run_pipeline.py) |
| Chain verifier | Yes | Yes — 9/9 | [verify_track2_workflow.py](verify_track2_workflow.py) |

---

## 6. What this submission provides beyond the rubric

The rubric requires: query generation, search, triage, and PDF acquisition.

This submission additionally provides:

| Addition | Evidence document |
|---|---|
| 30-paper gold-standard benchmark corpus | [CNFA_GOLD_STANDARD.md](CNFA_GOLD_STANDARD.md) |
| Retrieval recall measured against benchmark | [TRACK2_EVALUATION_REPORT.md §4](TRACK2_EVALUATION_REPORT.md) |
| ACCEPT precision — manual relevance assessment | [HUMAN_VALIDATION.md](HUMAN_VALIDATION.md) |
| Error taxonomy — failure mode decomposition | [FAILURE_ANALYSIS.md](FAILURE_ANALYSIS.md) |
| Query ablation study (K=1,3,5,8,9) | [TRACK2_EVALUATION_REPORT.md §6.1](TRACK2_EVALUATION_REPORT.md) |
| VOI–ACCEPT correlation (negative finding) | [TRACK2_EVALUATION_REPORT.md §6.2](TRACK2_EVALUATION_REPORT.md) |
| Baseline query comparison | [TRACK2_EVALUATION_REPORT.md §6.3](TRACK2_EVALUATION_REPORT.md) |
| End-to-end chain verifier (9/9 checks) | [verify_track2_workflow.py](verify_track2_workflow.py) |
| Downstream handoff + AE validation layer | [Phase 7/ae_handoff.py](<Phase 7/ae_handoff.py>), [ae_inbox_stub.py](<Phase 7/ae_inbox_stub.py>) |

---

## 7. Known limits

- Task 3 PDF acquisition ran live (9 lifecycle transitions) but acquired 0 PDFs — the candidate DOIs are paywalled and scidownl is policy-gated. The stage is demonstrated; no open PDF was available for the rows attempted.
- The local handoff layer exports 9 valid artifacts; 1 ACCEPT row is withheld because it lacks a usable abstract.
- The demonstrated classifier is keyword fallback, not the intended semantic classifier.
- Task 2 reproducibility depends on a local Article_Eater checkout (not bundled).
- The AE handoff is local stub validation, not production AE ingestion.

The strongest evaluation claim is about retrieval coverage: the pipeline correctly identifies and stages papers for its targeted gaps; it does not cover the broader CNFA literature because it was not given queries that cover it.

## 8. Scope boundary — what happens after AE handoff

This submission ends at AE inbox validation (`ae_inbox_stub.py`): an ACCEPT row becomes a schema-validated handoff artifact that the local stub accepts or rejects. The natural next stage — the real Article Eater ingesting the artifact, deduplicating against its live inventory, and indexing the paper into the knowledge base — is **out of scope for this submission**. The handoff layer is deliberately a local validation boundary, not production AE integration; it proves the artifact is well-formed and consumable, without claiming the downstream AE pipeline was exercised.
