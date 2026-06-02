# Human Validation — Accepted Papers + Threshold Analysis

**Author:** Kaden Leung
**Date:** 2026-06-01
**Reviewer:** Kaden Leung (pipeline author — acknowledged conflict of interest; external review recommended)
**Purpose:** Address expert panel findings RT1, R1, R2, AR2.

> **Metric authority note:** This document was written against the pre-v1.2.0 ACCEPT set (6 papers, before the keyword classifier expansion). After the classifier was fixed, there are 10 ACCEPT papers. Precision figures in this document (3/6 = 50% conservative, 3.5/6 = 58% liberal) reflect that earlier evaluation. Current authoritative metrics against the 10-paper ACCEPT set are in [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md): **5/10 = 50% conservative, 7/10 = 70% liberal**. The threshold analysis in §2 and the structural findings throughout remain valid.

---

## 1. Success Definition (P1 fix)

**The pipeline succeeds when it identifies at least one paper per targeted gap that a domain expert judges relevant to cognitive neuroscience of architecture, with ≥ 60% ACCEPT precision and zero papers acquired (Phase 5) that are later judged irrelevant without human review.**

---

## 2. Threshold Selection — Honest Account (R1 / RT1 fix)

### What happened

The VOI threshold (`voi_medium`) was initially set to 0.50 before results were observed. After Stage 2B produced 0 ACCEPTs, the threshold was lowered to 0.40. This is a recalibration after observing results.

### Why it happened (structural explanation)

All 42 Stage 2B papers have VOI scores ≤ 0.478. This is not a coincidence — it is a structural consequence of two pipeline decisions:

1. **All PDF-extracted references** (1,103 of 1,193 rows) receive the fallback VOI of 0.443 because they have no `discovered_query` (PDF citations don't carry SerpAPI query provenance).
2. **Task 2 query VOI scores** all fall in 0.443–0.478 because all 10 queries were scored as `"gap"` findings with `effect_size ≤ 0.5` → `score_voi()` maps these to 0.4 ("gap, weak signal").

The original `voi_medium=0.50` threshold was set without knowledge of this distribution. Setting it above 0.478 categorically excludes every paper in the pipeline, regardless of classifier confidence. Lowering to 0.40 is not "adjusting until I get a desired count" — it is "acknowledging that the VOI score distribution tops out at 0.478 for this corpus."

### What should have been done

The threshold should have been chosen after examining the VOI score distribution of Task 2 queries (available before Stage 2B runs). Had that been done, 0.40–0.45 would have been the principled choice from the start.

### Sensitivity table (full)

**VOI threshold sensitivity** (classifier threshold = 0.50 fixed):

| voi_medium | ACCEPT | EDGE_CASE | REJECT | Notes |
|---|---|---|---|---|
| 0.500 | **0** | 6 | 36 | Original setting; excludes everything (all voi ≤ 0.478) |
| 0.480 | **0** | 6 | 36 | Still excludes everything |
| 0.460 | **0** | 9 | 33 | Still excludes clf=0.60 papers (their voi=0.443) |
| 0.444 | **0** | 20 | 22 | Hard cliff — 0.443 is just below |
| **0.443** | **6** | 36 | 0 | **Actual VOI floor** — accepts all clf≥0.50 papers |
| 0.440 | **6** | 36 | 0 | Same as 0.443 in this corpus |
| **0.400** | **6** | 36 | 0 | **Current setting** |
| 0.350 | **6** | 36 | 0 | No further change — voi distribution is at floor |

**Key finding:** The threshold cliff is at 0.443 (the exact fallback VOI). There is no "tuning range" — the corpus structure creates a binary: either ≥ 0.444 (0 ACCEPTs) or ≤ 0.443 (6 ACCEPTs). The choice of 0.40 vs 0.443 does not change the outcome; any value below 0.443 produces the same 6 ACCEPTs.

**Classifier threshold sensitivity** (voi_medium = 0.40 fixed):

| clf_on_topic | ACCEPT | EDGE_CASE | REJECT | Notes |
|---|---|---|---|---|
| 0.70 | 0 | 42 | 0 | No papers reach clf=0.70 (keyword fallback peaks at 0.60) |
| 0.65 | 0 | 42 | 0 | Same — no papers at clf≥0.65 |
| **0.60** | **6** | 36 | 0 | Accepts all clf=0.60 papers; current effective threshold |
| **0.50** | **6** | 36 | 0 | **Current setting** — identical to 0.60 in this corpus |
| 0.45 | 24 | 18 | 0 | Would include clf=0.45 papers |
| 0.40 | 24 | 18 | 0 | Same as 0.45 |

**Key finding:** The classifier threshold cliff is at 0.60 (keyword fallback produces only clf ∈ {0.0, 0.25, 0.45, 0.60}). Setting `clf_on_topic` anywhere in 0.50–0.60 produces the same 6 ACCEPTs.

### What a different threshold would mean

The only decision with real consequence is whether to lower clf_on_topic to 0.45 to pick up 18 more papers. Manual inspection of those 18 (below) suggests ~5–8 might be relevant. This was deliberately **not done** because:
- The clf=0.45 bucket includes obvious noise (formatted citation strings like `"4. Söderlund,J.TheEmergenceofBiophilicDesign"`)
- Expanding without manual review would increase precision cost

---

## 3. Manual Relevance Assessment — 6 ACCEPT Papers

**CNFA scope:** Papers that study how the built environment (architecture, buildings, spatial design) affects human cognition, physiology, emotion, or behavior through mechanisms described by the 10 canonical frameworks (PP, SN, DP, DT, NM, IC, MS, EC, CB, MSI).

### Paper 1 — REF-2026-05-30-000137

**Title:** Integrating appreciative inquiry (AI) into architectural pedagogy: An assessment experiment of three retrofitted buildings in the city of Glasgow

**DOI:** 10.1016/j.foar.2017.02.001 | **Source:** Semantic Scholar

**Abstract excerpt:** *"This paper introduces Appreciative Inquiry (AI) as a mechanism that integrates various forms of inquiry into learning [about retrofitted buildings]."*

**Verdict:** ❌ **FALSE POSITIVE — NOT RELEVANT to CNFA**

**Reason:** This paper is about architectural *pedagogy* (how to teach architecture students to assess buildings). It measures student learning outcomes, not human cognitive or physiological responses to the built environment. The "AI" is "Appreciative Inquiry" (an organizational development method), not architecture-AI. No neural, physiological, or cognitive-neuroscience mechanisms are studied.

**Why it was accepted:** The keyword classifier counted "architecture" + "buildings" + "learning" + "assessment" = 4+ CNFA keywords → clf=0.60. The classifier has no concept of paper *focus*; it only counts keyword presence.

---

### Paper 2 — REF-2026-05-30-000409

**Title:** Global research agenda: Health, well-being, and the built environment

**DOI:** 10.5334/bc.262 | **Source:** OpenAlex

**Abstract excerpt:** *"Wellbeing in buildings is often approached as the aggregate result of individual interactions between building occupants and building features... [but this] ignores the ways in which broader social and symbolic dimensions shape wellbeing."*

**Verdict:** ✅ **TRUE POSITIVE — RELEVANT to CNFA**

**Reason:** Directly addresses how the built environment affects health and wellbeing. Engages with CNFA frameworks NM (neuromodulatory systems), IC (interoception/constructionist affect), and MS (memory systems). A research-agenda paper with scope relevant to the field.

---

### Paper 3 — REF-2026-05-30-000417

**Title:** Indicators of healthy architecture — A systematic literature review

**DOI:** 10.1007/s11524-020-00469-z | **Source:** Semantic Scholar

**Abstract excerpt:** *"The design of the built environment plays an important role as a determinant of health... so the design of buildings can greatly impact on human health. Accordingly, architecture health indices (AHIs) are used to evidence the effects on human health associated with the design of buildings."*

**Verdict:** ✅ **TRUE POSITIVE — RELEVANT to CNFA**

**Reason:** Systematic literature review of how architectural design affects health outcomes. Directly in CNFA scope. Relevant to multiple frameworks (CB, NM, IC, SN). A high-value synthesis paper.

---

### Paper 4 — REF-2026-05-30-000430

**Title:** Quantifying thermal comfort and carbon savings from energy-retrofits in social housing

**DOI:** 10.1016/j.enbuild.2021.110950 | **Source:** Semantic Scholar

**Abstract excerpt:** *"Energy retrofits of existing multi-unit residential buildings (MURBs) are necessary to reduce their carbon emissions. While doing so there is an opportunity to influence the indoor environment... This paper characterizes carbon emissions and [occupant] perceptions."*

**Verdict:** ❌ **FALSE POSITIVE — NOT RELEVANT to CNFA (marginally adjacent)**

**Reason:** The paper's primary contribution is energy engineering (carbon emissions quantification, retrofit cost-benefit). Thermal comfort appears as a secondary outcome measure, not the object of study. No cognitive, neural, or physiological mechanisms are examined. The CNFA field studies *how architecture affects cognition*; this paper studies *how retrofits affect energy bills and comfort self-reports*.

**Mitigation:** If the Stage 2B classifier had access to the full abstract (which it did), this is a classifier failure — thermal comfort + occupant perceptions are CNFA-adjacent keywords, but the paper's core is engineering economics.

---

### Paper 5 — REF-2026-05-31-000064

**Title:** Hapticity in Hybrid Space from an Enactive Perspective

**DOI:** 10.1007/978-981-96-4749-1_4 | **Source:** CrossRef

**Abstract excerpt:** *"Recent research suggest that virtual spaces can stimulate genuine physiological reactions and emotions, creating a sense of embodiment. This paper focuses on the potential to use the 'virtual affordance' in real space to stimulate more architecture-body interaction."*

**Verdict:** ✅ **TRUE POSITIVE — RELEVANT to CNFA**

**Reason:** Directly in CNFA scope. Addresses embodied cognition (EC framework), multisensory integration (MSI), and predictive processing (PP — "virtual affordances") in architectural space. The enactive perspective is a recognized theoretical strand in CNFA.

---

### Paper 6 — REF-2026-05-31-000065

**Title:** Seeing minds directly: Revisiting direct perception theory in social cognition

**DOI:** 10.1177/18724981251387330 | **Source:** Semantic Scholar

**Abstract excerpt:** *"The Direct Perception Theory (DPT) in social cognition is a tacit social cognitive process that allows us to directly perceive another person's feelings, intentions or mind state through body expression, without drawing an internal inference or mental simulation."*

**Verdict:** ⚠️ **BORDERLINE — NOT DIRECTLY RELEVANT to CNFA**

**Reason:** This paper is about person-to-person social cognition (perceiving other minds), not about built environment effects on cognition. While Direct Perception Theory has theoretical overlap with predictive processing (PP framework) and is philosophically aligned with CNFA's theoretical commitments, the paper itself does not study how architecture affects people. It belongs in social cognitive science, not CNFA proper.

**Could argue relevance:** If the research question were "how do architectural spaces shape social perception," this paper would be background theory. As submitted, it is off-target.

---

### ACCEPT Precision Summary

| Paper | True/False Positive | CNFA Relevance |
|---|---|---|
| 1 — Architectural pedagogy | ❌ FALSE POSITIVE | Not CNFA (pedagogical focus) |
| 2 — Health, well-being, built environment | ✅ TRUE POSITIVE | Core CNFA scope |
| 3 — Indicators of healthy architecture | ✅ TRUE POSITIVE | Core CNFA scope |
| 4 — Thermal comfort + energy retrofit | ❌ FALSE POSITIVE | Engineering, not CNFA |
| 5 — Hapticity + enactive perspective | ✅ TRUE POSITIVE | Directly CNFA |
| 6 — Direct perception theory | ⚠️ BORDERLINE | Theoretical background only |

**Precision: 3/6 clear true positives (50%), or 3.5/6 if borderline counted (58%)**

This is better than random (expected ~20–30% for arbitrary retrieval from this corpus) but below the threshold one would want for a systematic review tool.

---

## 4. False Negatives — Inspected REJECTs at clf=0.45, voi=0.478

These three papers were rejected because clf=0.45 < clf_on_topic threshold of 0.50.

| Paper | Title | CNFA-relevant? |
|---|---|---|
| REF-000004 | Unpacking the wow experience: Profound emotional responses to evocative works of architecture | **YES — False Negative** — directly CNFA (emotional responses to architecture) |
| REF-031011 | Linking cognitive load induced by route instruction types and building configuration (VR) | **YES — False Negative** — SN + cognitive load + VR methodology, core CNFA |
| REF-031012 | Wayfinding in libraries | **Marginal** — wayfinding (SN) but information-science focus |

**At least 2 of the 3 nearest REJECTs appear to be false negatives.** This confirms the IR reviewer's concern that recall is unknown and potentially low.

---

## 5. Interpretation

### Pipeline precision: 50–58% on the ACCEPT bucket
The pipeline is applying a reasonable relevance signal (keyword-based CNFA classification) but without the full HierarchicalClassifier it cannot distinguish between papers that *mention* architecture and papers that *study architecture's effects on people*. This distinction requires semantic embeddings, which the keyword fallback cannot provide.

### Recall: unknown, likely poor
The 3 near-miss REJECTs include papers with titles that are obviously CNFA-relevant ("profound emotional responses to evocative works of architecture"). This suggests that raising the classifier threshold to 0.50 (which drops clf=0.45 papers from ACCEPT) excludes genuinely relevant work. Recall measurement requires a gold standard — a set of known-relevant papers against which the retrieval is tested.

### What this means for the pipeline
The pipeline demonstrates that the *architecture* (candidate buffer, lifecycle tracking, triage stages) works correctly. The *results* — 6 ACCEPTs at 50% precision, unknown recall — reflect the limitations of:
1. Keyword-fallback classifier (vs. the intended HierarchicalClassifier)
2. VOI scores that don't discriminate between gaps (all compress to 0.443–0.478)
3. Low abstract coverage (20.8% hit rate) due to S2 rate limiting and no-DOI PDF references

### Recommendation
Before any Phase 5 PDF downloads, the 3 TRUE POSITIVEs (Papers 2, 3, 5) should be manually confirmed by the course instructor as suitable for acquisition. Papers 1 and 4 (false positives) should be re-triaged to EDGE_CASE or REJECT pending instructor review.
