# Dependency Overseer — Operations Runbook

**Date:** 2026-05-24
**Audience:** the Phase 3 operator (per Fournier's gate, panel review §10).
**Source authorities:**
- `docs/DEPENDENCY_OVERSEER_POST_PANEL_PAUSE_PLAN_2026-05-24.md` §5
- `docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md`
- `docs/DEPENDENCY_OVERSEER_RUTHLESS_PANEL_REVIEW_2026-05-24.md` §10 (Fournier)

This runbook says **what to do**, not what is true. It is anchored on what `ka_overseer_dashboard.py` shows, so the operator can read a widget and know the corresponding action.

If a procedure here conflicts with a panel review, design doc, or implementation spec, the design doc wins. Update the runbook.

---

## §1 — Quick reference

| Symptom on the dashboard | Page | First action |
|---|---|---|
| Page 1 reconciler-bridge gap > 100 | 1 | Run a reconciler tick (§3) |
| Page 2 verifier health "Failed" > 0 | 2 | Read the failed-run JSON (§5) |
| Page 2 BLOCKING completion-queue items > 0 | 2 | Triage the items (§7) |
| Page 2 signature-drift events > 0 | 2 | Reconcile manually (§8) |
| Page 1 AF row count flat for > 24h with no expected work | 1 | AF may be idle; consider Tasks A–F (§9) |
| Stale active artefacts > 0 on Page 2 | 2 | Inspect; rebuild if appropriate (§6) |
| Quarantined queue items > 0 on Page 2 | 2 | Read last_error, decide retry vs accept (§7) |

---

## §2 — Daily routine (5 minutes)

1. Launch the dashboard: `streamlit run ka_overseer_dashboard.py`.
2. Click **Refresh** on Page 1. Note Stage 4 (Atlas intake decided) total and the reconciler-bridge "Gap (unreconciled)" metric. Both should be steady or increasing by a small amount.
3. Switch to Page 2. Confirm "Last run: … PASS". Confirm "Reconciler ticks recorded" advanced since yesterday. Confirm "BLOCKING" completion-queue strip is zero or steady.
4. If anything is anomalous, jump to the symptom row above.

Aim for the daily routine to be 5 minutes when healthy. If it routinely takes longer, something needs attention — escalate (§10).

---

## §3 — Running a reconciler tick

The reconciler is the thing that brings KA-side state in sync with AF-side state. It runs as a one-shot Python script.

```bash
python3 scripts/dependency_overseer_reconciler_tick.py \
    --db 160sp/pipeline_lifecycle_full.db \
    --accepted-intake-decision accept_candidate \
    --limit 100
```

- `--db` is the KA lifecycle DB path. The default candidate list resolves to `160sp/pipeline_lifecycle_full.db` when present.
- `--accepted-intake-decision` defaults to `accept_candidate` (the post-2026-05-24 production criterion).
- `--limit` caps rows scanned per tick. Use `--limit 100` for warm-up smoke tests; omit for full sweeps.

Output is a JSON report: `af_papers_seen`, `inserted_pending`, `upgraded_to_matched`, `flagged_unresolved`, `skipped_already_matched`. After the run, Pages 1 and 2 will reflect the new state on Refresh.

**When to run a tick manually:** when the dashboard shows a large reconciler-bridge gap, when you've just performed Task A (manually accepting AF papers — see §9), when you want to confirm AF is reachable.

**Scheduled tick (cron):** not enabled by default. To enable, add to crontab:

```cron
*/5 * * * * cd /Users/davidusa/REPOS/Knowledge_Atlas && /usr/bin/python3 scripts/dependency_overseer_reconciler_tick.py --db 160sp/pipeline_lifecycle_full.db --accepted-intake-decision accept_candidate >> /tmp/overseer_reconciler.log 2>&1
```

The cron entry runs the tick every 5 minutes. Inspect `/tmp/overseer_reconciler.log` for errors. **Do not enable cron until you've confirmed manual ticks work for at least one cycle.**

---

## §4 — Backing up the lifecycle DB

Before any non-trivial DB operation — schema migration, manual UPDATE, large reconciler sweep — take a durable backup.

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
cp 160sp/pipeline_lifecycle_full.db \
   "backups/dependency_overseer/pipeline_lifecycle_full.db.bak-${TS}-before_OPERATION"
```

Replace `OPERATION` with a short verb that describes the work: `before_observability_layer`, `before_manual_sql_fix`, `before_phase3_resume`.

Backups in `backups/dependency_overseer/` are gitignored (~10 MB each). Keep at least the most recent 5. Older backups can be moved offline if disk pressure is real.

---

## §5 — Reading a failed verifier run

When Page 2 shows a failed run, click the "Recent N runs" expander and find the failure. Then query the DB for the full failure JSON:

```bash
sqlite3 160sp/pipeline_lifecycle_full.db \
  "SELECT run_id, started_at, checks_json FROM verifier_run_history \
   WHERE overall_passed = 0 ORDER BY started_at DESC LIMIT 1" \
  | python3 -c "import sys, json; d = sys.stdin.read().split('|',2); print(json.dumps(json.loads(d[2]), indent=2))"
```

Each check entry has `name`, `passed`, `description`, and `failures` (a list of dicts with the specific failing rows). Use `failures` to locate the offending data.

**Common patterns:**

- `kind_registration` failure → an artefact with `kind=` that's not in `artefact_kinds`. Either register the kind or tombstone the rogue artefact.
- `referential_integrity` failure → a `dependency_edges` row whose endpoint doesn't resolve. Tombstone the orphan edge.
- `hash_presence_on_fresh_artefacts` → an active+fresh artefact missing `raw_hash` or `semantic_hash`. Re-run the builder for that artefact, or tombstone it.
- `closed_enum_membership` → drift between the DB's stored enum value and `schemas/status_vocabularies.json`. Migrate the vocabulary file before changing the DB.

---

## §6 — Stale artefacts

A stale artefact is one whose `freshness_status='stale'` and `active=1` — it's published but known to be out of sync with its support set.

Find them:

```bash
sqlite3 160sp/pipeline_lifecycle_full.db \
  "SELECT artefact_id, kind, entity_id FROM artefact_registry \
   WHERE freshness_status='stale' AND active=1 ORDER BY kind, entity_id"
```

Two options per stale artefact:

1. **Enqueue a rebuild** (the normal path):
   ```bash
   sqlite3 160sp/pipeline_lifecycle_full.db \
     "INSERT INTO rebuild_queue (queue_id, artefact_id, reason, severity, first_seen_at, last_seen_at, attempt_count, state, fencing_token) \
      VALUES ('q:manual-' || hex(randomblob(8)), '<artefact_id>', 'manual_rebuild_request', 'medium', datetime('now'), datetime('now'), 0, 'queued', 0)"
   ```
   Then run a builder pass.

2. **Tombstone if no longer needed**:
   ```bash
   sqlite3 160sp/pipeline_lifecycle_full.db \
     "UPDATE artefact_registry SET active=0, tombstoned_at=datetime('now') WHERE artefact_id='<artefact_id>'"
   ```

Always take a backup (§4) before either of these.

---

## §7 — Triaging the completion queue

Page 2 surfaces the completion queue with severity-grouped counts. The triage rules:

| Severity | First action |
|---|---|
| `blocking` | Read in full immediately. Block any release decisions until cleared. |
| `high` | Read within the workday. Decide repair vs. waiver. |
| `medium` | Read by end of week. Often safe to batch-resolve. |
| `low` | Read when convenient. Often informational. |

To list open BLOCKING items:

```bash
sqlite3 160sp/pipeline_lifecycle_full.db \
  "SELECT queue_id, reason, paper_id, artefact_id, first_seen_at FROM completion_queue \
   WHERE status IN ('open','in_review') AND severity='blocking' ORDER BY first_seen_at"
```

Decision tree per item:

1. **Reason is `af_signature_drift_unresolved`**: see §8.
2. **Reason is `rebuild_queue_quarantine_after_watchdog_reclaim`**: a worker timed out repeatedly. Inspect the queue row's `last_error`. If a real bug, fix the builder. If transient, manually re-enqueue from quarantine.
3. **Reason is `cascade_threshold_exceeded`**: a large cascade was paused. Read the source artefact; decide whether to allow it (batch rebuild) or defer (file as Phase-4 work).
4. **Reason is something else**: read `reason` and `next_action`; if next_action says human_review, do the review and either `resolve` or `waive`.

Resolve a queue item:

```bash
sqlite3 160sp/pipeline_lifecycle_full.db \
  "UPDATE completion_queue SET status='resolved', resolved_at=datetime('now'), assigned_to='<your_id>' WHERE queue_id='<queue_id>'"
```

Waive (instead of resolve) when no fix is needed but the item shouldn't fire again under the same conditions.

---

## §8 — Acting on a signature drift event

A drift event means: an AF paper that the overseer previously synced has had its signature change. Cause is usually that the AF row was edited (title corrected, DOI updated) or that AF's signature derivation changed.

On Page 2, the "Signature drift events (unresolved)" section lists them with age in minutes. To inspect:

```bash
sqlite3 160sp/pipeline_lifecycle_full.db \
  "SELECT event_id, lifecycle_payload_hash, article_finder_payload_hash, created_at \
   FROM cross_db_sync_events WHERE status='unresolved' ORDER BY created_at"
```

For each unresolved row:

1. Find the AF-side paper: `lifecycle_payload_hash` is `paper:<ka_paper_id>`; look up the corresponding AF row by `canonical_paper_id` (often equals the KA paper_id).
2. Confirm whether the drift is intentional (e.g., AF deliberately corrected metadata) or accidental.
3. If intentional: accept the new AF signature by updating the sync event:
   ```bash
   sqlite3 160sp/pipeline_lifecycle_full.db \
     "UPDATE cross_db_sync_events SET status='matched', resolved_at=datetime('now') \
      WHERE event_id='<event_id>'"
   ```
   Then resolve the paired BLOCKING completion_queue item (§7).
4. If accidental: roll back the AF change, then re-run a reconciler tick (§3). The next tick will see matching signatures and clear the unresolved status automatically.

---

## §9 — Triggering AF activity (the to-do list of tasks A–F)

When the dashboard is too quiet, real AF activity is the cure. The six tasks from the pause plan §4.6, ranked low-cost first:

- **Task A** — flip 5–10 AF papers to `atlas_intake_decision='accept_candidate'` (lowest cost; highest immediate test value).
- **Task F** — drift a title in AF.papers on an already-synced paper (lowest cost; proves the unhappy path).
- **Task B** — re-run AF's `match-corpus` subcommand.
- **Task D** — drop PDFs into AF's inbox folder (`Article_Finder_v3_2_3/data/pdf_inbox/`).
- **Task C** — run AF's discovery_orchestrator on a fresh topic.
- **Task E** — run AF's full discovery on a research question (highest cost; highest fidelity test).

After running any of these, run a reconciler tick (§3) and reload Pages 1 and 2.

---

## §10 — Escalation

If a daily routine consistently exceeds 15 minutes, or the BLOCKING completion-queue count is growing rather than steady-or-shrinking, escalate:

1. Read all open BLOCKING items (§7).
2. Write a one-page incident note: what's happening, what you've tried, what you think is wrong, what you need.
3. Take a backup (§4) before any further changes.
4. Hand off to DK or the original implementer (CW) with the incident note + the affected `queue_id` / `artefact_id` / `paper_id` references.

The escalation path is informal in 2026-05-24. Phase 4 may formalize an on-call rotation; until then, escalation = a note in TASKS.md plus a Slack-equivalent ping.

---

## §11 — Rolling back the most recent migration

If a migration introduced a problem (rare; all migrations are additive in the current overseer), the rollback steps:

1. Take a backup (§4) of the current state.
2. Identify the migration: `git log --oneline scripts/migrations/`.
3. Restore the lifecycle DB from a backup taken **before** the migration applied. The backups in `backups/dependency_overseer/` are named with their before-OPERATION tag, e.g., `pipeline_lifecycle_full.db.bak-20260525T005558Z-before_observability_layer`.
4. Re-run tests to confirm the rollback is clean: `python3 -m pytest tests/test_overseer_*.py`.
5. Document the rollback in `TASKS.md` with the reason.

Note: rolling back the DB does NOT roll back the code. Either revert the relevant git commits or accept that the code references tables that no longer exist (which will fail loudly at next strict verify; this is the safe behaviour).

---

## §12 — Things the runbook does NOT cover (yet)

- Phase 3 LLM enrichment governance: deferred per the pause plan. When Phase 3 resumes, the runbook gains a section on grounding review, batched equivalence approval, and the auto-approve list.
- Topics / DYK cards / search index / reports: Phase 4 work.
- A real on-call rotation: §10 is informal until Phase 4.
- A formal incident-response workflow: again, Phase 4.
- The render-side verifier (`verifier_render.py`): the headless library choice (OVERSEER-RENDER-VERIFIER) is still open.

When any of these land, this runbook should grow a corresponding section.

---

## §13 — Last-mile note

This runbook tells you what to do. It does not tell you when you don't need to do anything. The default action for a healthy dashboard is to close the browser and go do other work. The system is supposed to take care of itself most of the time. If you find yourself checking the dashboard more than once a day during healthy operation, that's a feature request, not a normal use of time.
