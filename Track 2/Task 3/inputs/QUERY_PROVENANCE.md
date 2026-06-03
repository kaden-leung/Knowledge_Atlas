# Vendored Input — `query_results.json`

`query_results.json` in this directory is the **canonical output of Track 2 / Task 2, Phase 3**
(the gap-driven query generator). It contains the 10 Boolean + AI-citation query pairs that
Task 3's search, triage, and verification stages consume.

## Why it lives here

Task 3 previously read this artifact by reaching **sideways** into a sibling directory
(`../Task 2/Phase 3/query_results.json`). That created a hidden repository-structure
assumption: Task 3 would only verify correctly if the Task 2 directory happened to sit
next to it. To make Task 3 **self-contained and independently reproducible**, the artifact
was copied here and every Task 3 module now reads this local copy.

The dependency is therefore now:

> Task 3 depends on a committed input artifact — not on a sibling directory existing.

This is normal pipeline behavior: Task 2 generated these queries; Task 3 consumes the
resulting artifact.

## Source and integrity

- **Original source:** `Track 2/Task 2/Phase 3/query_results.json`
  (canonical Task 2 submission — branch `track2/kaden-leung-task2`)
- **Contents:** copied verbatim. **No modifications were made to the query data.**
- **Query set:** 10 queries, IDs `SC3, SC3, SC1, L3, NM1, NM7, NM2, L4, CSMP1, NVR1`,
  with VOI scores 0.443–0.478. These VOI scores — the only field Task 3's Stage 2B
  triage reads — are identical to every prior Task 3 run, so vendoring this file does not
  change any Task 3 metric, decision, or verifier result.

## Consumers (modules that read this file)

`verify_track2_workflow.py`, `run_pipeline.py`, `Phase 2/conftest.py`,
`Phase 2/search_runner.py`, `Phase 4/stage2b_triage_decision.py`,
`Phase 4/abstract_triage.py`, `Phase 6/generate_prisma_report.py`.
