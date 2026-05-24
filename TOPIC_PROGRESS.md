# TOPIC_PROGRESS.md — Knowledge_Atlas

Per the root-level CLAUDE.md "Live Conversation Topic Tracking" protocol.

---

## TOP-OVERSEER: Dependency Overseer (Phase 1)

**Status**: COMPLETED — 2026-05-23 (Phase 1 ship)
**Owner**: CW (Claude Code, Opus 4.7 1M)
**Linked tasks**: TASKS.md "Newly Added — 2026-05-23 (Dependency Overseer Phase 1)"

### Key decisions

- Followed the panel synthesis (`docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md`) and impl spec (`docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md`) verbatim, with one bounded set of adaptations: file paths in impl spec §2 mapped to the actual repo convention (`contracts/schemas/dependency_overseer/`, `scripts/migrations/`, top-level `overseer/`). This matches the existing companion-contract precedent.
- Heartbeat-based lease semantics (P7) implemented with autocommit mode (`isolation_level=None`) so explicit BEGIN IMMEDIATE in `transaction()` works; default pysqlite implicit-transaction mode collided with explicit BEGIN.
- Fencing tokens (P24) implemented as a CAS-style WHERE clause in `update_with_hashes`: writes carrying a stale token raise `FencingTokenMismatch`. The watchdog increments the artefact's fencing token on every reclaim, invalidating any pending writes from the dead worker.
- Vocabulary split (P26) implemented: closed enums in `schemas/status_vocabularies.json` enforced as DB `CHECK` constraints; open vocabularies in `vocabulary_registry` table seeded from PsychoPy and CNFA-canonical sources (70 canonical entries across 5 kinds).
- Two-tier hashing (P27): every active artefact carries both `raw_hash` and `semantic_hash`; only semantic_hash changes propagate cascade. Negative round-trip test confirms raw-only changes do not enqueue rebuilds.
- Active-vs-scaffold table split (P28): 17 active tables (writes in Phase 1); 5 scaffold-only tables (schema lands, no writes until activating phase). A verifier check (`scaffold_tables_empty`) catches premature Phase 2/3 writes.
- Cascade bound: 100 dependents per source (impl spec §14 OIQ #3 recommended value). When exceeded, a `completion_queue` row with severity 'high' is raised.

### Files and Artifacts

| File | Location | Type | Change |
|------|----------|------|--------|
| `DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md` | `docs/` | Design doc | NEW — 747 lines; 6-reviewer panel synthesis, B1-B12 + P1-P28 invariants, R1-R10 rejected suggestions, final schema, verifier contract, repair loop, phased plan, OR1-OR10 open risks |
| `DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md` | `docs/` | Engineering spec | NEW — 1151 lines; full SQL, JSON shapes, normalization rule v1, Python skeletons, 17-file test plan, 12 acceptance criteria, 7 open implementation questions |
| `dependency_overseer.sql` | `contracts/schemas/dependency_overseer/` | SQL schema | NEW — 400 lines; 22 tables (17 active + 5 scaffold), CHECK constraints, FKs, 11 indices |
| `2026_05_23_dependency_overseer.sql` | `scripts/migrations/` | SQL migration | NEW — dated copy of canonical schema |
| `status_vocabularies.json` | `contracts/schemas/dependency_overseer/` | Config | NEW — 28 closed-enum keys (P26) |
| `component_types.json` | `contracts/schemas/dependency_overseer/` | Config | NEW — per-component normalization hints (rule v1) |
| `absence_reasons.json` | `contracts/schemas/dependency_overseer/` | Config | NEW — 10 controlled absence_reason values (P10) |
| `artefact_kinds.json` | `contracts/schemas/dependency_overseer/` | Config | NEW — 3 Phase 1 kinds (pnu_row, article_epistemic_record, article_detail_json) |
| `psychopy_seed.json` | `contracts/schemas/dependency_overseer/` | Seed data | NEW — 70 canonical vocab entries (16 instruments, 18 measures, 17 constructs, 12 methods, 7 abstract sources) |
| `dependency_overseer_init.py` | `scripts/` | Init script | NEW — idempotent migration applier (CREATE TABLE IF NOT EXISTS) |
| `dependency_overseer_seed.py` | `scripts/` | Init script | NEW — idempotent seeder for vocabulary_registry + artefact_kinds (INSERT OR IGNORE) |
| `verify_dependency_overseer_contract.py` | `scripts/` | Verifier wrapper | NEW — runs strict verifier, exits 0 pass / 1 fail |
| `db.py` | `overseer/` | Python module | NEW — connection helper (WAL, FK ON, autocommit isolation_level=None), transaction() context manager |
| `ids.py` | `overseer/` | Python module | NEW — deterministic artefact_id, UUID4 helpers for build_run/queue/event/check ids, vocab_value_id, support_set_id_for |
| `normalization.py` | `overseer/` | Python module | NEW — rule v1 deterministic normalization (whitespace, keys, list order, case, cosmetic_only); UnknownComponentTypeError on unregistered types |
| `content_hashes.py` | `overseer/` | Python module | NEW — compute_raw_hash, compute_semantic_hash, compute_input_fingerprint (all 'sha256:<hex>') |
| `artefact_registry.py` | `overseer/` | Python module | NEW — register, get, get_by_entity, update_with_hashes (fencing-token enforced; raises FencingTokenMismatch), increment_fencing_token, mark_stale, mark_fresh, tombstone, list_by_kind |
| `dependency_edges.py` | `overseer/` | Python module | NEW — add_edge (idempotent, reactivates tombstoned), tombstone_edge, parents_of, children_of |
| `support_sets.py` | `overseer/` | Python module | NEW — capture (idempotent on member-derived id), compute_support_set_hash, get_members, get_hash |
| `vocabulary_registry.py` | `overseer/` | Python module | NEW — get, add_candidate, list_canonicals/candidates, canonical_for, mark_as_synonym |
| `rebuild_queue.py` | `overseer/` | Python module | NEW — enqueue (idempotent), claim_one (atomic, severity-ordered, fencing-token increment), heartbeat, complete, fail (quarantine threshold=5), queue_depth, oldest_queued_age_seconds |
| `watchdog.py` | `overseer/` | Python module | NEW — tick() reclaims worker_heartbeats past timeout; increments fencing_token to invalidate dead-worker writes; quarantines past threshold; enqueues completion_queue on quarantine |
| `completion_queue.py` | `overseer/` | Python module | NEW — enqueue (idempotent on artefact+reason), mark_in_review, resolve, waive, list_open(min_severity), has_blocking_open |
| `build_runs.py` | `overseer/` | Python module | NEW — start (CHECK status), finish (CHECK status), get |
| `article_epistemic_builder.py` | `overseer/` | Python module | NEW — Stage 1 deterministic builder; primary-claim rule cascade with claim_origin recording; answer-shape rule cascade with rule_trace_json; defeater target_kind enforcement; atomic write with fencing-token validation |
| `verifier_data.py` | `overseer/` | Python module | NEW — 15 Phase 1 checks (referential, uniqueness, hash presence, semantic-hash propagation, normalization-rule pinning, closed-enum membership, vocab integrity, kind registration, queue heartbeat invariants, fencing-token monotonicity, defeater target-typing, claim canonicalization, belief-network freshness, answer-shape rule-trace, scaffold-empty); verify_strict() + report_to_dict() |
| `repair_loop.py` | `overseer/` | Python module | NEW — route(check) maps failures to RepairAction; execute applies; route_and_execute processes a full report; can_promote() is the release gate (blocks on verifier fail, stale required artefacts, blocking completion items) |
| `last_mile_checks.py` | `overseer/` | Python module | NEW — record(), most_recent_per_artefact_and_kind(), has_recent_failures(); writes to last_mile_production_checks |
| `invalidator.py` | `overseer/` | Python module | NEW — invalidate_on_source_change(); only semantic_hash changes propagate; cascade-bound alert when dependents > 100 |
| `test_overseer_normalization.py` | `tests/` | Test | NEW — 18 tests |
| `test_overseer_content_hashes.py` | `tests/` | Test | NEW — 16 tests |
| `test_overseer_artefact_registry.py` | `tests/` | Test | NEW — 11 tests |
| `test_overseer_dependency_edges.py` | `tests/` | Test | NEW — 8 tests |
| `test_overseer_support_sets.py` | `tests/` | Test | NEW — 8 tests |
| `test_overseer_vocabulary_registry.py` | `tests/` | Test | NEW — 11 tests |
| `test_overseer_rebuild_queue.py` | `tests/` | Test | NEW — 15 tests |
| `test_overseer_watchdog.py` | `tests/` | Test | NEW — 5 tests |
| `test_overseer_completion_queue.py` | `tests/` | Test | NEW — 10 tests |
| `test_overseer_build_runs.py` | `tests/` | Test | NEW — 5 tests |
| `test_overseer_article_epistemic_builder.py` | `tests/` | Test | NEW — 17 tests |
| `test_overseer_verifier_data.py` | `tests/` | Test | NEW — 14 tests |
| `test_overseer_repair_loop.py` | `tests/` | Test | NEW — 10 tests |
| `test_overseer_last_mile_checks.py` | `tests/` | Test | NEW — 7 tests |
| `test_overseer_invalidation.py` | `tests/` | Test | NEW — 4 tests |
| `test_overseer_round_trip.py` | `tests/` | Test | NEW — 2 tests (Phase 1 acceptance #8/#9) |
| `conftest.py` | `tests/` | Test config | MODIFIED — added `overseer_db` fixture (autocommit mode, schema applied); preserved existing `aepl_db` fixtures |
| `pipeline_lifecycle_full.db` | `160sp/` | DB | MODIFIED — 22 new tables added (additive only; 1428 papers / 37128 lifecycle_events preserved); 70 vocab rows + 3 kinds rows seeded |
| `pipeline_lifecycle_full.db.bak-*-before_overseer_v1` | `backups/dependency_overseer/` | DB backup | NEW — durable backup taken before migration |
| `SPRINT_OVERSEER_PHASE_1_COMPLETION_2026-05-23.md` | `docs/` | Sprint report | NEW — Phase 1 ship report, all 12 acceptance criteria |

### Commits

| Commit | Subject | Files | Insertions |
|--------|---------|-------|------------|
| 1b27dfc | docs(epistemics): land dependency overseer synthesis and Phase 1 impl spec | 2 | 1898 |
| 6fb2918 | feat(overseer): land Phase 1 foundation — schema, seeds, normalization, hashing | 14 | 1922 |
| a74b43b | feat(overseer): land storage layer | 11 | 1336 |
| 8a6a6d3 | feat(overseer): land queue, watchdog, completion queue, build runs | 10 | 1156 |
| ac8b799 | feat(overseer): land Stage 1 article_epistemic_builder | 2 | 826 |
| 3540cbe | feat(overseer): land strict verifier, repair loop, last-mile recorder | 7 | 1404 |
| 8d95fd8 | feat(overseer): land invalidator + Phase 1 round-trip proofs | 3 | 405 |

### Test results

- 163 overseer tests passing locally on Python 3.14.2 / pytest 9.0.2.
- Live `160sp/pipeline_lifecycle_full.db` passes `python3 scripts/verify_dependency_overseer_contract.py --strict` with exit code 0.

### Still open within this topic (carried to TASKS.md)

- OVERSEER-PHASE-2 — Article Finder bridge
- OVERSEER-PHASE-3 — LLM enrichment governance
- OVERSEER-PHASE-4 — extend to topics, DYK, search, reports
- OVERSEER-RENDER-VERIFIER — headless-browser-backed `verifier_render`
- OVERSEER-PNU-BUILDER — per-PNU content_hashes history writer
- OVERSEER-IMPL-SPEC-PATH-NOTE — align impl spec §2 paths with shipped repo conventions
