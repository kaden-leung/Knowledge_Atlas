# Failure Analysis

**Date:** 2026-06-02  
**Purpose:** Consolidate the main observed failure modes, the evidence for each one, and what changed because they were measured

## 1. Central finding

Evaluation showed that retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.

That finding matters because it changed the interpretation of the whole system. The strongest negative result in this project is not "the classifier is weak." It is "most relevant papers never entered the candidate pool."

## 2. Failure matrix

| Failure | Evidence | Impact | Action taken |
|---|---|---|---|
| Retrieval coverage was much lower than expected | [TRACK2_EVALUATION_REPORT.md](TRACK2_EVALUATION_REPORT.md) | Most canonical CNFA papers never reached triage | Reframed the project around retrieval as the dominant bottleneck |
| Two Task 2 queries returned zero API results | [NULL_RESULTS_REPORT.md](NULL_RESULTS_REPORT.md) | 2 of 10 targeted gaps had no retrieval coverage | Marked query reformulation as required future work |
| `paperscraper` produced 0 live results | [MANIFEST.md](MANIFEST.md), [PIPELINE_ANALYSIS.md](PIPELINE_ANALYSIS.md) | One retrieval source contributed nothing in the demonstrated run | Fixed `.json` to `.jsonl` bug and documented demonstrated state honestly |
| `architecture` failed to match `architectural` | [MANIFEST.md](MANIFEST.md), [PIPELINE_ANALYSIS.md](PIPELINE_ANALYSIS.md) | Clearly relevant CNFA papers were false negatives at Stage 1 | Expanded Stage 1 keyword list |
| One returned abstract was clearly wrong | [TRACK2_EVALUATION_REPORT.md](TRACK2_EVALUATION_REPORT.md) | A stored abstract could be scientifically invalid even when the title match was correct | Added plausibility checks and flagged the corrupted case |
| Acquisition stage ran live but acquired 0 PDFs | [STAGE3_EVIDENCE_AUDIT.md](STAGE3_EVIDENCE_AUDIT.md) | Phase 5 ran on 2026-06-02 (9 transitions); both DOI-bearing rows are paywalled; scidownl correctly blocked | Stage ran and is evidenced; no PDF was successfully downloaded |

## 3. Failure categories

## 3.1 Retrieval failures

This is the dominant category.

- The 30-paper benchmark shows that most missed papers were never retrieved at all.
- Two of the ten designed queries returned zero results across all configured sources.
- `paperscraper` contributed no live results in the demonstrated run state.

Why this matters:

- downstream precision work cannot rescue papers that never enter `article_references`
- improving Stage 1 or Stage 2B alone cannot solve the main recall problem

## 3.2 Triage failures

These exist, but they are not the main bottleneck.

- The keyword fallback classifier missed adjectival forms like `architectural`
- The keyword fallback also admits some architecture-adjacent false positives
- Precision is limited by lexical matching rather than semantic understanding

Why this matters:

- triage still affects precision
- triage does not explain the majority of missed canonical papers

## 3.3 Data-quality failures

The project also surfaced data-quality failures that would be easy to miss in a less instrumented pipeline.

- one abstract returned for a correct DOI was clearly the wrong paper
- many Stage 2A failures were valid `MISSING_ABSTRACT` cases rather than software crashes
- some harvested references were too noisy for API resolution

Why this matters:

- the pipeline needs plausibility and validation checks, not just more retrieval volume
- documented terminal states are better than silently fabricating data

## 3.4 Demonstration-boundary failures

Some components exist in code but were not fully demonstrated in the current evidence state.

- acquisition ran live (9 transitions) but acquired 0 PDFs because the attempted DOIs are paywalled and scidownl is policy-gated
- the intended semantic classifier is not the demonstrated mode (keyword fallback is used)

Why this matters:

- the submission needs an implemented-vs-demonstrated distinction
- honest scoping is part of the strength of the project, not a weakness

## 4. What changed because these failures were measured

1. The project claim changed from "the pipeline runs" to "the pipeline was evaluated and the main bottleneck was identified."
2. The classifier discussion changed from vague limitation language to a specific keyword-mismatch bug with a concrete repair.
3. Query quality became a measured retrieval problem, not just a design assumption.
4. Acquisition claims were narrowed to the level actually supported by the current evidence.

## 5. Best use of this document

Use this file alongside:

- [TRACK2_EVALUATION_REPORT.md](TRACK2_EVALUATION_REPORT.md) for benchmark evidence
- [NULL_RESULTS_REPORT.md](NULL_RESULTS_REPORT.md) for query-level failures
- [STAGE3_EVIDENCE_AUDIT.md](STAGE3_EVIDENCE_AUDIT.md) for the acquisition boundary

This file is not meant to replace those artifacts. Its job is to connect them into one measurement -> discovery -> action story.
