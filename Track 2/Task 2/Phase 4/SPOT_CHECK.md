# Spot-Check — Manual Google Testing of 3 Queries
## Track 2 · Task 2 · Phase 4

**Date:** 2026-05-23
**Author:** Kaden Leung
**Method:** Paste the AI Citation query into Google, score the first page of results using the 3-dimension SC-6 rubric from `QUERY_GENERATOR_CONTRACT.md` v1.4.

> **Where the substantive query-result validation actually lives.** This browser-based table is a lightweight manual supplement. The **substantive** validation — real top results recorded per query, with relevance judgments — was carried out at the Task 3 level (a separate submission, branch `track2/kaden-leung-task3`), where all 10 queries were run live against SerpAPI/Scholar:
> - **Recorded retrieved papers per query:** `TRACK2_EVALUATION_REPORT.md` §4.3 query coverage matrix (papers retrieved, ACCEPT count, ACCEPT rate for each query).
> - **Manual relevance judgments:** `BENCHMARK_EVALUATION.md` ACCEPT-set assessment (each retrieved ACCEPT paper labeled true-positive / borderline / false-positive).
> - **Queries that retrieved nothing:** `NULL_RESULTS_REPORT.md` (documented, not hidden).
>
> (Those three documents ship with the Task 3 submission, not this one.) The browser spot-check table below was filled in on 2026-06-02 (Google Scholar Labs) and **passes SC-6** (3/3 queries scored ≥ 2). It complements — and is corroborated by — the deeper Task 3 live-retrieval evidence above.

---

## Why these three

Three queries selected for diversity across pattern, framework, and gap structure:

| Pick | Gap | Why this one |
|---|---|---|
| 1 | **SC3 step 3** (Holl vs. Ellard threshold) | Top-VOI gap; Pattern F with named proponents; psychophysiological measurement; tests whether real proponent names + skin conductance produces the Holl/Ellard debate literature |
| 2 | **SC3 step 6** (partial revelation) | Only Pattern C in batch; rebuttal-text DIRECTION (no named proponents); tests the Case-C fallback path |
| 3 | **L3 step 7** (Foster vs. daylight multi-channel) | Strongest framework-anchor alignment (CB→circadian photobiology); melanopsin measurement; tests whether the measurement-injection improvement actually surfaces chronobiology papers |

---

## Queries to paste

**Query 1 — SC3 step 3 (Pattern F, predictive processing):**

```
When Holl argues that emotional power of architectural thresholds depends on compositional placement, versus the alternative threshold event mechanism stated in the template, which account is better supported by psychophysiological studies measuring skin conductance or arousal response in building occupants under spatial transition, and can predictive processing theory adjudicate between them?
```

**Query 2 — SC3 step 6 (Pattern C, predictive processing):**

```
What experimental studies measuring physiological or behavioral outcomes find that partial revelation reduces rather than amplifies the threshold response by…, and do replications support the effect, as predicted by predictive processing / active inference theory?
```

**Query 3 — L3 step 7 (Pattern F, circadian photobiology):**

```
When Foster argues that CCT effects on circadian system are mediated directly by melanopic irradiance, versus the alternative daylight multi-channel stimulus mechanism stated in the template, which account is better supported by chronobiology studies measuring melanopic irradiance or melatonin in participants exposed to built environments, and can circadian photobiology adjudicate between them?
```

---

## Scoring rubric (from QUERY_GENERATOR_CONTRACT.md SC-6)

Each dimension scored 0 or 1:

| Dimension | Score 1 | Score 0 |
|---|---|---|
| **Phenomenon match** | First-page results address the same core phenomenon as the gap (e.g., arousal at spatial transitions — not general arousal) | Off-topic phenomenon |
| **Mechanism family match** | Results use the same mechanistic vocabulary (e.g., prediction error, melanopic irradiance) or a recognized equivalent | Generic or unrelated mechanism |
| **Measurement tradition match** | Results use the same instrument class (e.g., skin conductance, melatonin assay) | No measurement or wrong measurement family |

**Verdict from total:** `0–1` = irrelevant · `2` = partial · `3` = relevant. SC-6 passes if at least 2 of 3 queries score ≥ 2.

---

## Results table

Tested live in **Google Scholar Labs** (the AI-citation search the queries were designed for).

| Query ID | Phenomenon Match (0/1) | Mechanism Family Match (0/1) | Measurement Tradition Match (0/1) | Total (0–3) | Verdict | Top first-page result title (one line) |
|---|---|---|---|---|---|---|
| SC3-3 | 1 | 1 | 1 | 3 | relevant | A Deep Learning Framework for Predicting Psycho-Physiological States in Urban Underground Systems (Huang & Jiao, *Buildings*, 2026) |
| SC3-6 | 1 | 1 | 0 | 2 | partial | How humans integrate the prospects of pain and reward during choice (Talmi et al., *J. Neurosci.*, 2009) — on-target hits: Kok 2012, Plikat 2025 |
| L3-7  | 1 | 1 | 1 | 3 | relevant | Predicting melatonin suppression by light in humans (Giménez et al., *J. Pineal Res.*, 2022) |

**Date tested:** 2026-06-02  **Tester:** Kaden Leung

**Verdict: SC-6 PASS.** 3 of 3 queries scored ≥ 2 (requirement is ≥ 2 of 3); two scored a full 3/3.

**Per-query notes:**
- **SC3-3 (relevant, 3/3):** Returned architectural psychophysiology directly on target — skin-conductance/GSR studies of arousal during spatial transitions (Huang & Jiao; Xylakis; Canepa & Djebbara), several explicitly invoking predictive processing.
- **SC3-6 (partial, 2/3):** Strong on phenomenon (expectation/revelation reduces response, incl. Plikat's magic-trick revelation study) and mechanism (predictive coding / active inference), but the **measurement tradition drifted to fMRI/electrophysiology rather than architectural psychophysiology** — a concrete instance of the query-grounding limitation that is the project's central finding. Note: this query independently surfaced **Kok 2012**, paper #13 in `CNFA_GOLD_STANDARD.md`.
- **L3-7 (relevant, 3/3):** Strongest result — retrieved **both sides of the Foster debate** (melanopic-irradiance account vs. the multi-channel "circadian stimulus" model for architectural lighting) plus **R. G. Foster's own paper**, all using melatonin/melanopic-irradiance measurement in built environments.

---

## Notes on testing

1. Use a clean browser session (incognito mode) to minimize personalization effects on AI Overview ranking.
2. If AI Overview does not appear for a query, score the top 3 Google Scholar results instead and record `(Scholar fallback)` next to the verdict.
3. Google AI Overview is non-deterministic — a second run on the same query may surface different papers. The rubric is designed to be robust to that variability: it scores against domain alignment, not against specific paper IDs.

---

## How this connects to SC-6 in the contract

SC-6 (Manual test validation, QUERY_GENERATOR_CONTRACT.md v1.4) requires ≥ 3 queries tested with ≥ 2 scoring "relevant" (≥ 2/3 on the rubric above). **This is satisfied:** 3 queries were tested live in Google Scholar Labs on 2026-06-02 and all 3 scored ≥ 2 (two at 3/3), recorded in the results table above with the top retrieved paper for each.
