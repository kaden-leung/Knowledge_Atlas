# Task 2 & 3 Combined Pipeline — K-ATLAS Gap Targeting & Query Generation

**Date:** 2026-05-20
**Track:** 2 — Article Finder
**Phase:** 1 (Understanding) → feeds Phase 2 (Build)

---

## Pipeline Diagram

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                    TASK 2 & 3 COMBINED PIPELINE — K-ATLAS                       ║
╚══════════════════════════════════════════════════════════════════════════════════╝

  Article_Eater/                      Article_Finder/
  data/templates/                     core/ + search/ + triage/
  (166 PNU .json files)
         │
         ▼
┌─────────────────────┐
│   1. GAP EXTRACTOR  │  reads mechanism_chain steps
│                     │  flags: confidence < 0.5
│  • warrant type     │  gap_type: MECHANISM / VALIDATION /
│  • bridge_inferred  │            DIRECTION / BOUNDARY
│  • competing_accts  │
└─────────┬───────────┘
          │  EpistemicGap objects
          ▼
┌─────────────────────┐
│  2. VOI CALCULATOR  │  VOICalculator.calculate_voi()
│                     │  inputs: gap_type, belief, web
│  structural_voi =   │
│   0.6×centrality    │  combined = α×structural
│   + 0.4×sparsity    │           + (1-α)×epistemic
│                     │           × priority_weight
│  epistemic_voi =    │
│   uncertainty       │  priority ceiling:
│   × level_import    │    DIRECTION  → 1.0
│                     │    VALIDATION → 0.7
│  sorted by          │    MECHANISM  → 0.5
│  combined_voi ↓     │    BOUNDARY   → 0.4
└─────────┬───────────┘
          │  ranked EpistemicGap list
          │  (top-N selected)
          ▼
┌──────────────────────────────────────────────────┐
│               3. QUERY GENERATOR                 │
│                                                  │
│   ┌─────────────────────┐  ┌───────────────────┐ │
│   │  AI CITATION query  │  │  BOOLEAN query    │ │
│   │                     │  │                   │ │
│   │  Full NL sentence   │  │  "term1" AND      │ │
│   │  5-component form:  │  │  ("syn1" OR       │ │
│   │  • evidence type    │  │   "syn2") AND     │ │
│   │  • mechanism/       │  │  "mechanism"      │ │
│   │    measure          │  │  -exclusion       │ │
│   │  • env. condition   │  │                   │ │
│   │  • population       │  │  → Semantic       │ │
│   │  • theory anchor    │  │    Scholar API    │ │
│   │                     │  │  → PubMed API     │ │
│   │  → Google AI        │  │                   │ │
│   │    Citation (human) │  │  reproducible /   │ │
│   │                     │  │  auditable        │ │
│   └──────────┬──────────┘  └────────┬──────────┘ │
└──────────────┼─────────────────────┼─────────────┘
               │                     │
               └──────────┬──────────┘
                           │  query strings
                           ▼
              ┌────────────────────────┐
              │   4. SEARCH EXECUTION  │
              │                        │
              │   SerpAPI              │
              │   (Google Scholar)     │
              │                        │
              │   returns per hit:     │
              │   • title              │
              │   • snippet            │
              │   • DOI (if present)   │
              │   • URL                │
              └───────────┬────────────┘
                          │  raw hits
                          ▼
              ┌────────────────────────┐     ┌──────────────────┐
              │  5. ABSTRACT FETCHER   │────▶│  CORPUS DEDUPE   │
              │                        │     │                  │
              │  Semantic Scholar      │     │  articles.json   │
              │  CrossRef              │     │  (760 papers)    │
              │  PubMed                │     │                  │
              │  OpenAlex              │     │  DOI match →     │
              │                        │     │  SKIP            │
              │  enriches each hit     │◀────│                  │
              │  with full abstract,   │     └──────────────────┘
              │  authors, year, venue  │
              └───────────┬────────────┘
                          │  enriched candidates
                          ▼
              ┌────────────────────────┐
              │  6. TRIAGE ENGINE      │
              │                        │
              │  atlas_shared          │
              │  classifier            │
              │  +                     │
              │  VOI re-score          │
              │  (does this abstract   │
              │   actually address     │
              │   the gap?)            │
              └───────────┬────────────┘
                          │
              ┌───────────┴────────────────────────┐
              ▼           ▼            ▼            ▼
        ┌──────────┐ ┌─────────┐ ┌─────────┐ ┌──────────────────┐
        │  ACCEPT  │ │  EDGE   │ │  REJECT │ │ MISSING_ABSTRACT │
        │          │ │  CASE   │ │         │ │                  │
        │ addresses│ │ partial │ │ off-    │ │ no abstract      │
        │ the gap  │ │ match / │ │ topic / │ │ available →      │
        │ mechanism│ │ review  │ │ general │ │ manual review    │
        │ directly │ │ needed  │ │ only    │ │ queue            │
        └────┬─────┘ └────┬────┘ └────┬────┘ └────────┬─────────┘
             │             │           │                │
             └─────────────┴─────┬─────┘                │
                                 │                       │
                                 ▼                       │
              ┌────────────────────────┐                 │
              │   7. PRISMA FUNNEL     │◀────────────────┘
              │      DASHBOARD         │
              │                        │
              │  Records identified    │
              │  via search:    N      │
              │        ↓               │
              │  Duplicates removed    │
              │  (corpus dedupe): -n   │
              │        ↓               │
              │  Screened (abstract    │
              │  triage):       n      │
              │        ↓               │
              │  Excluded (REJECT): -n │
              │        ↓               │
              │  ACCEPT:        n      │
              │  EDGE_CASE:     n      │
              │  MISSING_ABS:   n      │
              └────────────────────────┘
```

---

## Key Code Locations

| Stage | File | Class / Function |
|---|---|---|
| Gap extraction | `Article_Eater/data/templates/*.json` | mechanism_chain steps |
| VOI scoring | `Article_Eater/src/services/voi_search.py` | `VOICalculator.calculate_voi()` |
| Gap detection | `Article_Eater/src/services/voi_search.py:922` | `GapDetector.detect_gaps()` |
| Query generation | `Article_Eater/src/services/voi_search.py:722` | `QueryGenerator` |
| Cross-field vocab | `Article_Eater/src/services/voi_search.py:132` | `CrossFieldVocabulary` |
| Corpus dedupe | `Article_Finder/core/ae_corpus_dedupe.py` | `AECorpusDedupe` |
| Triage / classify | `Article_Finder/triage/` | classifier + registry_sink |
| Corpus inventory | `Knowledge_Atlas/data/ka_payloads/articles.json` | 760 articles (substitute for missing lifecycle DB) |

---

## Five Priority Gaps (Phase 1 deliverable)

Ranked by estimated VOI impact. Gap type matters: `DIRECTION` gaps score up to 1.0; `MECHANISM` gaps cap at 0.5.

| # | Template · Step | Confidence | Gap type | What's missing |
|---|---|---|---|---|
| 1 | **SC3** Step 3 — multi-channel threshold bonus | 0.40–0.45 | `DIRECTION` | Holl (intentionality) vs. Ellard (channel count) are competing accounts; linear interpolation from single N=48 data point; additive vs. multiplicative function unknown |
| 2 | **CREA1** Step 1 — environmental → salience switching | 0.40 | `MECHANISM` | `bridge_inferred: true`, empty description, `ANALOGICAL` warrant — environmental sensory richness → DMN-ECN coupling flexibility has never been measured directly |
| 3 | **SC3** Step 5 — temporal density Goldilocks 20–45s | 0.45 | `VALIDATION` | Ellard observational only; no controlled study; panel names this "Prediction 1 from SC-II" — highest-priority open prediction in template |
| 4 | **L1** Step 3 — awe at >1:30 contrast, bright zone <20% FOV | 0.55 | `MECHANISM` | Threshold values (20% fraction, 1:30 ratio) are panel estimates; cultural/semantic alternative not ruled out; only 1 paper in corpus on this topic |
| 5 | **SC3** Step 6 — partial revelation +0.15–0.25 μS bonus | 0.40 | `DIRECTION` | Sign of effect is uncertain — partial revelation could amplify (anticipation) OR dampen (reduced surprise); rebuttal is a direction conflict, not just magnitude uncertainty |

### Critical implementation note — gap type classification

The current `GapDetector` in `voi_search.py:922` only assigns `VALIDATION` (uncertainty > 0.3) or `MECHANISM` (papers < 3). It **never assigns `DIRECTION`**. Gaps 1 and 5 above both have `competing_accounts` entries in their template JSON — the gap extractor must detect `competing_accounts` and route those as `DIRECTION` gaps. Failing to do so cuts their VOI score roughly in half (priority weight 0.5 → 1.0).

---

## VOI Formula Reference

```
structural_voi = 0.6 × centrality + 0.4 × sparsity

epistemic_voi  = belief.credence.uncertainty × level_importance
                 level_importance: theoretical=0.9, intermediate=0.7,
                                   empirical=0.5, observational=0.4

base_voi       = α × structural_voi + (1−α) × epistemic_voi
                 α by gap type: MECHANISM=0.7, DIRECTION=0.5,
                                VALIDATION=0.4, BOUNDARY=0.3

combined_voi   = min(base_voi × priority_weight, 1.0)
                 priority_weight: DIRECTION=1.0, VALIDATION=0.7,
                                  MECHANISM=0.5, BOUNDARY=0.4
```

Centrality dominates: it gets weight 0.6 inside structural_voi, and structural_voi gets weight α=0.7 for MECHANISM gaps → centrality drives ~42% of the final score before priority weighting.

---

## Query Format Reference

**AI Citation (natural language — Google AI Overview)**
Complete question sentence with 5 components:
1. Evidence type signal ("What experimental studies…" / "What neuroimaging evidence…")
2. Mechanism / measure (the specific neural or physiological process)
3. Environmental condition (the built-environment feature being manipulated)
4. Population / context (who / where)
5. Theoretical anchor (named theory or named phenomenon)

**Boolean (Google Scholar / Semantic Scholar API)**
`"primary term" AND ("synonym1" OR "synonym2") AND "mechanism" -exclusion`
Reproducible, auditable, bounded by explicit vocabulary choices.

Use AI Citation for discovery across terminological traditions.
Use Boolean for systematic coverage and pipeline API calls.
