# Codex Handoff — Implement the Shared-DB Write-Lease (enforcement of the coordination rule)

**Date:** 2026-05-26
**Governing rule:** `docs/SHARED_DB_WRITE_COORDINATION_RULE_2026-05-26.md` (read it first; this prompt implements it)
**Repo:** `Knowledge_Atlas`
**Canonical DB:** `160sp/pipeline_lifecycle_full.db`

---

## Copy-paste prompt for Codex

> You are implementing the enforcement layer for the shared-DB write-coordination
> rule in `docs/SHARED_DB_WRITE_COORDINATION_RULE_2026-05-26.md`. Read that doc and
> `overseer/db.py`, `overseer/artefact_registry.py`, `overseer/build_runs.py`
> first — match their existing style (autocommit + explicit `BEGIN IMMEDIATE` via
> `transaction()`, WAL, fencing-token discipline P24, stable IDs from
> `overseer/ids.py`). Do NOT invent a parallel concurrency model; this lease sits
> *beneath* the per-artefact fencing token, not instead of it.
>
> **macOS env:** `python3`/`pip3`, `pip3 install --break-system-packages`. Mac
> paths (`/Users/davidusa/REPOS/...`).
>
> **Coordinate first:** this is itself a production write. Before touching
> `160sp/pipeline_lifecycle_full.db`, `coord.py checkin codex-term`, claim the task,
> announce on the coord server, and apply the migration exactly once.
>
> Deliverables:
>
> 1. **`overseer/db_write_lease.py`** — `acquire(conn, *, worker_id, session_id,
>    builder_name, purpose, ttl_seconds=600)`, `heartbeat(conn, lease_id)`,
>    `release(conn, lease_id)`, `reclaim_expired(conn, db_path)`, `is_held(conn,
>    db_path)`, `require(conn, db_path) -> lease_row | raise LeaseNotHeld`.
>    `acquire` runs inside `BEGIN IMMEDIATE`; the partial-unique index
>    `ux_db_write_lease_active` makes a second active lease fail atomically.
>    Every (re)acquisition bumps `lease_token`; a reclaimed lease bumps it so the
>    prior holder's subsequent writes are rejectable (mirror P24's
>    `FencingTokenMismatch` shape — raise `LeaseTokenMismatch`).
>
> 2. **Migration** `scripts/migrate_add_db_write_lease.py` — additive only:
>    create `db_write_lease` (+ partial-unique index) per the rule doc §2; add
>    columns `worker_id`, `session_id`, `lease_id` to `build_runs` and
>    `article_epistemic_build_runs` (`ALTER TABLE ... ADD COLUMN`, nullable). Must
>    be idempotent (`IF NOT EXISTS` / column-existence check). Bootstrap: create
>    the lease table, then immediately take lease #1 for the migration itself.
>
> 3. **Write-mode connect** — extend `overseer/db.py` `connect(db_path, *,
>    write=False)`. When `write=False` (default) set `PRAGMA query_only = ON`.
>    `write=True` requires a live lease handle (or raises `LeaseNotHeld`); only
>    then is `query_only` left OFF. Existing read callers keep working unchanged.
>
> 4. **`scripts/audit_production_db_writers.py`** — the Rule 5 drift auditor.
>    Reports, with one-line SQL trace per number: (1) orphan registry rows
>    (`latest_build_run_id IS NULL`); (2) rows whose build run lacks
>    `worker_id`/`lease_id`; (3) rows by an unsanctioned `builder_name`;
>    (4) rows written outside any lease window; (5) registry count delta since the
>    last `status='verified'` build run. Exit non-zero on any violation so it can
>    gate promotion (§13). Add `--strict` and `--json-out`.
>
> 5. **Adopt it in the writers** — route the overseer normalized builder's
>    production writes through `connect(..., write=True)` under a held lease +
>    build run carrying `worker_id`/`session_id`/`lease_id`. Leave a `# LEASE:`
>    adoption marker at each production-write entry point so AG/CW can follow.
>
> 6. **JSON mirror** — on acquire/heartbeat/release, also write the active lease to
>    `scripts/coordination/db_write_lease.json` (server-down fallback; root
>    CLAUDE.md "never SQLite-only for cross-AI coordination").
>
> 7. **Tests** (`tests/test_db_write_lease.py`): second concurrent acquire fails;
>    expired lease is reclaimable and bumps the token; stale-token write rejected;
>    `write=True` without a lease raises; read connection is `query_only`; auditor
>    flags a deliberately-orphaned row and exits non-zero. Run the suite and the
>    auditor against a **copy** of `160sp/pipeline_lifecycle_full.db` (never the
>    live file) and paste the output. Per the repo verification discipline: ship
>    nothing untested; every count gets a one-line trace.
>
> Then `coord.py msg codex-term "HANDOFF" "lease enforcement landed; CW+AG must
> adopt connect(write=True) in their production-write paths"` and update `TASKS.md`.

---

## Notes for DK

- The **rule** (governance) is written by CW: `docs/SHARED_DB_WRITE_COORDINATION_RULE_2026-05-26.md`.
- This prompt covers the **enforcement code + Codex's own adoption**. CW and AG
  still each have to route their production writes through the leased connection —
  the lease is only as good as universal adoption; the auditor (Rule 5) is the net
  that *names the violator* until adoption is complete.
- CW can implement items 1–4 itself instead of handing to Codex if you'd rather —
  the only reason to give it to Codex is that Codex is one of the uncoordinated
  writers and needs to adopt the API anyway.
