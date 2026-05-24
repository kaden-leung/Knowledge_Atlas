# Dependency Overseer — Post-Panel Pause Plan

**Date:** 2026-05-24
**Driving document:** `docs/DEPENDENCY_OVERSEER_RUTHLESS_PANEL_REVIEW_2026-05-24.md`
**Decision:** DK accepts the panel's enterprise recommendation. Phase 3 is paused; Phases 1+2 stay in service; the next 90 days are operational tuning and infrastructure for the observability, runbook, and traffic-simulation gaps the panel named.

This document records what was decided, what will be built next, what specifically *won't* be built next, and the discrete tasks David can run to create real Article Finder traffic the overseer can observe.

---

## §1 — Phase 3 status

Phase 3 (LLM enrichment governance) is **paused, not killed**. The 544-line spec at `docs/DEPENDENCY_OVERSEER_PHASE_3_SPEC_2026-05-23.md` is preserved as a reference for resumption. No Phase 3 implementation work happens until all of these conditions are met:

1. ≥ 90 days of Phase 1+2 operating against real lifecycle DB traffic.
2. Observability layer (this doc, §3) has shipped and produced at least 30 days of verifier-run history.
3. A 1–2 page operations runbook (this doc, §5) is written and being followed.
4. Model cards exist for any LLM that would be in `model_allowlist.json` (Mitchell's gate).
5. The "is this dep overseer earning its keep?" scope audit (Larson's gate) has been written and answered.
6. The TLA+ or Alloy model of the lease+fencing state machine (Wayne's gate) has been written and model-checked.
7. The supervision protocol for every named worker (Armstrong's gate) is documented.

If after 90 days the overseer has not been earning its keep — measured against the per-table justification in the scope audit — Phase 3 may be killed rather than resumed, and AE's existing anti-cheat contract becomes the sole LLM-governance surface.

---

## §2 — What Phase 1+2 already does that the panel agrees should ship

- 22 active tables in the lifecycle DB, 220 tests, the strict verifier passes 17/17 against the live `160sp/pipeline_lifecycle_full.db`.
- Heartbeat-based leases + fencing tokens (Kleppmann's pattern; Reviewer 1 votes proceed-with-changes).
- Tombstone-not-delete history (Helland's pattern; Reviewer 2 votes proceed).
- AF reconciler smoke-tested against the live AF DB at `/Users/davidusa/REPOS/Article_Finder_v3_2_3/data/article_finder.db` (16,257 AF papers; 3 currently at `processed_partial`).

These ship as-is. The pause is on Phase 3, not Phase 1+2.

---

## §3 — Observability layer (Majors's gate)

The panel's strongest consensus is that the verifier is monitoring, not observability. To close that gap:

### 3.1 New table: `verifier_run_history`

```sql
CREATE TABLE verifier_run_history (
    run_id          TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT NOT NULL,
    overall_passed  INTEGER NOT NULL,            -- 0/1
    db_path         TEXT NOT NULL,
    checks_json     TEXT NOT NULL,               -- full per-check report serialized
    triggered_by    TEXT NOT NULL                -- 'manual' | 'cron:<name>' | 'test'
);
CREATE INDEX idx_verifier_run_history_time ON verifier_run_history(started_at);
CREATE INDEX idx_verifier_run_history_failed ON verifier_run_history(overall_passed, started_at) WHERE overall_passed = 0;
```

Every `verify_strict()` call writes a row. The wrapper script gains a `--no-history` flag for test scenarios; default is to record. The history table is queryable for: "which checks flip frequently?", "when did `_check_cross_db_sync` first start failing?", "what's the failure rate of `_check_kind_registration` over the last week?". This is the time-series Majors named.

### 3.2 New table: `reconciler_event_log`

```sql
CREATE TABLE reconciler_event_log (
    event_id          TEXT PRIMARY KEY,
    tick_run_id       TEXT NOT NULL,             -- groups events from one tick
    occurred_at       TEXT NOT NULL,
    af_paper_id       TEXT NOT NULL,
    af_signature      TEXT NOT NULL,
    af_status         TEXT,
    ka_paper_id       TEXT NOT NULL,
    action            TEXT NOT NULL,             -- 'inserted_pending' | 'upgraded_to_matched' | 'flagged_unresolved' | 'skipped_already_matched' | 'noop'
    sync_event_id     TEXT,                      -- FK to cross_db_sync_events.event_id when applicable
    reason            TEXT
);
CREATE INDEX idx_reconciler_event_log_time ON reconciler_event_log(occurred_at);
CREATE INDEX idx_reconciler_event_log_action ON reconciler_event_log(action, occurred_at);
CREATE INDEX idx_reconciler_event_log_paper ON reconciler_event_log(ka_paper_id);
```

This is the high-cardinality event log Majors demands. Each reconciler tick writes one row per AF paper seen. Cardinality on (action, af_status, ka_paper_id) lets us ask: "how many papers had signature drift in the last hour broken down by af_status?". Without this, the dry-run sensitivity sweep and operator-role responsibilities are flying blind.

### 3.3 Migration + applier

A new `scripts/migrations/2026_05_24_observability_layer.sql` adds both tables to the lifecycle DB. Additive only. `dependency_overseer_init.py` continues to apply it idempotently.

### 3.4 Modifications to existing code

- `overseer/verifier_data.py::verify_strict()` gains an optional `record_to_history: bool = True` parameter; when true and a connection is available, writes the full report to `verifier_run_history`.
- `overseer/article_finder_reconciler.py::tick()` writes one `reconciler_event_log` row per paper seen, even for no-op cases (so we have a denominator).
- New `scripts/dependency_overseer_observability_report.py` produces a daily summary: verifier-run pass/fail counts, reconciler event counts by action, completion_queue depth growth rate, oldest unresolved sync event.

Estimated effort: 1 commit, ~400 lines including tests.

---

## §4 — Article Finder traffic simulation (the user's explicit ask)

The panel was right that the overseer ships before there's much to observe. AF's live DB has been mostly idle since 2026-05-10: 16,196 papers in `candidate`, 40 `pending_scorer`, 18 `rejected`, 3 `processed_partial`. The richer signals tell a different story — 754 papers carry `atlas_intake_decision='accept_candidate'` and 438 carry `ae_corpus_match_status='matched'`. The reconciler's current proxy (`status='processed_partial'`) misses both of these populations.

### 4.1 Refine the "accepted" criterion (OVERSEER-AF-STATUS-CRITERION already in TASKS.md)

Switch the reconciler default from `status='processed_partial'` (3 rows) to `atlas_intake_decision='accept_candidate'` (754 rows). This alone turns the reconciler from "trickling 3 rows" into a substantive load. The richer-criterion implementation is straightforward; the connector already reads arbitrary AF columns.

Once the criterion changes, a single reconciler tick against the live AF DB will produce ~750 sync events in one pass. That's a real first-touch dataset for the observability layer to consume.

### 4.2 Five simulation modes (built incrementally)

**Mode 1 — Snapshot replay.** Copy the live AF DB to a snapshot file. Reconciler runs against the snapshot. Repeatable. Tests verifier convergence on real data. Easiest. *Build first.*

**Mode 2 — Scripted story.** A small Python script writes synthetic AF state changes to a fake AF DB over time: candidates appear, statuses flip, signatures drift, papers retire. The reconciler runs against the fake DB. Tests specific code paths (new pending, signature drift, matched promotion). *Build second.*

**Mode 3 — Synthetic load.** Generate N synthetic AF papers with controllable distributions (X new papers per tick, Y signature drifts per tick, Z status flips per tick). Tests reconciler under stress. *Build third if needed.*

**Mode 4 — Real-AF tick on schedule.** Run the reconciler against the live AF DB on a cron schedule (every 60 s recommended). Whatever AF does is what gets synced. This is the production mode, not a test mode. *Wire up after Mode 1.*

**Mode 5 — User-triggered AF activity.** David runs AF commands that create new state changes; reconciler picks them up on the next tick. *Always available; relies on §4.4 below.*

### 4.3 Snapshot replay first — concrete implementation

A new `scripts/dependency_overseer_af_snapshot.py`:

- `--snapshot` mode: copies `/Users/davidusa/REPOS/Article_Finder_v3_2_3/data/article_finder.db` to `backups/af_snapshots/article_finder.db.snapshot-<YYYYMMDDTHHMMSSZ>` (read-only copy).
- `--list-snapshots`: lists available snapshots with row counts and status distributions.
- `--replay SNAPSHOT_FILE`: runs the reconciler against the named snapshot with the new accepted criterion. Records every event to `reconciler_event_log`.

This gives reproducible test conditions: the same snapshot produces the same reconciler events regardless of when it's replayed. Snapshots can be archived, versioned, and used as fixtures.

### 4.4 Story-mode simulator — concrete implementation

A new `scripts/dependency_overseer_af_story_simulator.py` that writes a fake AF DB through a scripted sequence of events. Sample story:

```
t=0:   create 10 candidates
t=1m:  3 candidates → pending_scorer
t=2m:  2 of those → atlas_intake_decision='accept_candidate'
t=3m:  reconciler tick — should insert 2 pending sync events
t=4m:  1 of those → ae_corpus_match_status='matched'
t=5m:  reconciler tick — should upgrade 1 to matched
t=6m:  edit one paper's title — signature drift
t=7m:  reconciler tick — should flip to unresolved + raise blocking completion_queue
t=8m:  add 5 new candidates
t=9m:  reconciler tick — 5 noops (still candidate, not yet accepted)
t=10m: 3 of the new ones → accept_candidate
t=11m: reconciler tick — 3 new pending events
...
```

The script runs the story in real time or accelerated. Each step produces a known expected reconciler outcome, asserted in tests. This is the systematic exercise of the reconciler under known conditions, which the panel said was missing.

### 4.5 Estimated effort

Mode 1 (snapshot replay): 1 commit, ~150 lines + tests.
Mode 2 (story simulator): 1 commit, ~300 lines + tests.
Mode 3 (synthetic load): deferred until Modes 1+2 reveal whether it's needed.
Mode 4 (cron schedule): a one-line cron entry; documented in the runbook (§5).
Mode 5 (user-triggered): no code, just §4.6 below.

---

## §4.6 — Tasks David can run to create real AF activity

Each of these would put new state into AF.papers that the reconciler would pick up on the next tick. Ranked by cost (low → high) and value (high → low):

### Task A — Low cost, high value: flip 5–10 papers to `atlas_intake_decision='accept_candidate'`

The simplest forcing function. David can do this via the AF CLI or by directly editing a few rows in `Article_Finder_v3_2_3/data/article_finder.db`. The reconciler picks them up on the next tick after we ship §4.1 (the criterion change). Recommended starting point: 10 papers, mix of papers that already have `canonical_paper_id` set (will resolve to existing KA paper_ids) and papers without (will fall back to `AF:<af_paper_id>`).

### Task B — Low cost, medium value: re-run AF's corpus matcher

`Article_Finder_v3_2_3/cli/main.py` has a `match-corpus` subcommand. Re-running it on the current AF corpus would update `ae_corpus_match_status` and `ae_corpus_match_paper_id` values. The reconciler would see these as new accepted entries (via the criterion change in §4.1). Existing 438 matched papers + however many new ones the matcher produces.

### Task C — Medium cost, high value: run AF's discovery_orchestrator on one fresh topic

Pick a topic the existing corpus doesn't cover well (e.g., "thermal comfort in airport terminals" — adjacent to CNFA but not currently a covered surface). Run `search` and `import` subcommands. This fetches new candidates from OpenAlex / Crossref / Semantic Scholar; some will be auto-flagged `accept_candidate`. The reconciler sees the new candidates on its next tick. Cost is paid-OpenAlex-rate-limit and ~30 minutes of compute; value is a real new candidate stream the overseer hasn't seen before.

### Task D — Medium cost, medium value: trigger AF's PDF watcher on a small folder

Drop 3–5 PDFs into AF's inbox folder (path documented in AF's README; typical location is `Article_Finder_v3_2_3/data/pdf_inbox/`). AF's pdf_watcher.py processes them: extracts DOI, looks up metadata, scores, triages. Several rows in AF.papers change status. The reconciler picks up any that hit `accept_candidate`.

### Task E — High cost, high value: run AF's full discovery on a research question

Pick a real CNFA research question David is working on. Run AF's discovery_orchestrator end-to-end (gap_analyzer → bibliographer → citation_network → bounded_expander → triage). This produces a real cohort of accepted candidates. The overseer's reconciler then has a non-trivial workload to converge on. This is the most valuable test condition; also the most expensive to operate.

### Task F — Negative-test value: deliberately drift a paper's title in AF

After the reconciler has accepted a paper, manually edit that paper's title in AF.papers. The next tick should detect signature drift, flip the sync event to `unresolved`, and raise a `severity='blocking'` `completion_queue` row. This exercises the unhappy path that Phase 2's tests cover synthetically. Doing it once on real data confirms the synthetic test reflects reality.

David: I'd suggest starting with **Task A** (lowest cost, exercises the new criterion change immediately) and **Task F** (proves the drift-detection path on real data). Tasks B–E are higher-value but require AF-side work that may compete with your other priorities. **Tell me which of A–F you want me to ground the next round of observability + simulator work against.**

---

## §5 — Operations runbook (Fournier's gate)

A new `docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md` covers:

- How to run the reconciler tick (manual + cron pattern).
- How to read the daily observability report (after §3.4 ships).
- How to triage `completion_queue` items: by severity, by reason, by age.
- How to act on a `cross_db_sync_events` unresolved row.
- How to back up the lifecycle DB before any non-trivial operation.
- On-call rotation: who is the operator this week, what's the escalation path.
- What to do if the watchdog hasn't run in N hours.
- What to do if the verifier starts failing checks that previously passed.
- How to roll back the most recent migration if needed.

The runbook is a one-page operational manual, not an architectural document. It says what to *do*, not what's *true*.

Estimated effort: 1 commit, ~200 lines (markdown).

---

## §6 — Plan execution order

Recommended order, in this session or future sessions:

1. **Commit this pause plan** (1 commit).
2. **Update TASKS.md and TOPIC_PROGRESS.md** (1 commit, paired with the pause plan).
3. **Switch the reconciler's accepted criterion** from `status='processed_partial'` to `atlas_intake_decision='accept_candidate'` (1 commit, ~50 lines code change + test fixture update).
4. **Land the observability layer** (§3): `verifier_run_history` + `reconciler_event_log` tables + migration + recording at the verifier and reconciler call sites + a daily report script (1 commit, ~400 lines).
5. **Land the snapshot replay simulator** (§4.3) (1 commit, ~150 lines).
6. **Write the operations runbook** (§5) (1 commit, ~200 lines).
7. **Optionally land the story-mode simulator** (§4.4) if David picks Task A/F and wants synthetic validation alongside real data (1 commit, ~300 lines).
8. **Pause for 30 days of operation**, accumulate verifier-run-history and reconciler-event-log data, then revisit Phase 3 against the panel's gates.

Estimated commits: 6–7 in the immediate cycle; then a 30-day operational pause; then revisit.

---

## §7 — Conditions for resuming Phase 3 (from the panel)

For completeness, these are the panel's gates re-stated from §1:

| Gate | Owner | Concrete artifact required |
|------|-------|----------------------------|
| 90 days operational data | All | verifier_run_history with ≥30 days; reconciler_event_log with ≥30 days |
| Observability layer shipped | Majors | §3 above |
| Operations runbook | Fournier | §5 above |
| Model cards | Mitchell | One markdown card per allowed model |
| Scope audit | Larson | One-page "earning its keep" memo per table |
| Formal model | Wayne | TLA+ or Alloy module of lease+fencing+claim state machine |
| Supervision protocol | Armstrong | Per-worker supervisor + restart strategy table |
| Watermark + windowing | Akidau | Schema additions for event-time semantics |
| Saga compensation | McCaffrey | Compensation logic per event_kind |
| SIGKILL-mid-txn test | Kleppmann | A single test that proves zero partial state on abrupt exit |
| Column rename + version_id | Helland | Migration that adds version_id to artefact_registry |

When all 11 land, Phase 3 unpauses. Not before.

---

## §8 — What this pause is NOT

- Not a rollback. Phase 1+2 stay in service.
- Not a deletion. The Phase 3 spec stays in `docs/`.
- Not a 90-day waiting room. Active work continues — observability, simulator, runbook, criterion change, scope audit, formal model. These ARE the next 90 days of dep-overseer work.
- Not a vote of no-confidence. Phase 1+2 are real and useful. The panel's critique is that Phase 3's value is speculative *given the current operating state*; the right response is to make the operating state non-speculative.

The pause is honest infrastructure discipline. The single sentence that captures it: **build the operational reality first, then govern it; do not govern a reality you have not yet operated.**
