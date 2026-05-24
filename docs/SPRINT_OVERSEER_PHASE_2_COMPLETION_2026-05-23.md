# Sprint OVERSEER Phase 2 Completion Report

**Date**: 2026-05-23
**Version**: dependency_overseer Phase 2 (Article Finder bridge)
**Source authorities**:
- `docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md`
- `docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md` (P7, P14, P25, P26, OR3)
- `docs/SPRINT_OVERSEER_PHASE_1_COMPLETION_2026-05-23.md`
- `docs/AF_PIPELINE_RECON_2026-04-27.md`

## Summary

Phase 2 of the dependency overseer shipped in four commits (6d4959e → 513b4f7) plus this report. The Article Finder bridge is active: the four new artefact kinds are registered, `cross_db_sync_events` is no longer scaffold, the candidate PDF state machine works, the AF read-only connector is in place, the async reconciler tick pairs AF state with KA state, the P25 soft-stuck routing is live, and two new verifier checks (`cross_db_sync`, `abstract_source_provenance`) enforce the Phase 2 invariants. 220 overseer tests pass; the live lifecycle DB passes the strict verifier with 17/17 checks.

## Acceptance criteria status (Phase 2 spec §10)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Four new artefact kinds appear in `artefact_kinds` (idempotent seed) | ✓ | `artefact_kinds.json` v2; seed script inserted 4 new rows, skipped existing 3 |
| 2 | AF connector opens the live AF DB read-only | ✓ | Live smoke test: 16,257 papers visible; schema_version=6; writes fail |
| 3 | Reconciler tick is a no-op on clean state; inserts paired KA artefacts on new AF rows | ✓ | `tests/test_overseer_article_finder_reconciler.py`; live tick inserted 3 pending events for 3 `processed_partial` AF papers |
| 4 | AF↔KA disagreement flips events to unresolved and raises blocking completion_queue | ✓ | `test_tick_flags_unresolved_on_signature_drift` |
| 5 | State machine: every documented transition allowed; undocumented rejected; transitions emit dependency edges | ✓ | `tests/test_overseer_candidate_pdf_state.py` (11 tests) |
| 6 | Abstract-source provenance verifier rejects unresolved sources | ✓ | `tests/test_overseer_abstract_provenance.py` (10 tests) + `tests/test_overseer_phase2_verifier_checks.py` |
| 7 | Soft-stuck progress-marker → medium completion_queue; worker not killed | ✓ | `tests/test_overseer_progress_marker_heartbeats.py` (8 tests) |
| 8 | Phase 2 round-trip: AF → reconciler → state machine → extracted → verifier pass | ✓ | `tests/test_overseer_phase2_round_trip.py` |
| 9 | All Phase 1 tests continue to pass (no regressions) | ✓ | 163 Phase 1 tests + 57 Phase 2 tests = 220 total, all passing |
| 10 | Strict verifier on live lifecycle DB exits 0 | ✓ | `python3 scripts/verify_dependency_overseer_contract.py --strict --db 160sp/pipeline_lifecycle_full.db` → overall_passed: True, 17/17 checks |
| 11 | This ship report covers each criterion | ✓ | This document |

**Overall**: 11/11 Phase 2 acceptance criteria met.

## Files Changed

| File | Status | Purpose |
|------|--------|---------|
| `docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md` | NEW | Phase 2 implementation contract |
| `contracts/schemas/dependency_overseer/artefact_kinds.json` | MODIFIED (v1→v2) | +4 kinds: article_finder_candidate, abstract, pdf_artifact, ocr_artifact |
| `overseer/article_finder_connector.py` | NEW | Read-only AF DB connector, paper_signature, iter_papers |
| `overseer/candidate_pdf_state.py` | NEW | 6-state machine with allowed-transitions table |
| `overseer/abstract_provenance.py` | NEW | Vocabulary-resolved source enforcement |
| `overseer/article_finder_reconciler.py` | NEW | Async tick(); pending → matched/unresolved logic |
| `overseer/watchdog.py` | MODIFIED | + soft_stuck_tick() (P25) |
| `overseer/verifier_data.py` | MODIFIED | + _check_cross_db_sync, _check_abstract_source_provenance |
| `scripts/dependency_overseer_reconciler_tick.py` | NEW | One-shot wrapper (cron-able) |
| `tests/test_overseer_article_finder_connector.py` | NEW | 10 tests |
| `tests/test_overseer_candidate_pdf_state.py` | NEW | 11 tests |
| `tests/test_overseer_abstract_provenance.py` | NEW | 10 tests |
| `tests/test_overseer_article_finder_reconciler.py` | NEW | 10 tests |
| `tests/test_overseer_progress_marker_heartbeats.py` | NEW | 8 tests |
| `tests/test_overseer_phase2_verifier_checks.py` | NEW | 7 tests |
| `tests/test_overseer_phase2_round_trip.py` | NEW | 1 round-trip test |

Lines added: ~1,800 (modules + tests + spec).

## Key Design Decisions

1. **Asynchronous reconciler (resolves synthesis OR3).** The reconciler runs in its own tick rather than as a synchronous half of an AF write. AF writes its half (no overseer involvement); a 60s reconciler tick pairs events and detects drift. The verifier flags unresolved rows older than 300s and raises a blocking completion_queue item. SQLite has no native distributed-transaction support, so synchronous two-phase commit was not pursued.

2. **AF status field interpretation.** Live AF DB inspection showed 4 statuses: `candidate` (16196), `pending_scorer` (40), `rejected` (18), `processed_partial` (3). The MVP reconciler uses `processed_partial` as the proxy for "accepted by Atlas." This is configurable per tick; production deployment can tune to a richer signal (e.g., `atlas_intake_decision` or `ae_corpus_match_status`).

3. **Signature normalization for AF↔KA matching.** `paper_signature` is SHA-256 over a canonical JSON of `[doi, canonical_paper_id, title]` with each component stripped and lowercased. Catches material identity changes; tolerates casing and whitespace differences. Live signatures verified deterministic and order-invariant.

4. **State machine kinds vs states.** Each post-`metadata_only` state maps to a distinct artefact kind (`abstract`, `pdf_artifact`, `ocr_artifact`, `article_epistemic_record`). State transitions register the related artefact with `field_path=to_state` and add a `derived_from` dependency edge from the candidate. This keeps state machine evidence in the dependency graph rather than as a transient field.

5. **Soft-stuck severity is medium, not blocking.** Progress-marker stagnation does not kill the worker; the work may be genuinely slow. A medium completion_queue row alerts reviewers; idempotent enqueueing prevents row proliferation.

6. **Abstract-source provenance is structural in Phase 2.** The verifier checks the `derived_from` edge from each abstract artefact back to an article_finder_candidate; the state-machine API (`transition()`) is the contractual write path. Content-layer source-label inspection (the actual string stored in the abstract content) is a Phase 3 concern when content payloads land.

## Integration Points

- **Article Finder (read-only).** `/Users/davidusa/REPOS/Article_Finder_v3_2_3/data/article_finder.db`. AF code is unchanged. The overseer connector handles defensive schema variation.
- **Live lifecycle DB.** Reconciler tick on the live 160sp DB inserted 3 article_finder_candidate artefacts + 3 pending cross_db_sync_events rows (for the 3 AF papers at `processed_partial`). Live verifier passes all 17 checks.
- **Phase 1 builder.** The state machine's transition to `extracted` registers an `article_epistemic_record` artefact (with `field_path='extracted'`). The Phase 1 builder writes the record content separately under the no-field_path artefact for the same paper. Future work (OVERSEER-PHASE-2-BUILDER-INTEGRATION) may consolidate these.

## Testing Status

- 220 overseer tests passing locally on Python 3.14.2.
- Live lifecycle DB passes strict verifier (exit 0; 17/17 checks; 2 new checks added in Phase 2).
- Phase 2 round-trip proof passes: AF accepted paper → reconciler → state machine (5 transitions) → builder → reconciler upgrades to matched → verifier pass.

## Next Steps

Phase 2 spec §11 lists open implementation questions still appropriate to revisit in production:

- **OIQ #1 — AF DB path resolution**: Phase 2 hardcodes `~/REPOS/Article_Finder_v3_2_3/data/article_finder.db`. Move to a config file when more candidate paths are needed.
- **OIQ #2 — Reconciler daemon-mode wrapper**: Phase 2 ships the script. Daemon wrapping deferred to Phase 4.
- **OIQ #3 — AF status field for "accepted"**: `processed_partial` is the MVP proxy. Production may switch to `atlas_intake_decision='accept'` or richer multi-field criteria.
- **OIQ #4 — Soft-stuck threshold**: default N=5. Tunable in worker config.
- **OIQ #5 — PDF hash normalization across AF and KA**: AF's `pdf_sha256` field convention not yet aligned with KA. Will surface in Phase 4 production probing.
- **OIQ #6 — Backfill policy**: Phase 2 syncs forward only. Historical AF state remains unprocessed.

New TASKS.md follow-ups (to be added):

- **OVERSEER-PHASE-3** — LLM enrichment governance (synthesis Phase 6 / OR9).
- **OVERSEER-PHASE-4** — extend overseer to topics, DYK, search, reports; backpressure on rebuild_queue.
- **OVERSEER-RENDER-VERIFIER** — pick headless library and implement verifier_render.
- **OVERSEER-PNU-BUILDER** — per-PNU content_hashes history writer.
- **OVERSEER-AF-DAEMON** — daemon wrapper around reconciler_tick (Phase 4).
- **OVERSEER-AF-STATUS-CRITERION** — richer AF "accepted" signal (replace processed_partial proxy).

Subsequent phases each get their own implementation spec.
