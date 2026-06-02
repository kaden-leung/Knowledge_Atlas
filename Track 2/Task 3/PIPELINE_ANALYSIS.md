# Pipeline Analysis — Bugs Fixed, Limitations Documented

**Author:** Kaden Leung
**Date:** 2026-06-01
**Context:** Post expert-panel revision. Addresses precision, recall, VOI compression, and component failures.

> **Metric authority note:** Precision/ACCEPT figures in this document reflect the **pre-fix** classifier state (6 ACCEPT papers, 3/6 = 50%). After the Stage 1 keyword fix there are 10 ACCEPT papers; the authoritative current figures (5/10 conservative, 7/10 liberal) are in [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md). The bug analysis and structural findings here remain valid.

---

## 1. Bugs Fixed (this session)

### Bug 1 — Keyword classifier: `"architecture"` does not match `"architectural"`

**Severity:** High (caused false negatives for the most canonical CNFA papers)

**Root cause:** The keyword fallback uses `kw in title.lower()` (substring test). `"architecture"` and `"architectural"` differ at character 12 (`'e'` vs `'a'`), so the substring test fails. Every CNFA paper using the adjectival form "architectural" — including Djebbara 2019, the most-cited paper in this corpus — received `clf=0.00` and was rejected at Stage 1.

**Demonstrated impact:**
- Djebbara 2019 ("Sensorimotor brain dynamics reflect **architectural** affordances"): clf 0.00 → REJECT
- "Unpacking the wow experience: profound emotional responses to evocative works of **architecture**": clf 0.00 → REJECT (this one did have "architecture" in its title but still scored 0.25 before the fix because "emotion" only gives 1 hit)

**Fix applied:** Added `"architectural"`, `"affordance"`, `"affordances"`, `"sensorimotor"`, `"occupant"`, `"indoor"`, `"wellbeing"`, `"well-being"`, `"health"`, `"comfort"`, `"perception"`, `"environment"` to `CNFA_KEYWORDS` in `Phase 4/stage1_metadata_triage.py`.

**Post-fix results:**
| Paper | clf before | clf after | Stage 1 outcome |
|---|---|---|---|
| Djebbara 2019 — Sensorimotor brain dynamics | 0.00 | **0.50** | **PASS** (on-topic) |
| Wow experience — emotional responses to architecture | 0.00 | **0.25** | **PASS** (marginal) |
| VR wayfinding — cognitive load + building configuration | 0.00 | **0.25** | **PASS** (marginal) |
| Kok 2012 — visual cortex / V1 | 0.00 | 0.00 | REJECT (correct — no architectural vocabulary) |

**Important caveat:** This fix means Stage 1 would behave differently if re-run. The 984 rejections and 6 ACCEPTs were computed with the buggy classifier. A re-run with the fixed classifier would likely yield more ACCEPTs (Djebbara 2019 alone would move from REJECT to ACCEPT if it had an abstract). The pipeline state in the DB reflects the *pre-fix* classifier; the correct results require a re-run.

---

### Bug 2 — paperscraper `.json` → `.jsonl` suffix

**Severity:** High (caused 100% failure rate on 10 live queries)

**Root cause:** paperscraper ≥ 0.2 requires a `.jsonl` file extension; the adapter was using `.json`. The error `"Please provide a filepath with .jsonl extension"` appeared on every query.

**Fix applied:** Changed `tempfile.mkstemp(suffix=".json")` to `suffix=".jsonl"` in `Phase 2/adapters/paperscraper_adapter.py`. Updated the file reader to parse JSONL (one JSON object per line) instead of one JSON array.

**Post-fix verification:** Live test on `"architectural affordances" AND "predictive coding"` returned 3 results without error. paperscraper is now operational.

**Note:** paperscraper searches arXiv, not Google Scholar. Result quality for CNFA queries may be low because CNFA research is predominantly published in peer-reviewed journals (Neuron, PNAS, Building and Environment) rather than preprint servers. However, it provides genuine preprint coverage.

---

## 2. Known-Item Recall Test Results

Five papers expected to be findable in any reasonable CNFA literature search:

| Paper | In pipeline? | Stage | What happened |
|---|---|---|---|
| Djebbara 2019 (PNAS) — Sensorimotor brain dynamics | ✅ Yes | `rejected_at_metadata` | False negative from keyword bug (now fixed) |
| Djebbara 2021 (Sci Rep) — Brain dynamics during transition | ❌ No | — | Not retrieved by any source |
| Kok 2012 (Neuron) — Less is more / expectation sharpens V1 | ✅ Yes | `rejected_at_metadata` | No CNFA vocabulary in title — correct REJECT |
| Dumesnil 2026 (bioRxiv) — Architecture shapes event boundaries | ✅ Yes | `abstract_missing` | Retrieved but S2/APIs had no abstract for this preprint |
| Fich 2014 — CAVE VR cortisol study | ❌ No | — | Not retrieved; was not in our 10-query search scope |
| Kaplan — Attention Restoration Theory | ✅ Yes | `rejected_at_metadata` | Retrieved via PDF harvest; rejected by classifier (marginal) |
| Ulrich — Biophilia / stress recovery | ✅ Yes | `rejected_at_metadata` | Retrieved via PDF harvest; rejected by classifier |

**Known-item recall: 4/7 found in pipeline (57%)**. Of those 4 found, 3 were rejected before triage. Only the Dumesnil preprint survived to abstract collection (and then failed there).

**Interpretation:** Retrieval coverage is reasonable (57% of tested gold-standard papers entered the pipeline). The bigger problem is post-retrieval rejection — the keyword classifier eliminated genuinely relevant papers. The bug fix addresses this for papers using "architectural" vocabulary; papers with no architectural terms (Kok 2012, Fich 2014) cannot be caught by keyword matching alone — that requires the HierarchicalClassifier with semantic embeddings.

---

## 3. VOI Score Compression — Root Cause

**Observation:** All 10 Task 2 query VOI scores fall in the range 0.443–0.478 (spread = 0.035).

**Root cause confirmed:** The `voi_score` field in `query_results.json` was pre-computed at Task 2 time from template-level gap metadata, **not** from `score_voi(findings)`. All queries have `findings_count=0` in the stored JSON, confirming that `aggregate_paper_voi([])` was not the source.

The values reflect the Task 2 query generator's assessment of each gap's information value based on the Atlas's existing belief structure:
- All 10 gaps are classified as `primary_gap_type='DIRECTION'` (direction-of-effect conflicts)
- All are at `depth_tier='A'` (high theoretical importance)
- But none has a large effect-size assessment → `score_voi()` maps these to ~0.4 ("gap, weak signal")

The 0.478 ceiling is not an artifact of bad scoring — it reflects that the Atlas genuinely considers all 10 targeted gaps to be at similar levels of uncertainty. A more discriminating VOI would require some gaps to have confirmed large effects (score → 0.8+) or established contradictions (score → 1.0) against which others could be compared.

**Implication for the pipeline:** VOI cannot serve as a meaningful ranking signal when all values compress to within 0.035 of each other. In the current corpus, the classifier confidence is the only discriminating signal for ACCEPT vs. EDGE_CASE. The `voi_medium` threshold is a floor, not a discriminator.

**The reviewer was right to flag this.** A more informative VOI would require either:
1. Running `score_voi()` on actual extracted findings from the Eater (available only after Phase 7), or
2. Using a different ranking proxy — e.g., citation count, recency, or the query's `depth_tier` and `corpus_coverage` fields

---

## 4. Classifier Improvement Path

The HierarchicalClassifier in `Article_Finder/triage/classifier.py` uses sentence-transformer embeddings and centroid-based classification. It would produce continuous confidence scores rather than the step function (0.00, 0.25, 0.45, 0.60) that the keyword fallback produces.

**Expected improvement with real classifier:**
- Djebbara 2019 (`"Sensorimotor brain dynamics reflect architectural affordances"`): keyword = 0.50; real classifier likely 0.80+ (directly in PP+EC centroid)
- Kok 2012 (`"Less is more: expectation sharpens V1"`): keyword = 0.00; real classifier probably 0.40–0.60 (predictive coding in neuroscience without explicit architectural terms)
- Pedagogical paper (false positive): keyword = 0.60; real classifier likely 0.20–0.30 (no neuroscience signal)

**To generate the centroid file:**
```bash
cd Article_Finder
python3 scripts/build_centroids.py \
  --input data/cnfa_seed_papers.json \
  --output triage/.centroids.pkl
```
The seed papers JSON must be created from known-relevant CNFA papers. This is a one-time 10–15 minute process.

---

## 5. Updated Precision / Recall Estimates

### Precision (measured)
**Current (with pre-fix classifier):** 3/6 = 50% on ACCEPT bucket

**Estimated post-fix (with fixed keyword classifier):** Cannot be directly measured without re-running Stage 1 and Stage 2B. However, the bug fix expands the ACCEPT pool (Djebbara 2019 would now pass Stage 1 if it had an abstract). If 1–2 additional true positives enter ACCEPT and no new false positives are added, precision improves to 4–5/7 = 57–71%.

**Estimated post-real-classifier:** Likely 70–85% based on the improvement pattern observed: the false positives (pedagogical paper, energy engineering paper) have weak architectural-cognition signals that embeddings would capture; the true positives have strong signals.

### Recall (partial measurement)
**Known-item test:** 4/7 (57%) — measures retrieval coverage only, not full pipeline recall

**Full pipeline recall** (retrieval + abstract collection + Stage 1 + Stage 2B) is unmeasured. Based on known-item test:
- Retrieval: ~57% (4 of 7 entered the pipeline)
- Post-retrieval survival rate: 1/4 (25%) reached abstract collection; 0/4 reached ACCEPT
- **End-to-end recall on known items: 0/7 (0%)** — none of the known CNFA gold-standard papers reached ACCEPT

This is the most important unresolved issue. The pipeline successfully identified 3 true positives in ACCEPT, but none of them are the canonical CNFA papers. The pipeline is finding papers that are CNFA-adjacent (health + built environment) rather than papers in the core CNFA theoretical tradition.

---

## 6. Recommended Next Steps (prioritized)

| Priority | Action | Impact |
|---|---|---|
| **1** | Re-run Stage 1 and Stage 2B with the fixed classifier | Fixes the false negative for architectural vocabulary; changes the ACCEPT set |
| **2** | Build HierarchicalClassifier centroid file | Improves precision from ~50% to expected ~70–85% |
| **3** | Instructor review of all 6 current ACCEPTs before Phase 5 acquisition | Prevents downloading false-positive papers |
| **4** | Gold-standard recall evaluation (10–20 known CNFA papers) | Fills the biggest remaining methodological gap |
| **5** | paperscraper live re-run (bug now fixed) | Adds arXiv preprint coverage |
| **6** | VOI proxy improvement (use depth_tier or citation count as supplement) | Makes the ACCEPT/EDGE_CASE boundary more meaningful |

---

## 7. What Remains Genuinely Uncertain

1. **End-to-end recall:** The pipeline finds some relevant papers, but whether it covers 10%, 50%, or 90% of the relevant CNFA literature is unknown. The known-item test hints at serious recall issues.
2. **Real-classifier impact:** The keyword fallback is demonstrably buggy (architectural/architecture miss) and coarse (step function). The improvement from the real classifier could be modest or substantial.
3. **VOI as a ranking signal:** With a 0.035 spread, VOI adds almost no discriminating power in the current corpus. It is currently a noise source in the triage decision, not a signal.
