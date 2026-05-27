# Shared Production DB — Write-Coordination Rule

**Date:** 2026-05-26
**Status:** governing rule (pre-Stage-2 precondition)
**Applies to:** all workers — CW (Claude Code), AG (Agentic Gemini), Codex-term,
Codex-desk, and any automated builder / cron / repair loop.
**Canonical DB in scope:** `160sp/pipeline_lifecycle_full.db` (the lifecycle /
production DB), and any single canonical Stage-2 DB that succeeds it.

---

## 0. Why this rule exists

On 2026-05-24→26 the `artefact_registry` row count in
`160sp/pipeline_lifecycle_full.db` drifted **3 → 13 between sessions with no AEPL
build run responsible**. An uncoordinated worker wrote the shared production DB.

The existing concurrency control does not catch this:

- **Fencing token (P24)** — `overseer/artefact_registry.update_with_hashes()`
  rejects a write whose `fencing_token` is below the row's
  `current_fencing_token`. This guards **updates to an already-registered
  artefact**. It does **not** guard (a) `register()` of *new* artefacts,
  (b) whether a builder should be running against production at all, or
  (c) *which worker* ran it.
- **`build_runs`** records `builder_name` + `builder_version` but **no
  `worker_id` / `session_id`** — so a drifted row cannot even be attributed to a
  worker after the fact.
- **WAL mode** prevents corruption under concurrent writers; it does **not**
  prevent two workers from each running a semantic rebuild against production.

So the registry can grow silently and unattributably. This rule closes that hole.

---

## 1. Design decision this rule rests on

**Stage 2 converges on the overseer's normalized model as the single canonical
write path** (DK, 2026-05-26). One writer module, one production DB. Therefore the
fix is a **write-lease + attribution + drift audit**, *not* a DB split.
(`AEPL-RULE-RECONCILE` folds the layer's denormalized builder into the overseer's
rule module; the layer builder becomes a read/projection/export consumer that
emits the page payload, never a second writer of production content.)

---

## 2. The five rules

### Rule 1 — One canonical writer module
Only the overseer normalized write path may write epistemic content to the
canonical DB. The denormalized article-epistemic-layer builder is demoted to a
**projection/export consumer** (it reads the canonical tables and emits the page
payload `data/ka_payloads/article_epistemic_layer.json`). It must not `INSERT`,
`UPDATE`, or `register()` production content. (Tracks `AEPL-RULE-RECONCILE`.)

### Rule 2 — No production write without a held write-lease
Before any process opens the canonical DB **for writing** — builder, repair loop,
schema migration, *or a manual one-off fix* — it must acquire an exclusive
**DB write-lease**. A process that does not hold a current lease must open the DB
**read-only** (`PRAGMA query_only = ON`) or refuse to proceed.

The lease lives in a new table in the same DB:

```sql
CREATE TABLE db_write_lease (
    lease_id          TEXT PRIMARY KEY,
    db_path           TEXT NOT NULL,         -- canonical DB this lease covers
    worker_id         TEXT NOT NULL,         -- cw | ag | codex-term | codex-desk | cron:<name>
    session_id        TEXT NOT NULL,         -- worker's session/run id
    builder_name      TEXT NOT NULL,         -- e.g. overseer_normalized_builder
    purpose           TEXT NOT NULL,         -- short human reason
    acquired_at       TEXT NOT NULL,
    heartbeat_at      TEXT NOT NULL,
    expires_at        TEXT NOT NULL,         -- heartbeat-extended TTL
    released_at       TEXT,                  -- NULL while held
    lease_token       INTEGER NOT NULL       -- bumped on every (re)acquisition
);
-- At most one *active* lease per db_path:
CREATE UNIQUE INDEX ux_db_write_lease_active
    ON db_write_lease(db_path) WHERE released_at IS NULL;
```

Discipline (mirrors the fencing-token + watchdog model already in `overseer/`):

- **Acquire** inside `BEGIN IMMEDIATE`; the partial-unique index makes a second
  concurrent active lease fail atomically. Acquisition bumps `lease_token`.
- **TTL + heartbeat.** Lease TTL = 10 min; holder heartbeats every ≤3 min
  (extends `expires_at`). A crashed holder's lease expires and is reclaimable —
  this matches the coord server's 2-min stale-worker rule and the watchdog's
  reclaim path.
- **Reclaim** of an expired lease bumps `lease_token`; the prior holder's writes
  are rejected on token mismatch (same shape as P24). This is the
  belt-and-suspenders layer beneath the per-artefact token.

### Rule 3 — Every production write is attributed to a worker
`build_runs` (and `article_epistemic_build_runs`) gain **additive** columns
`worker_id`, `session_id`, `lease_id`. Every `register()` / `update_with_hashes()`
/ row insert happens inside a build run that carries the holding worker and lease.
An `artefact_registry` row with `latest_build_run_id IS NULL`, or whose build run
has no `worker_id`/`lease_id`, is by definition a **coordination violation**.

### Rule 4 — The lease composes with the existing coordination server
The HTTP coord server (`http://localhost:8420`, `scripts/coordination/coord.py`)
coordinates **tasks**; the DB write-lease coordinates **data**. To write
production a worker must hold **both**: the claimed task *and* the DB write-lease.
The active lease is mirrored to a JSON fallback
(`scripts/coordination/db_write_lease.json`) so a worker with the server down can
still see who holds the DB before writing (per the root CLAUDE.md "never use
SQLite alone for cross-AI coordination" rule).

### Rule 5 — Drift audit at session start and before promotion
`scripts/audit_production_db_writers.py` reconciles `artefact_registry` against
`build_runs` + `db_write_lease` and reports:

1. **orphan rows** — `latest_build_run_id IS NULL`;
2. rows whose build run has **no `worker_id`/`lease_id`**;
3. rows written by an **unsanctioned `builder_name`**;
4. rows whose write timestamp falls **outside any lease window**;
5. **registry count delta** since the last sealed (`status='verified'`) build run.

The audit runs (a) at every session start, per the coordination protocol, and
(b) as a **§13 release-gate precondition** for the epistemic layer. A failed
audit **blocks Stage-2 promotion**.

---

## 3. Enforcement vs. adoption (the part that actually decides whether this works)

- **Enforcement (code):** add the `db_write_lease` table + the additive
  `build_runs` columns; add `overseer/db_write_lease.py` (acquire / heartbeat /
  release / reclaim / require) and a write-mode `connect(..., write=True)` in
  `overseer/db.py` that refuses to drop `PRAGMA query_only` without a live lease
  handle; add `scripts/audit_production_db_writers.py`.
- **Adoption (social — the hard part):** the lease only works if **every** writer
  routes through it. CW, AG, and Codex builders must each switch their production
  writes to the leased write-connection. Until all three adopt it, the audit
  (Rule 5) is the safety net that *names* the violator instead of silently
  drifting.

Because Codex/AG are themselves among the uncoordinated writers, the
implementation should be built and adopted with their buy-in — see the handoff
prompt in `docs/CODEX_PROMPT_DB_WRITE_LEASE_2026-05-26.md`.

---

## 4. Migration safety note (do not ironically violate the rule)

Adding `db_write_lease` and the `build_runs` columns to
`160sp/pipeline_lifecycle_full.db` is itself a production write. It must be done
**once, by a single worker, after announcing on the coord server**, and ideally as
the *first* operation to acquire a lease (bootstrap: create the table, then
immediately take lease #1 for the migration). Do not apply this schema change from
two sessions at once.
