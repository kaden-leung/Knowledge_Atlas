# Track 2 Task 3 — Contract and Component Version Registry

This file is the single source for versioned contract and module bumps.
Update it whenever a contract document or a versioned output schema changes.

## Contracts

| Contract | Current version | File |
|---|---|---|
| Search runner | v1.2.0 | [Phase 2/SEARCH_RUNNER_CONTRACT.md](Phase%202/SEARCH_RUNNER_CONTRACT.md) |
| Search results JSON schema | v1.1.0 | [Phase 2/schema/search_results.schema.json](Phase%202/schema/search_results.schema.json) |
| Schema (article_references DDL) | v1.0.0 | [Phase 3/SCHEMA_CONTRACT.md](Phase%203/SCHEMA_CONTRACT.md) |
| Reference harvester | v1.0.0 | [Phase 3/REFERENCE_HARVESTER_CONTRACT.md](Phase%203/REFERENCE_HARVESTER_CONTRACT.md) |
| Stage 1 triage | v1.0.0 | [Phase 4/STAGE1_TRIAGE_CONTRACT.md](Phase%204/STAGE1_TRIAGE_CONTRACT.md) |
| Abstract collector | v1.0.0 | [Phase 4/ABSTRACT_COLLECTOR_CONTRACT.md](Phase%204/ABSTRACT_COLLECTOR_CONTRACT.md) |
| Triage decision | v1.0.0 | [Phase 4/TRIAGE_DECISION_CONTRACT.md](Phase%204/TRIAGE_DECISION_CONTRACT.md) |
| PDF acquisition | v1.0.0 | [Phase 5/PDF_ACQUISITION_CONTRACT.md](Phase%205/PDF_ACQUISITION_CONTRACT.md) |

## DB Migrations

| Migration | Description | Added |
|---|---|---|
| 001_article_references.sql | Core candidate buffer table | Phase 3 initial |
| 002_lifecycle_transitions.sql | Audit log for all state changes | Phase 3 initial |
| 003_v_acquisition_queue.sql | View: Phase 5 read path | Phase 3 initial |
| 004_indexes.sql | PRISMA funnel and dashboard indexes | Phase 6 |
| 005_model_version.sql | model_version, voi_breakdown, pipeline_version columns | Hardening v1 |

## Classifier Modes

| Mode label | Description |
|---|---|
| `keyword_fallback_v1` | CNFA keyword list; no centroid file; current production mode |
| `hierarchical_v{n}` | HierarchicalClassifier with centroid file (pending — atlas_shared required) |

## Hardening Version

| Component | Version |
|---|---|
| Human review gate | v1 (policy_clearance.json + human_review_log.json; 30-day sign-off) |
| setup_verify.py | v2 (--mode pr-only|full) |
| pipeline_config.py | v1 |
| pipeline_logger.py | v1 (JSONL; logs/ gitignored) |
| quarantine.py | v1 |
| CI workflow | v1 (6 jobs) |
