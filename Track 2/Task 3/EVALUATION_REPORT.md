# Pipeline Evaluation Report — Final State

**Author:** Kaden Leung
**Date:** 2026-06-01
**Status:** Post-fix, post-re-run, post-expanded-benchmark
**Execution mode:** Degraded (keyword fallback classifier; no HierarchicalClassifier centroids)

> **Metric authority note:** [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) is the authoritative metric source for this submission. This document provides supporting context and historical comparison (before-vs-after fix). Where any number here conflicts with BENCHMARK_EVALUATION.md, the latter takes precedence.

---

## 1. North-Star Metric

**The pipeline succeeds when ≥ 50% of an expert-curated gold-standard CNFA bibliography reaches ACCEPT.**

Current measured result: **13% (2/15)** — below threshold.

---

## 2. Execution Modes

| Mode | Description | Current state |
|---|---|---|
| **Production** | All components operational; real semantic classifier; full abstract coverage | ❌ Not available |
| **Research** | Keyword fallback classifier; real retrieval APIs; real abstract collection | ✅ This run |
| **Degraded** | paperscraper fixed; S2 rate-limited; no centroids | ⚠️ Active limitations |
| **Offline/Mock** | All network calls mocked; fixture data only | ✅ Available for tests |

**All reported numbers are from Research/Degraded mode.** Production mode requires the HierarchicalClassifier centroid file.

---

## 3. Benchmark Results — Expanded Gold Standard (15 papers)

**Selection criteria:** Canonical CNFA papers, core environmental psychology classics, and key theoretical foundations cited across the 10 COGS-160 Atlas frameworks.

| Paper | In pipeline? | Final decision | Notes |
|---|---|---|---|
| Djebbara 2019 — Sensorimotor brain dynamics (PNAS) | ✅ Yes | **ACCEPT** | Abstract corrupted (see §6); title classification only |
| Djebbara 2021 — Brain dynamics during transition (Sci Rep) | ✅ Yes (no DOI) | **ACCEPT** | Found by scholarly without DOI stored |
| Dumesnil 2026 — Architecture + event boundaries (bioRxiv) | ✅ Yes | MISSING_ABSTRACT | Fake DOI from fixture data |
| Ulrich 1984 — View through a window (Science) | ✅ Yes | rejected_at_metadata | "view" "window" not in CNFA keywords |
| Kaplan 1995 — Restorative benefits of nature | ❌ No | — | Not retrieved by any query |
| Fich 2014 — CAVE VR cortisol (Gold Standard) | ❌ No | — | Not retrieved; not in query scope |
| Kok 2012 — Expectation sharpens V1 (Neuron) | ✅ Yes | rejected_at_metadata | No architectural vocabulary |
| Clark 2019 — Active inference and precision | ❌ No | — | Not retrieved |
| Browning — 14 Patterns of biophilic design | ❌ No | — | Not retrieved |
| Bedrosian 2011 — Light at night and mood | ❌ No | — | Not retrieved |
| Lu 2020 — Wayfinding in hospitals | ❌ No | — | Not retrieved |
| Evans 2006 — Child development + built environment | ❌ No | — | Not retrieved |
| Heschong — Daylighting and cognitive performance | ❌ No | — | Not retrieved |
| Gramann 2017 — Mobile brain-body imaging | ❌ No | — | Not retrieved |
| Wilson 2002 — Six views of embodied cognition | ❌ No | — | Not retrieved |

**Summary:**

| Metric | Count | Rate |
|---|---|---|
| Retrieval recall | 5/15 | **33%** |
| ACCEPT recall | 2/15 | **13%** |
| North-star target | — | 50% |
| Distance to target | — | **37 percentage points** |

### Interpretation

The pipeline retrieves papers that appear in response to the specific 10 Boolean queries from Task 2. It does **not** function as a comprehensive CNFA literature search. The 10 queries cover specific theoretical gaps (PP threshold events, SN spatial depth, NM dopamine/serotonin, CSMP1 mirror neurons, NVR1 polyvagal) but miss large areas of the CNFA literature:

- Attention Restoration Theory (Kaplan)
- Stress recovery from nature (Ulrich)
- Gold-standard cortisol studies (Fich)
- Biophilic design corpus (Browning, Heschong)
- Mobile EEG methodology (Gramann)

**Root cause:** Retrieval gap, not classifier gap. These papers would not appear even with the real HierarchicalClassifier, because they were never retrieved in the first place. Fixing the classifier cannot recover papers that the query layer never found.

---

## 4. Precision Measurement — Full ACCEPT Set (10 papers)

| Paper | Assessment | CNFA-relevant? |
|---|---|---|
| Djebbara 2021 — Brain dynamics during transition | ✅ True positive | Core CNFA (clf=0.85) |
| Djebbara 2019 — Sensorimotor brain dynamics | ✅ True positive | Core CNFA; abstract corrupted |
| Global research agenda: health + built environment | ✅ True positive | Core CNFA scope |
| Indicators of healthy architecture — systematic review | ✅ True positive | Core CNFA scope |
| Hapticity in Hybrid Space — enactive perspective | ✅ True positive | EC + MSI frameworks |
| Comfort, health, energy use review | ⚠️ Borderline | Built environment health but energy-engineering focus |
| Seeing minds directly — direct perception theory | ⚠️ Borderline | CNFA-adjacent theoretical background |
| Integrating appreciative inquiry into architectural pedagogy | ❌ False positive | Pedagogical, not neuroscientific |
| Quantifying thermal comfort + energy retrofits | ❌ False positive | Energy engineering, not CNFA |
| Flexible learning spaces in NZ schools | ❌ False positive | Educational policy, not CNFA |

**Precision: 5/10 clear TPs (50%), 7/10 including borderlines (70%)**

**False positive pattern:** All 3 false positives are papers that mention architecture in non-neuroscience contexts (pedagogy, energy engineering, educational policy). The keyword classifier cannot distinguish "paper about architecture" from "paper about architectural effects on human neuroscience." This requires semantic embeddings.

---

## 5. Summary Table — Three-Run Comparison

| Metric | Original (pre-fix) | Post-bug-fix | Target |
|---|---|---|---|
| Retrieval recall (7-paper) | 57% | 57% | — |
| Retrieval recall (15-paper) | ~33%* | 33% | ≥ 70% |
| ACCEPT recall (7-paper) | 0% | 29% | ≥ 50% |
| ACCEPT recall (15-paper) | 0% | **13%** | ≥ 50% |
| ACCEPT precision (conservative) | 50% | 50% | ≥ 70% |
| ACCEPT precision (liberal) | 58% | 70% | ≥ 70% |
| Total ACCEPTs | 6 | 10 | — |
| North-star (50% of 15-paper gold standard reaching ACCEPT) | 0% | 13% | ≥ 50% |

*7-paper benchmark was a biased sample (overrepresented Djebbara-lab papers the pipeline is specifically designed to retrieve)

**What the bug fix actually changed:**
- Recall improved (2 canonical papers now in ACCEPT vs 0)
- Precision held flat (same true/false positive ratio)
- The adversarial reviewer's hypothesis — that the bug was only one of several causes — was confirmed. Fixing it improved the result but did not close the gap to target.

---

## 6. Known Data Quality Issues

| Issue | Status | Impact |
|---|---|---|
| Djebbara 2019: wrong abstract from S2 | 🔶 Flagged in DB (`abstract_source = 'corrupted_wrong_paper_returned'`); abstract set to NULL | Affects Phase 5 metadata quality; does not affect ACCEPT decision (title-based clf) |
| Dumesnil 2026: fake fixture DOI | 🔶 Known | No API will resolve `10.1101/2026.01.15.123456` — fixture data artifact |
| 11 gold-standard papers: never retrieved | ❌ Unresolved | Retrieval layer scope limitation; requires new queries or expanded search |

---

## 7. What Remains to Be Done (Priority Order)

| Priority | Action | Unblocks |
|---|---|---|
| 1 | Train HierarchicalClassifier centroids | Semantic precision improvement; less keyword false-positive noise |
| 2 | Expand Task 2 queries to cover Kaplan/Ulrich/Fich/biophilic subfields | Retrieval recall improvement (currently 33%) |
| 3 | Instructor review of 10 ACCEPT papers before Phase 5 acquisition | Prevents acquiring 3 confirmed false positives |
| 4 | Djebbara 2019 abstract: fetch from CrossRef or PubMed manually | Corrects corrupted record |
| 5 | Expand gold standard to 30-50 papers with expert curation | More reliable recall estimate |
| 6 | Define query expansion strategy for missed subfields | Closes the 67% retrieval gap |

---

## 8. Final Technical Assessment

The system is architecturally complete and successfully executes an end-to-end literature acquisition workflow consisting of query generation, search, deduplication, triage, acquisition planning, and reporting.

Multiple implementation defects discovered during evaluation were corrected, including a keyword-classification bug (the adjectival "architectural" was not matched by the keyword "architecture"), a paperscraper integration bug (.jsonl suffix incompatibility), and abstract-plausibility validation for metadata quality control. Re-running the pipeline after these fixes demonstrated measurable improvements in downstream paper acceptance — Djebbara 2019, the most-cited CNFA paper in the corpus, moved from REJECT to ACCEPT.

However, expanded evaluation against a 15-paper gold-standard benchmark revealed that retrieval coverage remains the dominant limitation. Retrieval recall was 33% (5/15), and end-to-end ACCEPT recall was 13% (2/15), indicating that most canonical papers never entered the candidate pool. Precision of accepted papers remained approximately 50% under conservative evaluation criteria.

Accordingly, the primary limitation of the current system is not triage accuracy but retrieval scope. The 10 Task 2 Boolean queries are targeted at specific theoretical gaps (PP threshold events, NM dopamine/serotonin, etc.) and do not cover the broader CNFA foundational corpus (Kaplan, Ulrich, Fich, Browning, Gramann). A classifier improvement cannot rescue papers that were never retrieved. The architecture is functional and test coverage is strong (full offline suite passing: 186 passed, 1 skipped), but current retrieval effectiveness is insufficient to support claims of comprehensive literature discovery.

**Future work should prioritize retrieval expansion, query diversification, semantic retrieval methods, and evaluation against larger gold-standard corpora before drawing stronger conclusions about overall system effectiveness.**

---

## 9. Honest Framing for Course Submission

**What this pipeline does well:**
- Correctly implements the pipeline architecture (buffer → triage → acquisition)
- Identifies bugs and measures their effects empirically
- Provides honest, measured performance data rather than speculative claims
- Retrieves and correctly ACCEPTs the two most-cited Djebbara-lab papers in the field
- Demonstrates 70% precision (liberal) on the ACCEPT set with a keyword fallback

**What this pipeline does not do:**
- Achieve comprehensive CNFA literature coverage (33% retrieval recall on 15-paper benchmark)
- Reach the 50% north-star ACCEPT recall target
- Operate with the intended semantic classifier (keyword fallback only)
- Recover the foundational CNFA corpus (Kaplan, Ulrich, Fich, Browning, Gramann)

**Appropriate claims for submission:**
- "The pipeline correctly identifies and stages CNFA-related candidates from a targeted gap-driven search"
- "With keyword fallback classification, 70% of accepted papers are CNFA-relevant (liberal assessment)"
- "End-to-end recall against a 15-paper gold standard is 13%, indicating substantial room for improvement with semantic retrieval and expanded query coverage"

**Claims to avoid:**
- "The pipeline surfaces most relevant CNFA literature"
- "The triage system is production-ready"
- Any claim that implies the 10 ACCEPTs represent comprehensive coverage of any CNFA gap
