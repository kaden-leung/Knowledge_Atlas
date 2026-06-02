# Benchmark Evaluation — Executive Summary

**Author:** Kaden Leung
**Date:** 2026-06-02
**Course:** UCSD COGS 160

---

**This document is the authoritative source for benchmark metrics used throughout this submission.**

**If a metric appears elsewhere in any other document, this document takes precedence.**

Full methodology, per-query tables, ablation details, and discussion are in [TRACK2_EVALUATION_REPORT.md](Track 2/Task 3/TRACK2_EVALUATION_REPORT.md). All other documents that cite a metric should reference this file, not each other.

---

## Key Metrics

| Metric | Result | Basis |
|---|---|---|
| Benchmark corpus | 30 canonical CNFA papers | [CNFA_GOLD_STANDARD.md](Track 2/Task 3/CNFA_GOLD_STANDARD.md) |
| Retrieval recall (15-paper set) | **5/15 = 33%** | Papers entering `article_references` |
| End-to-end recall (15-paper set) | **2/15 = 13%** | Papers reaching `triage_decision = ACCEPT` |
| Retrieval recall (30-paper set) | **2/30 = 7%** | Full benchmark (books excluded from retrieval) |
| ACCEPT precision — conservative | **5/10 = 50%** | TP only; false positives = 3 |
| ACCEPT precision — liberal | **7/10 = 70%** | TP + borderline (2) |
| Abstract hit rate (DOI-bearing rows) | **73.2%** | S2 + CrossRef + PubMed + OpenAlex fallback chain |
| Query success rate | **8/10 = 80%** | 2 null-result queries documented |
| AE handoff validation | **9/9 valid** | `inbox_validation_report.json` |
| Test suite | **185/185 passing** | `pytest` across all phases |
| Chain verifier | **9/9 checks** | `verify_track2_workflow.py` |

---

## Central Finding

**Retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.**

Evidence: 96% of benchmark failures (papers that did not reach ACCEPT) were never retrieved — they were absent from the candidate pool before triage began. Improving the classifier or adjusting thresholds cannot recover papers that never entered `article_references`.

---

## Error Taxonomy (30-paper benchmark)

| Failure mode | Count | % of misses | Root cause |
|---|---|---|---|
| Never retrieved — no DOI (books) | 7 | 24% | Books not indexed by any academic API |
| Never retrieved — DOI present | 21 | 72% | Papers outside scope of 10 Task 2 queries |
| Stage 1 classifier reject | 1 | 3% | No architectural vocabulary in title (pure neuroscience paper) |
| Stage 1 noise rules | 0 | 0% | — |
| No abstract available | 0 | 0% | — |
| Stage 2B triage reject | 0 | 0% | — |

---

## Query Ablation Summary

Re-filtering existing results to simulate running only the top-K queries (by VOI):

| K | Queries | Papers | ACCEPTs | Marginal ACCEPTs |
|---|---|---|---|---|
| 1 | SC3-step3 (VOI 0.478) | 7 | 2 | — |
| 3 | + SC3-step6, SC1-step2 | 29 | 2 | 0 (22 new papers, 0 new ACCEPTs) |
| 5 | + L3-step7, NM1 | 50 | 2 | 0 (21 new papers, 0 new ACCEPTs) |
| 8 | + NM7, NM2, CSMP1-step2 | 80 | 4 | +2 (CSMP1 added 2 ACCEPTs) |
| 9 | + NVR1-step2 | 90 | 4 | 0 (10 new papers, 0 new ACCEPTs) |

Finding: ACCEPT count did not track VOI ranking. The lowest-VOI query (CSMP1-step2, VOI 0.443) contributed 2 ACCEPTs; the top-VOI query (SC3-step3, VOI 0.478) also contributed 2. Three queries with intermediate VOI contributed 0 ACCEPTs despite adding 43 papers. VOI does not predict per-query ACCEPT rate within this corpus's narrow score range (0.443–0.478).

---

## ACCEPT Set — Manual Assessment

| Paper | Source | clf | voi | Verdict |
|---|---|---|---|---|
| Brain dynamics of architectural affordances during transition | SC3-step3 (scholarly) | 0.85 | 0.478 | True positive |
| Sensorimotor brain dynamics reflect architectural affordances | SC3-step3 (SerpAPI) | 0.60 | 0.478 | True positive |
| Hapticity in Hybrid Space from an Enactive Perspective | CSMP1-step2 | 0.60 | 0.443 | True positive |
| Seeing minds directly: Direct Perception Theory | CSMP1-step2 | 0.60 | 0.443 | Borderline |
| Global research agenda: Health, well-being, built environment | PDF-harvest | 0.60 | 0.443 | True positive |
| Indicators of healthy architecture — systematic review | PDF-harvest | 0.60 | 0.443 | True positive |
| A review of comfort, health, and energy use | PDF-harvest | 0.85 | 0.443 | Borderline |
| Possibilities, perceptions and practices: flexible learning spaces | PDF-harvest | 0.60 | 0.443 | False positive |
| Integrating appreciative inquiry into architectural pedagogy | PDF-harvest | 0.60 | 0.443 | False positive |
| Quantifying thermal comfort + energy retrofits | PDF-harvest | 0.60 | 0.443 | False positive |

False positive pattern: all 3 are papers that use architectural vocabulary in pedagogical or engineering contexts. The keyword fallback classifier cannot distinguish these from CNFA-specific papers. Semantic embeddings would address this.

---

## Scope Limitations

- Benchmark corpus was curated by the pipeline author (selection bias risk).
- 30-paper set is small; confidence intervals are wide.
- VOI correlation finding is based on 9 active queries (2 returned zero results).
- Classifier operates in keyword-fallback mode, not the intended semantic mode.

Full discussion: [TRACK2_EVALUATION_REPORT.md §8](Track 2/Task 3/TRACK2_EVALUATION_REPORT.md)
