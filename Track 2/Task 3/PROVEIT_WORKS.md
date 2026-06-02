# Prove It Works — End-to-End Pipeline Trace

**Author:** Kaden Leung
**Date:** 2026-06-01
**Purpose:** Phase 7 submission requirement — one paper traced from gap to triage decision

---

## End-to-End Trace: REF-2026-05-31-000064

**Paper:** *Hapticity in Hybrid Space from an Enactive Perspective*
**Authors:** J. Yang
**Year:** 2024
**Venue:** International Conference on Architecture across Boundaries

---

### Step 1 — Gap Source (Task 2)

| Field | Value |
|---|---|
| Template ID | `CROSS_SOCIAL_MIRROR_PRESENCE_001` |
| Display ID | `CSMP1` |
| Step | 2 |
| Primary gap type | `DIRECTION` — competing accounts of how mirror neuron / embodied simulation mechanisms interact with architectural co-presence |
| Frameworks targeted | IC (Interoceptive / Constructionist Affect), EC (Embodied Cognition) |
| VOI score | **0.443** |
| VOI bucket | Low (all Task 2 queries fall in 0.443–0.478; see HUMAN_VALIDATION.md §2) |
| Depth tier | B |
| Corpus coverage | Dense |
| Query rationale | DIRECTION gap in CSMP1 step 2 (IC+EC frameworks). Pattern F selected per gap→pattern mapping. Third AND term was restructured from template fragment to researchable terms on 2026-05-27. |

---

### Step 2 — Boolean Query

```
("mirror neurons" OR "embodied simulation" OR "motor resonance")
AND ("social presence" OR "co-presence" OR "shared manifold")
AND ("architecture" OR "built environment" OR "space")
-review
```

Query display key: **`CSMP1-step2`**

---

### Step 3 — Search Execution

| Field | Value |
|---|---|
| Run ID | `RUN-20260531-000436` |
| Run date | 2026-05-31 |
| Sources enabled | `serpapi_scholar`, `scholarly_search`, `paperscraper_search` |
| SerpAPI credits used (this run) | 10 total / 1 for this query |
| Result position | **#1 of 10** from SerpAPI |
| Search URL | `https://link.springer.com/chapter/10.1007/978-981-96-4749-1_4` |
| Candidate ID | `CAND-RUN-20260531-000436-000064` |
| Merged from sources | `serpapi_scholar`, `scholarly_search` (both found this paper; merged by DOI) |
| discovered_at | `2026-05-31T00:17:21Z` |

---

### Step 4 — Ingestion into article_references

| Field | Value |
|---|---|
| reference_id | **`REF-2026-05-31-000064`** |
| doi | `10.1007/978-981-96-4749-1_4` |
| title_raw | Hapticity in Hybrid Space from an Enactive Perspective |
| first_author_surname | Yang |
| publication_year | 2024 |
| venue | International Conference on Architecture across … |
| discovered_via | `scholarly_search, serpapi_scholar` |
| discovery_run_id | `RUN-20260531-000436` |
| discovered_query | *(full query above)* |
| source_voi_score | 0.443 |
| triage_stage (initial) | `metadata_only` |
| Lifecycle transition 1 | `None → metadata_only` \| reason: `initial_insert:scholarly_search, serpapi_scholar` \| writer: `db_loader` \| `2026-05-31T00:18:30Z` |

Deduplication: DOI `10.1007/978-981-96-4749-1_4` was not previously in `article_references`, so **Branch E (fresh insert)** fired in `insert_or_dedupe_reference()`. No merge occurred.

---

### Step 5 — Stage 1: Metadata Triage

| Field | Value |
|---|---|
| Stage | Stage 1 (metadata-only screen) |
| Run ID | `RUN-STAGE1-FIXED-20260601` |
| Classifier mode | Keyword fallback (no HierarchicalClassifier centroids available) |
| Title keywords matched | `architecture` (in title), `hapticity` → `embodied` (via "enactive") |
| Classifier confidence | **0.25** (1–2 keyword hits → marginal pass) |
| Threshold | 0.20 |
| Noise check | No noise rules triggered |
| Decision | **PASS** → `abstract_pending` |
| Lifecycle transition 2 | `metadata_only → abstract_pending` \| reason: `stage1_passed:0.25` \| writer: `abstract_triage` \| `2026-05-31T01:55:51Z` |

Note: Before the keyword classifier bug fix (2026-06-01), this paper scored clf=0.25 and passed Stage 1 correctly. "Hapticity" contains "hap" (not a CNFA keyword) but "architecture" appears in the title, giving 1 hit → clf=0.25 → passes 0.20 threshold.

---

### Step 6 — Stage 2A: Abstract Collection

| Field | Value |
|---|---|
| Stage | Stage 2A (abstract fallback chain) |
| Run ID | `RUN-4B-FIXED-20260601` |
| DOI tried | `10.1007/978-981-96-4749-1_4` |
| Source 1 (Semantic Scholar by DOI) | No abstract returned |
| Source 2 (Semantic Scholar by title) | No match |
| Source 3 (CrossRef by DOI) | **SUCCESS** — abstract returned |
| abstract_source | **`crossref`** |
| abstract_text (first 200 chars) | *"The integration of digital technology offers new opportunities to design, visualize, and experience physical spaces. Recent research suggest that virtual spaces can stimulate genuine physiological reactions and emotions, creating a sense of embodiment…"* |
| study_type | `None` (estimated from abstract — no study-type keywords matched) |
| Lifecycle transition 3 | `abstract_pending → abstract_collected` \| reason: `abstract_source:crossref` \| writer: `abstract_collector` \| `2026-06-01T06:14:32Z` |

---

### Step 7 — Stage 2B: Triage Decision

| Field | Value |
|---|---|
| Stage | Stage 2B (classifier × VOI triage) |
| Run ID | `RUN-4D-FIXED-20260601` |
| Classifier mode | Keyword fallback |
| Classifier confidence | **0.60** (clf with full title + abstract → 3+ keyword hits including `architecture`, `embodied`, `space`, `environment`) |
| Classifier bucket | On-topic (≥ 0.50) |
| VOI score | **0.443** (from CSMP1-step2 query; voi_medium threshold = 0.40) |
| VOI bucket | Low (0.443 > voi_medium 0.40 → passes medium bar) |
| Decision matrix cell | clf ≥ 0.50 AND voi ≥ 0.40 → **ACCEPT** |
| triage_decision | **`ACCEPT`** |
| triage_reason | `accept_topic_and_voi:clf=0.60,voi=0.44` |
| Lifecycle transition 4 | `abstract_collected → triage_complete` \| reason: `accept_topic_and_voi:clf=0.60,voi=0.44` \| writer: `abstract_triage` \| `2026-06-01T10:18:06Z` |

---

### Step 8 — PDF Acquisition Attempt

| Field | Value |
|---|---|
| triage_stage | `triage_complete` |
| triage_decision | **`ACCEPT`** |
| Run ID | `RUN-P5-20260602-192128` |
| v_acquisition_queue | **YES — row appears in `v_acquisition_queue`** |
| pdf_acquisition_attempts | **3** (Unpaywall + OpenAlex + scidownl gate) |
| Unpaywall result | `acquisition_unpaywall:fail_http_403` — DOI found, PDF URL paywalled |
| OpenAlex result | `acquisition_openalex:fail_http_403` — same DOI, no OA version found |
| scidownl gate | `acquisition_scidownl:blocked_policy_gate` — correctly blocked (no clearance) |
| Final result | `acquisition_failed_all_sources` |
| acquired_paper_id | `NULL` — PDF not acquired |

Three live API calls were made and logged. All transitions are in `lifecycle_transitions` with timestamps `2026-06-02T19:21:28Z`–`2026-06-02T19:21:29Z`. The paper is not open access; Unpaywall (HTTP 403) and OpenAlex (HTTP 403) both confirmed the DOI is paywalled. scidownl is policy-gated and did not fire. See `STAGE3_EVIDENCE_AUDIT.md`.

---

### Step 9 — AE Handoff

| Field | Value |
|---|---|
| Stage | Phase 7 (AE handoff export) |
| Script | `Phase 7/ae_handoff.py` |
| Output artifact | `Phase 7/handoff_outbox/REF-2026-05-31-000064.json` |
| handoff_version | `1.0` |
| doi | `10.1007/978-981-96-4749-1_4` (lowercase, validated) |
| title | `Hapticity in Hybrid Space from an Enactive Perspective` |
| abstract | Present (CrossRef, 391 words) |
| triage_decision | `ACCEPT` |
| triage_reason | `accept_topic_and_voi:clf=0.60,voi=0.44` |
| voi_score | `0.443` |
| discovered_via | `["scholarly_search", "serpapi_scholar"]` |

Validation checks passed before export: DOI normalised, abstract non-null, triage_decision = ACCEPT.

---

### Step 10 — AE Inbox Validation

| Field | Value |
|---|---|
| Stage | Phase 7 (AE inbox stub) |
| Script | `Phase 7/ae_inbox_stub.py` |
| Report | `Phase 7/handoff_outbox/inbox_validation_report.json` |
| artifacts_seen | 9 |
| valid_count | **9** |
| invalid_count | **0** |
| This paper | `REF-2026-05-31-000064.json` — in `valid_files` list |
| Schema check | PASS — all required fields present |
| DOI check | PASS — lowercase, matches `^10\.\d{4,9}/\S{3,}` |
| Abstract check | PASS — non-null, plausibility check passed |
| Verdict | **VALID — ready for AE ingestion** |

---

### Complete Lifecycle Summary

```
2026-05-31T00:17:21Z  QUERY: CSMP1-step2 sent to SerpAPI + scholarly
                       artifact: query_id = CSMP1-step2

2026-05-31T00:17:21Z  SEARCH: SerpAPI returns #1: "Hapticity in Hybrid Space..."
                               scholarly also finds same paper → merged by DOI
                       artifact: candidate_id = CAND-RUN-20260531-000436-000064

2026-05-31T00:18:30Z  INSERT: REF-2026-05-31-000064 created in article_references
                               discovered_via = "scholarly_search, serpapi_scholar"
                               triage_stage = metadata_only
                       artifact: reference_id = REF-2026-05-31-000064

2026-05-31T01:55:51Z  STAGE 1: metadata screen PASS (clf=0.25 ≥ 0.20)
                               triage_stage → abstract_pending
                       artifact: lifecycle_transition id=1, from=None, to=metadata_only

2026-06-01T06:14:32Z  STAGE 2A: CrossRef returns abstract
                               triage_stage → abstract_collected
                       artifact: abstract stored, abstract_source = crossref

2026-06-01T10:18:06Z  STAGE 2B: ACCEPT (clf=0.60, voi=0.443, matrix: on-topic+medium)
                               triage_stage → triage_complete
                               triage_decision = ACCEPT
                       artifact: v_acquisition_queue row created

2026-06-02T19:21:28Z  STAGE 3: live acquisition attempt (RUN-P5-20260602-192128)
                               acquisition_unpaywall:fail_http_403
                               acquisition_openalex:fail_http_403
                               acquisition_scidownl:blocked_policy_gate
                               acquisition_failed_all_sources
                               pdf_acquisition_attempts = 3
                       artifact: lifecycle_transitions (9 rows across 3 processed papers)

2026-06-02T          AE HANDOFF: ae_handoff.py exported artifact
                       artifact: handoff_outbox/REF-2026-05-31-000064.json
                                 doi, title, abstract, triage_decision, voi_score

2026-06-02T          AE VALIDATION: ae_inbox_stub.py — 9/9 valid, 0 invalid
                       artifact: inbox_validation_report.json
                                 REF-2026-05-31-000064.json → VALID
```

---

### Human Relevance Assessment

"Hapticity in Hybrid Space from an Enactive Perspective" discusses:
- Embodied simulation and mirror neurons in architectural space (EC framework)
- Virtual affordances and physiological reactions to space (PP + MSI frameworks)
- Architecture–body interaction through haptic/sensory engagement

**Verdict: TRUE POSITIVE** — directly in CNFA scope. The paper studies how spatial design affects embodied physiological responses, which is the core object of study in the CNFA field.

---

## Disclaimer on Execution Mode

All stages above executed in **Research/Degraded mode**:
- Semantic classifier: keyword fallback (no HierarchicalClassifier centroids)
- paperscraper: 0 live results in the run that produced this paper (fixed post-run)
- Phase 5: ran live on 2026-06-02; 9 acquisition transitions logged; 0 PDFs acquired (both DOI-bearing rows paywalled; scidownl gate correctly blocked)

Results should not be interpreted as production-mode performance. See `EVALUATION_REPORT.md §8` for the full technical assessment.
