# Dependency Overseer Phase 2 Implementation Spec

Date: 2026-05-23
Status: Phase 2 implementation contract
Depends on:
- `docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md` (design contract; B11, P14, OR3)
- `docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md` (Phase 1)
- `docs/SPRINT_OVERSEER_PHASE_1_COMPLETION_2026-05-23.md` (Phase 1 ship report)
- `docs/AF_PIPELINE_RECON_2026-04-27.md` (Article Finder repo recon)
- `docs/ARTICLE_INTAKE_AF_INTEGRATION_CONTRACT_2026-03-24.md` (existing AF integration contract)

Phase 2 activates the four scaffold-only tables and four new artefact kinds named in the synthesis Phase 6 plan, plus the P25 progress-marker heartbeats deferred from Phase 1. Phase 2 does **not** modify Article Finder's own database; it reads from AF's local DB and writes overseer state into the Knowledge_Atlas lifecycle DB.

## 1. Scope

In scope for Phase 2:

- Activate `cross_db_sync_events` (no longer scaffold-only).
- Register four new artefact kinds: `article_finder_candidate`, `abstract`, `pdf_artifact`, `ocr_artifact`.
- Wire the candidate PDF state machine (`metadata_only → abstract_only → candidate_pdf_unverified → pdf_verified → ocr_ready → extracted`).
- Implement abstract-source provenance (per companion contract §10 allowed sources).
- Implement the Article Finder peer-DB reconciler (async, see §3 below).
- Implement the Article Finder peer-DB sync verifier (`_check_cross_db_sync`).
- Implement P25 progress-marker heartbeats and soft-stuck routing.

Out of scope for Phase 2:

- LLM enrichment (Phase 3).
- Topics / DYK / search index (Phase 4).
- Modifying Article Finder's own schema or code (AF is read-only from the overseer's perspective).
- Backfilling historical AF state into the overseer. New AF state syncs forward from Phase 2 ship; historical reconciliation is a separate task.

## 2. Article Finder Surface

Article Finder lives at `/Users/davidusa/REPOS/Article_Finder_v3_2_3/`. Its canonical DB is `data/article_finder.db`. Relevant tables (per inspection 2026-05-23):

- `papers` — AF's candidate / triaged / accepted records
- `citations` — citation graph
- `claims` — AF's per-paper extracted claims
- `expansion_queue` — citation-expansion work
- `paper_embeddings`, `paper_facet_scores`, `facets`, `facet_nodes`, `node_centroids`
- `rules`, `schema_version`, `extracted_tables`

The overseer reads from AF.papers (and AF.citations, AF.claims as needed); it writes only to its own KA lifecycle DB.

**Connection helper:** `overseer/article_finder_connector.py` exposes `connect_readonly(path=None)` which opens the AF DB with `mode=ro` and resolves the path from a configurable candidate list (`data/article_finder.db` under the AF repo root by default, overridable).

## 3. Cross-DB Sync Model (resolving OR3)

The synthesis open risk OR3 named the unresolved question: sync vs async reconciler for the `accept_candidate` event.

**Phase 2 resolution: asynchronous reconciler.**

Rationale:

- Synchronous two-phase commit across two SQLite files is not natively supported and would require distributed-transaction tooling absent from the repo.
- AF and KA both serialize writes at the single-writer level. A logical `accept_candidate` decomposes into two side writes: AF flips a paper's status, KA registers the artefact and inserts the lifecycle row. A brief window where one side has the write and the other does not is acceptable as long as: (a) each side records the event in an event log immediately, and (b) the reconciler pairs the events within a bounded interval.
- The verifier check `_check_cross_db_sync` flags any `cross_db_sync_events` row with `status='unresolved'` older than a configurable threshold (default 5 minutes). Crossing the threshold raises a `completion_queue` row with severity `high`.

**Event flow for `accept_candidate`:**

1. AF writes its half (status flip on `papers` row). AF doesn't touch the overseer DB; the AF code path is unchanged.
2. The overseer's reconciler reads AF.papers periodically and detects new "accepted in AF" rows that don't yet have a paired KA artefact.
3. For each such row, the reconciler inserts an overseer `cross_db_sync_events` row with `status='pending'` and `event_kind='accept_candidate'`, plus an `artefact_registry` row of kind `article_epistemic_record` (or `article_detail_json`) for the paper.
4. The reconciler matches AF and KA hashes; if they agree on canonical paper_id and core metadata, the event status flips to `matched`.
5. If hashes disagree (canonical_paper_id collision, conflicting DOI, etc.), status flips to `unresolved` and a `completion_queue` row is raised.

A symmetric flow handles `tombstone_paper` and `registry_snapshot` events.

**Reconciler runs as a tick** (`overseer/article_finder_reconciler.py::tick(conn)`), similar to the watchdog. Default interval: 60 s.

## 4. Repository Layout

New files:

```
overseer/
    article_finder_connector.py   # read-only AF DB connection
    article_finder_reconciler.py  # async tick(): pair events, detect drift
    candidate_pdf_state.py        # state machine
    abstract_provenance.py        # abstract-source vocabulary check
scripts/
    dependency_overseer_phase2_register_kinds.py
        # idempotent: registers article_finder_candidate, abstract,
        # pdf_artifact, ocr_artifact in artefact_kinds
    dependency_overseer_reconciler_tick.py
        # one-shot reconciler tick; designed to be run as a cron job
tests/
    test_overseer_article_finder_connector.py
    test_overseer_article_finder_reconciler.py
    test_overseer_candidate_pdf_state.py
    test_overseer_abstract_provenance.py
    test_overseer_progress_marker_heartbeats.py
docs/
    DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md     (this file)
    SPRINT_OVERSEER_PHASE_2_COMPLETION_2026-05-23.md   (written at ship)
```

Modified files:

```
contracts/schemas/dependency_overseer/artefact_kinds.json
    + 4 new kinds (article_finder_candidate, abstract, pdf_artifact, ocr_artifact)
overseer/verifier_data.py
    + _check_cross_db_sync (active in Phase 2)
    + _check_abstract_source_provenance (new)
    - _check_scaffold_tables_empty (cross_db_sync_events removed from scaffold list)
overseer/rebuild_queue.py
    + heartbeat() activates progress_marker_unchanged_since logic (P25)
overseer/watchdog.py
    + soft-stuck routing on identical progress_marker for N intervals
```

## 5. Candidate PDF State Machine

The six states from synthesis P28 / impl spec §3:

```
metadata_only
    → abstract_only            (when abstract lands)
    → candidate_pdf_unverified (when PDF file present but identity unverified)
    → pdf_verified             (when PDF hash matches metadata-claimed identity)
    → ocr_ready                (when OCR artefact landed)
    → extracted                (when overseer-tracked extractor completed)
```

Each state is a distinct artefact_registry row. Transitions happen by:
1. Registering the next-state artefact (`register(kind='abstract', ...)`).
2. Adding a `dependency_edges` row `derived_from` linking new state to prior state.
3. Tombstoning the prior state if it should no longer be active (e.g., when `pdf_verified` lands, `candidate_pdf_unverified` is tombstoned).

The state machine module exposes `transition(conn, paper_id, from_state, to_state, support_hash)` returning the new artefact_id and validating the transition (only allowed pairs).

## 6. Abstract-Source Provenance

Per companion contract §10, allowed abstract sources are seeded in `vocabulary_registry` (Phase 1 already did this): `crossref`, `openalex`, `publisher_metadata`, `pdf_extracted`, `llm_summarized_from_pdf`, `manual`, `missing`. Phase 2 adds enforcement: every `abstract` artefact's content carries an `abstract_source` field whose value MUST resolve in `vocabulary_registry` for kind `abstract_source_label`. The new verifier check `_check_abstract_source_provenance` enforces this.

For `llm_summarized_from_pdf`: this source is allowed in Phase 2 but the actual generation falls under Phase 3 LLM governance. Phase 2 records the source label without invoking an LLM.

## 7. Verifier Additions

Two new checks land in Phase 2:

**`_check_cross_db_sync`** — Every `cross_db_sync_events` row with `status='unresolved'` older than `unresolved_threshold_seconds` (default 300) raises a failure. Stale unresolved rows mean the reconciler is not keeping up.

**`_check_abstract_source_provenance`** — For every active `abstract` artefact, the embedded `abstract_source` value must resolve in `vocabulary_registry` for kind `abstract_source_label`. Missing or unresolved values fail the check.

The `_check_scaffold_tables_empty` check loses `cross_db_sync_events` from its scaffold list — that table is now active.

## 8. P25 Progress-Marker Heartbeats

Activate the deferred P25 behavior:

- `rebuild_queue.heartbeat(progress_marker=...)` already tracks `progress_marker_unchanged_since` in Phase 1 (no-op acted on yet).
- Phase 2 adds: `overseer/watchdog.py::tick()` checks for workers whose `progress_marker` has not changed for N intervals (default 5). These workers are flagged "soft-stuck" and routed to human review via a `completion_queue` row with severity `medium`. The worker is not killed — just flagged — because the work may still be making slow progress.

A new test fixture demonstrates soft-stuck routing on a worker whose heartbeat is fresh but whose progress_marker has stagnated.

## 9. Test Plan

| Test file | Coverage |
|-----------|----------|
| `test_overseer_article_finder_connector.py` | RO-mode connect; missing file handled; schema_version visible |
| `test_overseer_article_finder_reconciler.py` | tick() inserts pending events for new AF rows; matches when hashes agree; flags unresolved when they disagree; idempotent re-run |
| `test_overseer_candidate_pdf_state.py` | each transition allowed; invalid transitions rejected; tombstones prior state where appropriate; dependency_edges row created |
| `test_overseer_abstract_provenance.py` | abstract artefact with valid abstract_source passes; missing/unresolved source fails verifier |
| `test_overseer_progress_marker_heartbeats.py` | unchanged marker for N intervals → soft-stuck completion_queue row; changing marker resets the timer; killed worker still reclaimed by liveness check |
| Extensions to `test_overseer_verifier_data.py` | `_check_cross_db_sync` flags unresolved older than threshold; `_check_abstract_source_provenance` flags bad sources |
| `test_overseer_phase2_round_trip.py` | end-to-end: candidate PDF appears in AF → reconciler picks it up → state machine walks metadata_only → ... → extracted → verifier passes throughout |

Target: 30-50 new tests; all 163 Phase 1 tests must continue to pass.

## 10. Acceptance Criteria

1. The four new artefact kinds appear in `artefact_kinds` (idempotent seed script applied).
2. AF connector opens the live `Article_Finder_v3_2_3/data/article_finder.db` read-only.
3. The reconciler tick on a clean state is a no-op; on a state with new AF-accepted rows, inserts paired KA artefacts and `cross_db_sync_events`.
4. Disagreement between AF and KA on canonical paper_id flips events to `unresolved` and raises a `completion_queue` blocking row.
5. Candidate PDF state machine: every documented transition is allowed; every undocumented one is rejected. Each transition emits a `dependency_edges` row.
6. Abstract-source provenance verifier rejects any `abstract` artefact whose source is not in `vocabulary_registry`.
7. Soft-stuck progress-marker detection emits a `completion_queue` row with severity `medium` and does not kill the worker.
8. Phase 2 round-trip: AF row → reconciler → state machine → extracted artefact → verifier pass.
9. All Phase 1 tests continue to pass (no regressions).
10. `scripts/verify_dependency_overseer_contract.py --strict` exits 0 on the live lifecycle DB.
11. Phase 2 ship report `docs/SPRINT_OVERSEER_PHASE_2_COMPLETION_2026-05-23.md` covers each criterion above.

## 11. Open Implementation Questions for Phase 2

1. **AF DB path resolution**: hardcoded `~/REPOS/Article_Finder_v3_2_3/data/article_finder.db` vs configurable. Recommend: config-file lookup in `overseer/config.py` with a single `AF_DB_PATH_CANDIDATES` list, mirroring the lifecycle DB pattern.
2. **Reconciler tick scheduling**: Phase 2 ships the `tick()` function and a runnable script; long-running daemon-mode wrapping is deferred to Phase 4 alongside the other workers.
3. **Hash agreement criterion for AF↔KA matching**: minimum agreement is on `doi` AND `canonical_paper_id` (or both null). Title match used as a tiebreaker. Detailed rule lives in `article_finder_reconciler.py` and is configurable.
4. **Soft-stuck threshold N**: default N = 5 intervals (≈2.5 minutes if interval is 30 s). Tunable in worker config.
5. **PDF hash discipline**: SHA-256 of the canonical file bytes; AF may use a different hashing convention. Reconciler normalizes if AF's hash format is documented; otherwise raises a `completion_queue` `pdf_hash_format_mismatch` row.
6. **Backfill policy**: not done in Phase 2. New AF state from Phase 2 ship forward gets paired events; historical state is left as-is. A separate `dependency_overseer_phase2_backfill.py` script is planned but not part of the ship criteria.

## 12. Sequence of Work

The recommended order for execution mirrors the Phase 1 ballistic pattern:

1. Land this spec.
2. Register 4 new artefact kinds.
3. Activate cross_db_sync_events (remove from scaffold-list).
4. Implement AF connector + tests.
5. Implement candidate PDF state machine + tests.
6. Implement abstract-source provenance check + tests.
7. Implement reconciler + tests.
8. Implement P25 soft-stuck routing + tests.
9. Add verifier checks (cross_db_sync, abstract_source_provenance).
10. Phase 2 round-trip test.
11. Run full test suite; run live verifier.
12. Phase 2 ship report.

Estimated commits: 6-8 (similar to Phase 1).
