# TOPIC_PROGRESS.md — Knowledge_Atlas

Per the root-level CLAUDE.md "Live Conversation Topic Tracking" protocol.

---

## TOP-OVERSEER-2: Dependency Overseer (Phase 2 — Article Finder bridge)

**Status**: COMPLETED — 2026-05-23 (Phase 2 ship)
**Owner**: CW (Claude Code, Opus 4.7 1M)
**Linked tasks**: TASKS.md "Newly Added — 2026-05-23 (Dependency Overseer Phase 2)"

### Key decisions

- Resolved synthesis OR3 with an asynchronous reconciler (60s tick) rather than synchronous two-phase commit. SQLite has no native distributed-transaction support; the verifier check `_check_cross_db_sync` flags unresolved events older than 300s, providing the safety net.
- AF connector is strictly read-only (`mode=ro` URI). AF code is unchanged by Phase 2; the overseer never writes to AF.
- AF status filter for "accepted by Atlas": MVP uses `processed_partial` (3 rows match in the live AF DB at 16,257 papers total). Configurable per tick. Production-grade criterion is tracked as OVERSEER-AF-STATUS-CRITERION.
- Each post-`metadata_only` state in the candidate-PDF state machine maps to a distinct artefact kind (`abstract`, `pdf_artifact`, `ocr_artifact`, `article_epistemic_record`). State evidence lives in the dependency graph (derived_from edges), not as a transient field.
- Soft-stuck severity is `medium`, not `blocking`. Progress-marker stagnation alerts reviewers; the worker is not killed because slow progress may still be real progress. Idempotent enqueue prevents row proliferation.
- Abstract-source provenance is structural in Phase 2 (derived_from edge check); content-layer source-label inspection is deferred to Phase 3 when content payloads land.

### Files and Artifacts

| File | Location | Type | Change |
|------|----------|------|--------|
| `DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md` | `docs/` | Phase 2 spec | NEW — 213 lines; scope, AF surface, OR3 resolution, state machine, verifier additions, P25, test plan, 11 acceptance criteria, 6 open implementation questions |
| `SPRINT_OVERSEER_PHASE_2_COMPLETION_2026-05-23.md` | `docs/` | Ship report | NEW — all 11 acceptance criteria covered |
| `artefact_kinds.json` | `contracts/schemas/dependency_overseer/` | Config | MODIFIED v1→v2 — added article_finder_candidate, abstract, pdf_artifact, ocr_artifact |
| `article_finder_connector.py` | `overseer/` | Python module | NEW — resolve_af_db_path, connect_readonly (URI mode=ro), iter_papers, paper_signature (SHA-256 over normalised doi+canonical+title), schema_version |
| `candidate_pdf_state.py` | `overseer/` | Python module | NEW — STATES, ALLOWED_TRANSITIONS, STATE_TO_RELATED_KIND, ensure_candidate, transition (idempotent + adds derived_from edge), InvalidTransitionError |
| `abstract_provenance.py` | `overseer/` | Python module | NEW — is_allowed_source, canonical_source, require_allowed_source, list_allowed_sources; UnknownAbstractSourceError |
| `article_finder_reconciler.py` | `overseer/` | Python module | NEW — tick(); pending → matched/unresolved logic; ReconcilerReport; idempotent |
| `watchdog.py` | `overseer/` | Python module | MODIFIED — added soft_stuck_tick() (P25), SOFT_STUCK_INTERVAL_MULTIPLIER constant, SoftStuckFlag dataclass |
| `verifier_data.py` | `overseer/` | Python module | MODIFIED — added _check_cross_db_sync, _check_abstract_source_provenance; total checks 15 → 17 |
| `dependency_overseer_reconciler_tick.py` | `scripts/` | Wrapper | NEW — cron-able one-shot tick; JSON report to stdout |
| `test_overseer_article_finder_connector.py` | `tests/` | Test | NEW — 10 tests |
| `test_overseer_candidate_pdf_state.py` | `tests/` | Test | NEW — 11 tests |
| `test_overseer_abstract_provenance.py` | `tests/` | Test | NEW — 10 tests |
| `test_overseer_article_finder_reconciler.py` | `tests/` | Test | NEW — 10 tests |
| `test_overseer_progress_marker_heartbeats.py` | `tests/` | Test | NEW — 8 tests |
| `test_overseer_phase2_verifier_checks.py` | `tests/` | Test | NEW — 7 tests |
| `test_overseer_phase2_round_trip.py` | `tests/` | Test | NEW — 1 end-to-end round-trip test |
| `pipeline_lifecycle_full.db` | `160sp/` | DB | MODIFIED — 4 new kind rows seeded; live reconciler smoke test added 3 article_finder_candidate artefacts + 3 cross_db_sync_events pending rows |

### Commits

| Commit | Subject | Files | Insertions |
|--------|---------|-------|------------|
| 6d4959e | docs(overseer): land Phase 2 implementation spec (Article Finder bridge) | 1 | 213 |
| 85adaf0 | feat(overseer): Phase 2 — register 4 kinds, AF connector, state machine, abstract provenance | 9 | 786 |
| 8b5ab3a | feat(overseer): Phase 2 — Article Finder ↔ KA reconciler (async tick) | 3 | 440 |
| 513b4f7 | feat(overseer): Phase 2 — P25 soft-stuck + cross-DB sync + abstract provenance verifier checks | 4 | 394 |

### Test results

- 220/220 overseer tests passing (Phase 1: 163 + Phase 2: 57).
- Live `160sp/pipeline_lifecycle_full.db` passes strict verifier with 17/17 checks.
- Phase 2 round-trip proof: AF accepted paper → reconciler → state machine (5 transitions) → builder → reconciler upgrades to matched → verifier pass.

### Still open within this topic (carried to TASKS.md)

- OVERSEER-AF-STATUS-CRITERION — Replace `processed_partial` proxy with richer AF "accepted" signal.
- OVERSEER-AF-DAEMON — Daemon-mode wrapper around reconciler_tick.
- OVERSEER-AF-PDF-HASH — Normalise AF↔KA PDF hash conventions.
- OVERSEER-PHASE-2-BUILDER-INTEGRATION — Consolidate state-machine `extracted` artefact with Phase 1 builder output.

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
