# Track 2 · Task 3 — Grading Snapshot

**Author:** Kaden Leung
**Date:** 2026-05-28
**Branch:** `track2/kaden-leung-task3` (forked from `origin/master`)

This directory is the **grading snapshot mirror** of Task 3 work. The canonical, runnable copy lives outside the Knowledge_Atlas repo at:

```
~/Downloads/UCSD/COGS 160/Track 2/Task 3/
```

The mirror exists so the grader can read all deliverables from the conventional Knowledge_Atlas submission location, matching the Task 2 pattern (`Knowledge_Atlas/Track 2/Task 2/`).

## What's here

| Path | Purpose |
|---|---|
| `MANIFEST.md` | Top-level audit trail: deliverables, DB row counts, reproduction recipe, path deviations from the course spec |
| `Phase 2/SEARCH_RUNNER_CONTRACT.md` | v1.2.0 — SC-1 through SC-32, JSON Schema artifact, credit policy |
| `Phase 2/search_runner.py` + `adapters/` | Four-source harvester (SerpAPI primary, scholarly + paperscraper fallbacks, mock for offline) |
| `Phase 2/test_*.py` | 40/40 tests pass |
| `Phase 3/SCHEMA_CONTRACT.md` | v1.0.0 — `article_references` + `lifecycle_transitions` DDL contract |
| `Phase 3/REFERENCE_HARVESTER_CONTRACT.md` | v1.0.0 — PDF reference-list extractor contract |
| `Phase 3/DEDUPE_SPOTCHECK.md` | Manual spot-check of 10 merge events — PASS, 0 false positives |
| `Phase 3/migrate.py` + `migrations/*.sql` | Idempotent SQLite migration runner + 4 SQL files |
| `Phase 3/dedupe.py` | `insert_or_dedupe_reference()` — the single mutation path; Branches A–E |
| `Phase 3/db_loader.py` | Phase 2 → DB writer |
| `Phase 3/reference_harvester.py` | pdfplumber-based PDF reference extractor |
| `Phase 3/test_*.py` | 51/51 tests pass |
| `memory/project_t3_phase3_spec.md` | Verbatim course spec for Phase 3 |

**Total:** 91/91 tests pass across Phases 2 and 3.

## Why this is a snapshot, not the live copy

Phase 3 code uses `_HERE.parents[2]` to find `Article_Finder/` (for `normalize_doi`, `normalize_title`). From the canonical working directory, that resolves correctly to `COGS 160/`. From inside `Knowledge_Atlas/Track 2/Task 3/Phase 3/`, it would resolve to `COGS 160/Knowledge_Atlas/`, which doesn't contain `Article_Finder`. The mirror is therefore reading material for the grader — to **run** the code, use the canonical path above.

This matches the Task 2 mirror pattern. The Task 2 mirror at `Knowledge_Atlas/Track 2/Task 2/` is also a grading snapshot, not a runnable copy.

## How to reproduce the DB from these sources

See `MANIFEST.md` § "Reproducing the Phase 3 run" for the exact command sequence. The reproduction starts from the canonical working directory and writes:
1. `Track 2/Task 3/Phase 2/search_results.json` (Phase 2 output)
2. `Track 2/Task 3/task3_pipeline_lifecycle.db` (Phase 3 source-of-truth DB)
3. `Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db` (materialized snapshot via `VACUUM INTO`)

The materialized snapshot is content-equal to the local DB. Both have hash `3075d06e4b3201bef0ab47414f70d9368f22a72febefd23490222e5570e31592` after the run documented in MANIFEST.

## Path deviations from course spec

Documented in `MANIFEST.md` § "Path deviations". Briefly: three substitutions were required because referenced course-staff scripts and prototyping corpora do not exist on this machine. The substitutes are local equivalents (built from scratch where the AE coordination scripts were unavailable; the 20 local PDFs in `Part 2 Pdfs/` and `Part_One_10pdfs/` substitute for the 46-PDF review corpus the spec referenced).

## Active constraints

- Local DB and runtime JSON outputs are gitignored (see `.gitignore`)
- The materialized snapshot at `Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db` is **not** committed in this branch (binary artifact, reproducible from these sources)
- Never push to bare `git push` — only `git push fork <branch>` (see `feedback_push_safety` memory)
- Never commit `SERPAPI_KEY` — `.env` is gitignored
