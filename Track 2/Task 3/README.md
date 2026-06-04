# Track 2 · Task 3 — CNFA Literature Discovery Pipeline

**Author:** Kaden Leung · UCSD COGS 160 · Branch `track2/kaden-leung-task3`

> **Start at [GRADER_GUIDE.md](GRADER_GUIDE.md).** It has the architecture diagram, the one-command verification, the key results, and the evidence map. This README is only a signpost.

## One-command verification

```bash
cd "Track 2/Task 3"
python3 verify_track2_workflow.py        # → CHAIN: 9/9 checks passed
```

No `pip install`, API key, or network access is required to verify: the command reads the committed database and JSON evidence using only the Python standard library. To re-run the *live* pipeline instead, see [requirements.txt](requirements.txt) and `setup_verify.py`.

## What this is

A gap-driven pipeline that turns CNFA knowledge gaps (Task 2) into targeted queries, retrieves and triages candidate papers, attempts PDF acquisition, and hands accepted papers to a downstream validator. Phases 2–7, full offline test suite passing (`186 passed, 1 skipped`), end-to-end chain verifier.

**Central finding:** retrieval coverage, not triage accuracy, is the dominant source of missed relevant literature — see [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md).

## Reading order

1. [GRADER_GUIDE.md](GRADER_GUIDE.md) — entry point (architecture, verification, results, limits)
2. [BENCHMARK_EVALUATION.md](BENCHMARK_EVALUATION.md) — authoritative metrics
3. [PROVEIT_WORKS.md](PROVEIT_WORKS.md) — one paper traced through all 10 lifecycle stages
4. [MANUAL_REVIEW_PACKET.md](MANUAL_REVIEW_PACKET.md) — evidence for the autograder's manually capped points
5. [MANIFEST.md](MANIFEST.md) — full audit trail and the authoritative-database note

## Authoritative database

`Track 2/Task 3/task3_pipeline_lifecycle.db` is committed and is the single source of truth the verifier reads. It is a reproducibility artifact, not meant to be regenerated during grading. (A separate `Knowledge_Atlas/data/ka_payloads/pipeline_lifecycle_full.db` is an earlier, stale course-path placeholder — not used here.)
