# Project Reconstruction

**Date:** 2026-06-02  
**Method:** Repository reconstruction from file contents, not filenames alone  
**Scope:** `Track 2/Task 2`, `Track 2/Task 3`, mirrored Task 2 files in `Knowledge_Atlas`, and the strongest existing evaluation/validation artifacts

## 1. What the system does

This project is a gap-driven literature discovery pipeline for the cognitive neuroscience of architecture (CNFA).

Task 2 is the source of search intent. It is not just a prelude to retrieval; it turns epistemic gaps into targeted retrieval questions that later phases cannot recover from if omitted.

The implemented story is:

Task 2:
- extract epistemic gaps
- assign VOI-style prioritization
- generate paired search queries

Task 3:
- run retrieval across scholarly sources
- load candidates into a shared DB buffer
- harvest additional references from local PDFs
- perform Stage 1 metadata triage
- collect abstracts through a fallback chain
- perform Stage 2B decision triage
- queue ACCEPT rows for acquisition
- generate reporting and evaluation artifacts

The strongest existing project claim is not merely that the pipeline runs. It is that the pipeline was evaluated and that the dominant observed failure mode is retrieval coverage, not downstream triage alone.

## 2. What is implemented

### Fully implemented and evidenced

- Task 2 gap extraction outputs and query generation outputs exist under [Track 2/Task 2/MANIFEST.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2/MANIFEST.md>).
- Task 2 query generation is contract-heavy and verification-heavy, with 17 documented verification questions in [VERIFICATION.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2/Phase 4/VERIFICATION.md>).
- Task 2 Phase 3 deliverables are mirrored into `Knowledge_Atlas/Track 2/Task 2/Phase 3/`, which partially solves discoverability.
- Task 3 search, DB loading, reference harvesting, triage, acquisition logic, and reporting code all exist and are documented in [MANIFEST.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/MANIFEST.md>).
- Task 3 setup verification already has a one-command script in [setup_verify.py](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/setup_verify.py>).
- End-to-end trace evidence exists in [PROVEIT_WORKS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/PROVEIT_WORKS.md>).
- Benchmark/evaluation artifacts exist in [TRACK2_EVALUATION_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/TRACK2_EVALUATION_REPORT.md>), [EVALUATION_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/EVALUATION_REPORT.md>), [HUMAN_VALIDATION.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/HUMAN_VALIDATION.md>), [PIPELINE_ANALYSIS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/PIPELINE_ANALYSIS.md>), and [NULL_RESULTS_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/NULL_RESULTS_REPORT.md>).
- [PROVEIT_WORKS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/PROVEIT_WORKS.md>) is especially valuable because it gives one lifecycle trace from gap source to ACCEPT.

### Implemented but only partially demonstrated

- `paperscraper` is wired but the demonstrated live run produced zero results before the `.jsonl` fix; the repo documents both the bug and the fix, but the demonstrated system state is still mixed.
- PDF acquisition logic exists and dry-run evidence exists in [acquisition_report.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 5/acquisition_report.json>), but live acquisition evidence is explicitly absent in [MANIFEST.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/MANIFEST.md>) and [PROVEIT_WORKS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/PROVEIT_WORKS.md>).
- The intended semantic classifier exists in the larger codebase, but the demonstrated Task 3 run uses keyword fallback because no centroid file is present.

## 3. What appears missing

The following do not appear to exist in the inspected repository state:


The following now exist and close earlier visibility and reproducibility gaps:

- [AUDIT_SUMMARY.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/AUDIT_SUMMARY.md>)
- [GRADER_GUIDE.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/GRADER_GUIDE.md>)
- [TRACK2_ARCHITECTURE.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/TRACK2_ARCHITECTURE.md>)
- [RUBRIC_TRACEABILITY.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/RUBRIC_TRACEABILITY.md>)
- [verify_track2_workflow.py](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/verify_track2_workflow.py>)
- [STAGE3_EVIDENCE_AUDIT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/STAGE3_EVIDENCE_AUDIT.md>)
- [FAILURE_ANALYSIS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/FAILURE_ANALYSIS.md>)
- [Phase 7/ae_handoff.py](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 7/ae_handoff.py>)
- [Phase 7/ae_inbox_stub.py](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 7/ae_inbox_stub.py>)
- [run_pipeline.py](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/run_pipeline.py>)
- [BENCHMARK_EVALUATION.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/BENCHMARK_EVALUATION.md>)
- [LESSONS_LEARNED.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/LESSONS_LEARNED.md>)
- [HOW_TO_RUN.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2/HOW_TO_RUN.md>)
- [run_gap_extraction.sh](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2/run_gap_extraction.sh>)

## 4. What appears duplicated

There is meaningful duplication in the evaluation/documentation layer:

- [MANIFEST.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/MANIFEST.md>) is already a grader-oriented high-level summary.
- [EVALUATION_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/EVALUATION_REPORT.md>) uses a 15-paper benchmark and frames a final technical assessment.
- [TRACK2_EVALUATION_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/TRACK2_EVALUATION_REPORT.md>) uses a 30-paper benchmark and provides the stronger evidence for the retrieval-bottleneck claim.
- [HUMAN_VALIDATION.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/HUMAN_VALIDATION.md>) overlaps with precision/false-positive discussion.
- [PIPELINE_ANALYSIS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/PIPELINE_ANALYSIS.md>) overlaps with bug-fix interpretation and classifier limitations.
- [NULL_RESULTS_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/NULL_RESULTS_REPORT.md>) overlaps with failure analysis.

This duplication is not useless, but it does create a discoverability problem and a metric-authority problem.

The cleanest fix is to designate one benchmark authority and let the other evaluation docs act as supporting material.

## 5. What appears undocumented or under-documented

- There is no obvious `START HERE` entry point for a grader beyond discovering [MANIFEST.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/MANIFEST.md>) manually.
- There is no short architecture document connecting Task 2 -> Task 3 -> evaluation.
- Task 2 reproducibility is weaker than its manifest suggests. The manifest describes submission-root copies and reproduction commands, but the actual `Track 2/Task 2` directory currently does not contain the claimed root copies `gap_extractor.py`, `query_generator.py`, `gap_results.json`, and `query_results.json`.
- Task 2 also lacks a clean wrapper for the PYTHONPATH-sensitive extraction path.
- Stage 3 evidence is now documented in [STAGE3_EVIDENCE_AUDIT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/STAGE3_EVIDENCE_AUDIT.md>), which makes the dry-run-only boundary explicit.
- There is no dedicated rubric traceability matrix that maps requirement to evidence in one table.
- There is no dedicated demonstrated-vs-implemented matrix that makes overclaiming hard to miss.
- There is no canonical one-command validation entry point for the Task 3 evidence story.

## 6. Central thesis validation

Proposed thesis:

> Evaluation showed that retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.

This claim is supported strongly enough to use, but only if one benchmark document is made authoritative.

Evidence supporting it:

- [TRACK2_EVALUATION_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/TRACK2_EVALUATION_REPORT.md>) states that 96% of misses in the 30-paper analysis are retrieval failures.
- [EVALUATION_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/EVALUATION_REPORT.md>) independently argues that the main limitation is retrieval scope rather than classifier quality.
- [NULL_RESULTS_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/NULL_RESULTS_REPORT.md>) documents query-level retrieval failures directly.

Risk:

- The repo currently contains both a 15-paper and 30-paper benchmark framing. The thesis is credible, but only if graders are pointed to one clear benchmark authority.

Hard decision:

- The 30-paper evaluation should be authoritative because it is the stronger test of the retrieval bottleneck claim.
- The 15-paper evaluation should remain as supporting evidence only.

Recommended wording:

- Safe and strong: "Evaluation showed that retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature."
- Avoid stronger wording like "proved" unless all metric authority is consolidated first.

## 7. Plan validation

For each proposed improvement, the classification below reflects actual repo state and likely grading value.

### 1. `AUDIT_SUMMARY.md`

**Status:** Now exists  
**Value:** High  
**Classification:** `COMPLETED`

Reason:
- Useful as an internal-to-grader bridge, but it does not itself unlock rubric points.
- It becomes high-value only if it is concise and factual rather than a second manifesto.

### 2. `GRADER_GUIDE.md`

**Status:** Now exists  
**Value:** High  
**Classification:** `COMPLETED`

Reason:
- The repo lacks a true obvious entry point.
- [MANIFEST.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/MANIFEST.md>) is strong, but it is not labeled as the universal starting point and does not orient Task 2 + Task 3 + evaluation together.

### 3. `TRACK2_ARCHITECTURE.md`

**Status:** Now exists  
**Value:** High  
**Classification:** `COMPLETED`

Reason:
- Architecture is currently scattered across phase plans, manifest prose, and the end-to-end trace.
- A one-page flow artifact would materially reduce grader comprehension cost.

### 4. Evidence map inside architecture or guide

**Status:** Now exists inside grader-facing docs  
**Value:** Medium-high  
**Classification:** `COMPLETED`

Reason:
- Evidence is present but fragmented.
- A light evidence map inside the architecture or grader guide is better than creating a separate document.

### 5. Task 2 reproducibility layer

**Status:** Improved with wrapper and run guide  
**Value:** High  
**Classification:** `COMPLETED`

Reason:
- The repo has Task 2 manifests and mirrored outputs, but no clean one-command wrapper.
- The current manifest also appears stale or inconsistent about root-copy files, which makes a clean `HOW_TO_RUN.md` plus wrapper more justified.

### 6. Rubric traceability matrix

**Status:** Now exists  
**Value:** Very high  
**Classification:** `COMPLETED`

Reason:
- Graders often ask "where is the evidence for requirement X?"
- A compact matrix mapping rubric requirement to file and evidence would directly reduce grading time and confusion.

### 7. Demonstrated vs implemented matrix

**Status:** Now exists inside grader-facing docs  
**Value:** High  
**Classification:** `COMPLETED`

Reason:
- This is the cleanest way to prevent accidental overclaiming.
- It makes dry-run only vs live evidence obvious at a glance.

### 8. Canonical validation command

**Status:** Now exists  
**Value:** Very high  
**Classification:** `COMPLETED`

Reason:
- `setup_verify.py` is useful, but graders care more about one obvious command that checks real project evidence.
- `verify_track2_workflow.py` should become that command if implemented.

### 9. Visual architecture diagram

**Status:** Now exists  
**Value:** High  
**Classification:** `COMPLETED`

Reason:
- A short ASCII flow is faster to read than prose.
- It should show Task 2 -> retrieval -> DB buffer -> triage -> acquisition readiness -> evaluation.

### 10. What Task 2 means to Task 3

**Status:** Now explicit  
**Value:** High  
**Classification:** `COMPLETED`

Reason:
- Task 2 is the source of search intent.
- A grader should not have to infer that from the filenames.

### 6. Stage 3 evidence audit

**Status:** Now explicit and evidence-backed  
**Value:** High  
**Classification:** `COMPLETED`

Reason:
- Dry-run evidence already exists.
- What is missing is not "all acquisition work," but a clear decision about whether live evidence exists and whether to collect a small controlled demonstration.
- This is a high-value truthfulness/rubric question.

### 7. Phase 7 handoff layer

**Status:** Completed for local validation  
**Value:** Mixed by component  
**Classification:** `COMPLETED`

Reason:
- `ae_handoff.py`, `ae_inbox_stub.py`, and `verify_track2_workflow.py` now exist and provide a local downstream-validation path.
- The current demonstrated result is 9 exported artifacts, 9 validated artifacts, and 1 skipped `ACCEPT` row due to missing abstract.
- `run_pipeline.py` now exists as a thin wrapper over existing evidence commands and keeps live search behind `--confirm-live`.

Current split:
- `ae_handoff.py`: `COMPLETED`
- `ae_inbox_stub.py`: `COMPLETED`
- `verify_track2_workflow.py`: `COMPLETED`
- `run_pipeline.py`: `COMPLETED`

### 8. Benchmark authority

**Status:** Completed with authoritative report plus alias  
**Value:** Very high  
**Classification:** `COMPLETED`

Reason:
- `TRACK2_EVALUATION_REPORT.md` is declared authoritative.
- `BENCHMARK_EVALUATION.md` now exists as a navigation alias and does not duplicate metrics.

### 11. `FAILURE_ANALYSIS.md`

**Status:** Now exists  
**Value:** Medium-high  
**Classification:** `COMPLETED`

Reason:
- The content already exists across [NULL_RESULTS_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/NULL_RESULTS_REPORT.md>), [PIPELINE_ANALYSIS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/PIPELINE_ANALYSIS.md>), and [HUMAN_VALIDATION.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/HUMAN_VALIDATION.md>).
- A dedicated failure analysis is justified only if it consolidates rather than duplicates.

### 12. `LESSONS_LEARNED.md`

**Status:** Now exists  
**Value:** Medium  
**Classification:** `COMPLETED`

Reason:
- Useful because it emphasizes evaluation-driven learning without duplicating benchmark metrics.
- It remains secondary to the benchmark authority and grader guide.

### 13. `What Changed Because of Evaluation`

**Status:** Missing as a named section  
**Value:** High  
**Classification:** `REQUIRED`

Reason:
- This is one of the cleanest ways to show measurement -> discovery -> action.
- It can live inside the benchmark authority or lessons-learned doc and does not need a standalone file.

### 14. `RUBRIC_TRACEABILITY.md`

**Status:** Missing  
**Value:** Medium  
**Classification:** `REQUIRED`

Reason:
- This would directly reduce grading friction, especially for rubric-scannable evidence.
- If created, it should be compact and table-based.
- If the grader guide already includes a strong rubric/evidence map, a separate file may become unnecessary.

### 15. `KNOWN_LIMITATIONS.md`

**Status:** Missing as a single authority  
**Value:** Low-medium  
**Classification:** `OPTIONAL`

Reason:
- Known limitations are already documented across the evaluation reports and null-results analysis.
- A separate file risks duplication unless the grader guide cannot surface limitations clearly.

### 16. `PROJECT_STORY.md`

**Status:** Missing  
**Value:** Low  
**Classification:** `UNNECESSARY`

Reason:
- Too likely to duplicate the guide, architecture doc, and benchmark summary.
- Graders are more likely to use a guide plus benchmark report than read another narrative artifact.

### 17. Official submission entry point

**Status:** Weakly solved  
**Value:** Very high  
**Classification:** `REQUIRED`

Reason:
- This can be solved either by `GRADER_GUIDE.md` or by elevating the existing manifest with a strong `START HERE` signal.
- Some kind of single obvious entry point is necessary.

### 18. Fresh grader test

**Status:** Missing  
**Value:** Medium-high  
**Classification:** `RECOMMENDED`

Reason:
- This is a very good definition-of-done check.
- It should live inside the plan or grader guide, not as a separate major document.

## 8. Recommended execution order

1. Create `GRADER_GUIDE.md`, `TRACK2_ARCHITECTURE.md`, and `RUBRIC_TRACEABILITY.md`.
2. Add the Task 2 reproducibility layer: `HOW_TO_RUN.md` and `run_gap_extraction.sh`.
3. Add `verify_track2_workflow.py` as the canonical validation command.
4. Designate `TRACK2_EVALUATION_REPORT.md` as the authoritative benchmark source and add a top-line authority declaration.
5. Add compact `What Changed Because of Evaluation` and `What Was Removed` sections inside the benchmark authority or lessons-learned doc.
6. Perform a Stage 3 evidence audit before deciding on any live demonstration.
7. Only then decide whether the handoff layer is worth implementing this round.

## 9. Bottom line

The project is stronger than it first appears. The main weakness is not lack of substantive work. The main weakness is that grader-facing navigation, reproducibility, and metric authority are underdesigned relative to the quality of the underlying pipeline and evaluation.

The best next improvements are the ones that make existing evidence easier to find and trust. The worst next improvements would be adding more narrative documents that restate what the repo already says.
