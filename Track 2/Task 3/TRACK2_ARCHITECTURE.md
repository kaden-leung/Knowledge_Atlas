# Track 2 Architecture — Expanded Reference

> **Navigation note:** [GRADER_GUIDE.md](GRADER_GUIDE.md) contains the inline pipeline diagram and is the recommended starting point. This file is the expanded reference — it adds a per-stage evidence map (§3) linking each stage to its specific artifact files. Read this if you want to jump directly to a specific stage's evidence without reading the full guide.

This file shows the pipeline flow and where evidence lives.

## 1. Pipeline diagram

```text
Task 2
Gap Extraction
      |
      v
Query Generation
      |
      v
Task 3 Retrieval
      |
      v
DB Buffer (article_references)
      |
      +--> Reference Harvesting from local PDFs
      |
      v
Stage 1 Metadata Triage
      |
      v
Abstract Collection
      |
      v
Stage 2B Triage Decision
      |
      v
ACCEPT Queue (v_acquisition_queue)
      |
      v
Acquisition Readiness
      |
      v
Evaluation + Validation
```

## 2. Why Task 2 matters

Task 3 is not a generic literature search pipeline. Task 2 supplies the search intent.

- Task 2 extracts epistemic gaps from the upstream knowledge system.
- Task 2 converts those gaps into targeted search queries.
- Task 3 then measures how well those gap-driven queries retrieve useful literature.

Without Task 2, Task 3 would be a generic search-and-triage pipeline. With Task 2, it becomes a gap-targeted retrieval system.

## 3. Evidence map

| Stage | Main evidence |
|---|---|
| Gap extraction | [Track 2/Task 2/Phase 2/gap_results.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2/Phase 2/gap_results.json>) |
| Query generation | [Track 2/Task 2/Phase 3/query_results.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 2/Phase 3/query_results.json>) |
| Retrieval | [Track 2/Task 3/Phase 2/search_results.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 2/search_results.json>) |
| DB buffer | [task3_pipeline_lifecycle.db](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/task3_pipeline_lifecycle.db>) |
| Stage 1 + Stage 2A + Stage 2B | [MANIFEST.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/MANIFEST.md>) |
| End-to-end lifecycle trace | [PROVEIT_WORKS.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/PROVEIT_WORKS.md>) |
| Downstream handoff validation | [Phase 7 handoff_manifest.json](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/Phase 7/handoff_outbox/handoff_manifest.json>) |
| Human precision review | [HUMAN_VALIDATION.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/HUMAN_VALIDATION.md>) |
| Null results and missing abstracts | [NULL_RESULTS_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/NULL_RESULTS_REPORT.md>) |
| Benchmark evaluation | [TRACK2_EVALUATION_REPORT.md](</Users/bigdaddy/Downloads/UCSD/COGS 160/Track 2/Task 3/TRACK2_EVALUATION_REPORT.md>) |

## 4. Demonstrated vs implemented

| Component | Implemented | Demonstrated |
|---|---|---|
| Retrieval | Yes | Yes |
| DB loading | Yes | Yes |
| Reference harvesting | Yes | Yes |
| Stage 1 triage | Yes | Yes |
| Stage 2A abstract collection | Yes | Yes |
| Stage 2B triage | Yes | Yes |
| PDF acquisition | Yes | Ran live (9 transitions, 0 PDFs — paywalled) |
| AE handoff | Yes | Yes, local validation |

The central evaluated finding is:

**Evaluation showed that retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature.**
