# Dependency Overseer — State of the Build

**Date:** 2026-05-25
**Audience:** DK (single source of truth on where we are)
**Purpose:** answer five questions in one document — what was the plan, what's done, what's waiting, what's left, what will we have at the end, can it really manage all the pipelines.

---

## §1 — The Original Plan

The handoff document `docs/HANDOFF_DEPENDENCY_OVERSEER_2026-05-23.md` set the scope: a **global dependency creation, maintenance, and monitoring layer** for the Knowledge Atlas. The driving requirement was that the lifecycle DB should know the values of everything important enough that dependency state is calculable.

The expert panel brief `docs/DEPENDENCY_OVERSEER_EXPERT_PANEL_BRIEF_2026-05-23.md` enumerated ten architectural components:

1. A lifecycle DB that is the source of record.
2. A global artefact registry.
3. A dependency graph between artefacts.
4. Content hashes and support sets for every derived value.
5. Rebuild queues for stale or missing derived artefacts.
6. Verification runs recorded in the DB.
7. Repair/completion loops.
8. Release gates that block stale promotion.
9. Provenance on every component, including explicit LLM provenance.
10. Formal linkage between Article Finder's local DB and the master lifecycle DB.

The synthesis derived from a simulated six-reviewer panel review confirmed the direction and produced a phased plan:

- **Phase 1**: minimum viable overseer over PNU and article-epistemic records — schema, registry, queues, builder, verifier, repair loop.
- **Phase 2**: Article Finder peer-DB sync + abstract handling + candidate PDF state machine.
- **Phase 3**: LLM enrichment governance (grounding, review queues, content equivalence, vocabulary canonicalization).
- **Phase 4**: extend to topics, DYK cards, search index, reports, release dashboards; add backpressure and concurrency.

That was the plan. The phases were each gated on the prior phase shipping, with explicit invariants (B1–B12 carried from the brief, P1–P28 added by the synthesis) and explicit rejected suggestions (R1–R10).

---

## §2 — What's Shipped

Twenty-three commits between 2026-05-23 and 2026-05-25, organized in three layers.

### 2.1 Phase 1 (shipped 2026-05-23)

`docs/SPRINT_OVERSEER_PHASE_1_COMPLETION_2026-05-23.md` is the full ship report. Highlights:

- **22 active lifecycle DB tables** in `contracts/schemas/dependency_overseer/dependency_overseer.sql`. Migration applied to `160sp/pipeline_lifecycle_full.db`; durable backup taken first.
- **5 JSON contract files** for status vocabularies, component types, absence reasons, artefact kinds, and the PsychoPy + CNFA seed for the vocabulary registry (70 canonical entries).
- **14 Python modules** under `overseer/`: db, ids, normalization, content_hashes, artefact_registry, dependency_edges, support_sets, vocabulary_registry, rebuild_queue, watchdog, completion_queue, build_runs, article_epistemic_builder, verifier_data, repair_loop, last_mile_checks, invalidator.
- **The article-epistemic Stage 1 builder** is deterministic; primary-claim selection with explicit claim_origin recording; defeater target-typing enforcement; answer-shape rule cascade with rule_trace_json; atomic write with fencing-token validation.
- **15 verifier checks** ship in `verifier_data.py`; live `160sp/pipeline_lifecycle_full.db` passes 15/15 at Phase 1 ship.
- **Positive and negative round-trip proofs** demonstrate PNU semantic-hash change → invalidation → rebuild → verifier pass, and whitespace-only PNU reformat → no rebuild.
- **163 tests** pass at Phase 1 ship.

Acceptance: 10/12 criteria met; 1 partial (manual backup instead of scripted rotation since `scripts/backup_databases.py` doesn't exist in this repo); 1 deferred (render verifier — headless library not yet chosen).

### 2.2 Phase 2 (shipped 2026-05-23)

`docs/SPRINT_OVERSEER_PHASE_2_COMPLETION_2026-05-23.md` is the ship report.

- **4 new artefact kinds** registered: `article_finder_candidate`, `abstract`, `pdf_artifact`, `ocr_artifact`.
- **`overseer/article_finder_connector.py`** opens AF DB read-only; iter_papers reads core columns defensively; `paper_signature` is a stable SHA-256 over normalized (doi, canonical_paper_id, title).
- **`overseer/candidate_pdf_state.py`** — six-state machine: metadata_only → abstract_only → candidate_pdf_unverified → pdf_verified → ocr_ready → extracted. Each transition registers the appropriate artefact + adds a `derived_from` dependency edge.
- **`overseer/abstract_provenance.py`** — vocabulary-resolved source-label enforcement; require_allowed_source raises UnknownAbstractSourceError.
- **`overseer/article_finder_reconciler.py`** — async tick that reads AF.papers, registers article_finder_candidate artefacts on KA side, inserts cross_db_sync_events rows (pending → matched on KA-side record presence; pending → unresolved on AF signature drift).
- **`overseer/watchdog.py::soft_stuck_tick()`** — P25 progress-marker detection; raises medium-severity completion_queue rows for soft-stuck workers without killing them.
- **2 new verifier checks**: `_check_cross_db_sync` (unresolved events past threshold), `_check_abstract_source_provenance` (every abstract artefact has a derived_from edge to a candidate parent).
- **Phase 2 round-trip proof**: AF row → reconciler → state machine → extracted artefact → verifier passes all checks.
- **220 tests** pass at Phase 2 ship.

Acceptance: 11/11 criteria met. Live AF DB inspected: 16,257 papers; reconciler synced 3 papers at `processed_partial` status.

### 2.3 Phase 3 spec and review (2026-05-23)

Phase 3 specification was written, then twice revised under user-requested review rounds:

- `docs/DEPENDENCY_OVERSEER_PHASE_3_SPEC_2026-05-23.md` (544 lines) covers source packets, prompt templates, grounding verifier (field-pinned), bounded retry with parameter variance, dry-run mode with sensitivity sweep, content equivalence checks, batched approval, LLM-aided vocabulary canonicalization, six new verifier checks, the Phase 3 operator role with five responsibilities.

Then the **ruthless ten-expert panel review** (`docs/DEPENDENCY_OVERSEER_RUTHLESS_PANEL_REVIEW_2026-05-24.md`) returned:

- 0 unconditional go
- 4 proceed-with-changes (Kleppmann, Helland, McCaffrey, Akidau)
- 6 pause-and-fix (Wayne, Majors, Mitchell, Fournier, Larson, Armstrong)

You accepted the panel's recommendation. Phase 3 is paused, not killed. The 544-line spec is preserved for resumption. Phase 3 unpauses only when 11 panel gates close (model cards, formal model, supervision protocol, scope audit, watermarks, saga compensation, SIGKILL test, version_id rename, observability layer, runbook, 30 days operational data).

### 2.4 Post-panel pause work (shipped 2026-05-24)

`docs/DEPENDENCY_OVERSEER_POST_PANEL_PAUSE_PLAN_2026-05-24.md` records what was decided. The pivot was: **build the operational reality first, then govern it; do not govern a reality you have not yet operated.**

Concrete work shipped 2026-05-24:

- **`docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md`** — diagrams Article Finder as a single pipeline with seven entry points feeding eleven stages, with the overseer reconciler bridging Stage 4 (atlas_intake_decision) into KA-side state. Identifies what AF's existing Streamlit dashboard does NOT show (atlas_intake_decision distribution, ae_corpus_match_status, KA-side data, reconciler activity). Maps each of six real-AF-activity tasks (A–F) to specific dashboard widgets. Converges into a two-page monitoring spec.
- **Observability layer** — `verifier_run_history` and `reconciler_event_log` tables, migration applied to live DB, recording wired into `verify_strict()` and reconciler `tick()`.
- **Criterion switch** — reconciler default switched from the legacy `status='processed_partial'` (3 rows on live AF) to `atlas_intake_decision='accept_candidate'` (754 rows on live AF). The `ArticleFinderPaper` dataclass gained intake_decision and corpus_match_status fields.
- **KA Overseer Dashboard** — `ka_overseer_dashboard.py`, native Streamlit, two pages:
  - **Page 1 — AF→KA Pipeline Flow**: boxology funnel with live counts at each stage, reconciler-bridge widget showing the AF-eligible vs KA-registered gap, sync-event status counts, source attribution (top sources by paper count), stuck-paper detector (papers parked > 7 days).
  - **Page 2 — Overseer Health & Activity**: verifier health (pass/fail history, last run verdict, recent runs expander), reconciler activity (action distribution bar chart, tick count, last event), signature-drift unresolved list, completion-queue severity-grouped triage, stale artefact / quarantined queue counts.
- **`docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md`** — operations runbook with 13 sections. Quick-reference symptom-to-action table; 5-minute daily routine; reconciler tick procedure (manual + cron); DB backup discipline; failed-verifier triage; stale-artefact handling; completion-queue triage by severity; signature-drift resolution; AF activity triggers; informal escalation; migration rollback.
- **241/241 overseer tests pass**. Live verifier passes 17/17 checks. Live DB has 36 tables (6 KA-base + 22 dep-overseer + 6 article-epistemic-layer from a parallel worker's track + 2 observability), 30 indices.

### 2.5 Live operational state right now

- 13 `article_finder_candidate` artefacts in the lifecycle DB (3 from prior smoke + 10 from the criterion-switch smoke).
- 13 `cross_db_sync_events` rows, all `pending` (no real activity to upgrade or drift them yet).
- 2 `verifier_run_history` rows.
- 10 `reconciler_event_log` rows, all `inserted_pending`.
- 0 unresolved sync events; 0 BLOCKING completion-queue items; 0 stale artefacts; 0 quarantined queue items.

This is a healthy idle state. The dashboard is alive but observing an idle system.

---

## §3 — What I'm Waiting On (and Why)

Three things, in priority order.

### 3.1 Real AF traffic — waiting on you

The dashboard works. The pipeline boxology is encoded. The reconciler is running under the right criterion. But Article Finder has been mostly idle since 2026-05-10: 754 papers carry `atlas_intake_decision='accept_candidate'` (all from work done before 2026-05-10), and there's no recent activity on the production tail.

Per the post-panel pause plan §4.6, the path to making the dashboard observe real activity is six tasks (A–F) you can run. The two I recommended first:

- **Task A**: flip 5–10 papers in AF.papers to `atlas_intake_decision='accept_candidate'`. Lowest cost. Lets us see the dashboard's reconciler-bridge widget close in real time.
- **Task F**: drift a title in AF.papers on an already-synced paper. Lowest cost negative-path test. Lets us see the signature-drift widget light up + the BLOCKING completion-queue entry appear.

Why I'm waiting on you for these: I can write the SQL, but flipping rows in AF.papers is your prerogative — AF is a peer system and I should not modify it without your sign-off. The §4.6 tasks B–E (re-run AF's corpus matcher, run discovery on a fresh topic, drop PDFs in inbox, run full discovery on a research question) all require AF-side commands that may compete with your other priorities.

### 3.2 The 30-day operational window — waiting on time

Majors and Larson both insisted (panel review §7 and §11) that Phase 3 should not be discussed until at least 30 days of operational telemetry exist. The observability tables started recording 2026-05-24. The window opens 2026-06-23. Until then, every conversation about Phase 3 has to start with "we don't have the data yet."

Why I'm waiting on time: there is no shortcut. The whole point of the 30-day window is to convert speculative claims about Phase 3's value into empirical claims. Speeding it up by simulating traffic would defeat the purpose — that's why the snapshot simulator and story simulator were deferred (OVERSEER-AF-SNAPSHOT-SIMULATOR is marked deferred in TASKS.md).

### 3.3 The Phase 3 resume decision — waiting on you, after 3.2

After the 30-day window plus Tasks A/F, the data will say something about whether Phase 3 is needed. Specifically:

- If the reconciler-bridge widget shows a stable gap (i.e., AF has accept_candidate papers but they're not being driven through to AE handoff fast enough), then LLM-side governance to accelerate the bottleneck may matter.
- If the dashboard shows everything moving smoothly without LLM intervention (papers reach `matched` status purely via deterministic builders), then Phase 3 may be killable, and AE's existing anti-cheat contract (`Article_Eater_PostQuinean_v1_recovery/docs/SUBSCRIPTION_LLM_ORCHESTRATION_AND_ANTI_CHEAT_CONTRACT_2026-05-21.md`) is sufficient for the LLM governance the project actually needs.

Why I'm waiting on you for this: it's not a technical decision; it's a strategic one. The data informs it but doesn't make it.

---

## §4 — What Remains To Be Done

Three horizons.

### 4.1 Short-term (next 30 days; depends on Tasks A/F)

- **Validate the dashboard against real activity** — flip rows per Task A, drift a title per Task F, watch the widgets reflect both correctly. This is the one-time empirical confirmation that the build is operational, not just architectural.
- **Tune what's noisy in the runbook** — after 7–10 days of daily routine, refine the symptom-to-action table. Some symptoms named in the runbook may not actually fire; others may fire that I didn't anticipate.
- **Identify what's missing on the dashboard** — operating it will reveal which questions you ask that the dashboard can't answer. Those become widgets to add.

### 4.2 Medium-term (after 30-day window; gated on the resume decision)

If you choose "resume Phase 3":

- **Close the 11 panel gates.** Tracked in TASKS.md:
  - OVERSEER-SCOPE-AUDIT (Larson) — per-table "earning its keep" memo; delete tables that can't justify themselves.
  - OVERSEER-FORMAL-MODEL (Wayne) — TLA+ or Alloy model of the lease+fencing+claim state machine; model-check against the 28 P# invariants.
  - OVERSEER-SUPERVISION-PROTOCOL (Armstrong) — for each named worker, document supervisor + restart strategy + escalation path.
  - OVERSEER-MODEL-CARDS (Mitchell) — FAT* 2019 §3 fields per allowed LLM model.
  - OVERSEER-WATERMARK-WINDOWING (Akidau) — event-time semantics for cascade invalidation.
  - OVERSEER-SAGA-COMPENSATION (McCaffrey) — compensation logic per `cross_db_sync_events.event_kind`.
  - OVERSEER-SIGKILL-TEST (Kleppmann) — end-to-end test injecting process death mid-transaction.
  - OVERSEER-VERSION-ID-RENAME (Helland) — `active` → `is_current_version`; add `version_id` column.
  - Plus: the runbook stabilized, the observability data accrued, the data-grounded Phase 3 resumption memo written.
- **Execute Phase 3 v1** per the spec — source packets, prompt templates, LLM invocations, field-policy enforcement, grounding verifier (field-pinned, with dry-run mode), bounded retry with parameter variance, human review queue, content equivalence checks, vocabulary canonicalization, 6 new verifier checks. Estimated 8–11 commits.
- **Pilot backing_prose_v1 in dry-run mode** against real AE-submitted artefacts. Tune thresholds via the sensitivity sweep.
- **Phase 3 v1.1**: after 50 human-approved invocations of `provenance_summary`, add it to the auto-approve list with reviewer attestation.

If you choose "redesign Phase 3":

- Produce a slimmer governance plan based on observed needs. Likely scope: 2–4 new tables instead of 4; one prompt template instead of a registry; per-invocation provenance without the full source-packet hash-pinning machinery if it turns out to be over-engineered for the actual LLM workload.

If you choose "kill Phase 3":

- Tombstone the four scaffold tables (`llm_invocations`, `prompt_templates`, `source_packets`, `content_equivalence_checks`) with a migration that drops their CHECK constraints' enforcement but leaves the tables for audit.
- Delete the 544-line Phase 3 spec and the two revision documents, OR keep them for historical reference with a header saying "NOT IMPLEMENTED — see kill decision 2026-06-XX".
- Update `model_allowlist.json` to point at AE's existing anti-cheat contract as the binding LLM-governance surface.
- Final TASKS.md cleanup; remove the 11 panel-gate items.

### 4.3 Long-term (Phase 4 territory, after Phase 3 resolves)

Phase 4 was the original "extend to topics, DYK, search index, reports" plan. The post-panel pause plan didn't rule it out; it deferred it. Specific items if it lights up:

- **Register additional artefact kinds**: `topic_summary`, `dyk_card`, `search_index_row`, `daily_report`. One artefact_kinds entry each + a builder for each.
- **Backpressure on the rebuild queue**: at 760 papers and one worker the queue is bounded by data. At Phase 4 scale (topics × papers × dyk variants × search-index entries) the queue can grow without bound. Backpressure rules need to be defined.
- **Postgres migration**: SQLite WAL with one writer at a time was accepted for Phase 1 by the panel. If concurrent writers become operationally necessary at Phase 4 scale, migrate to Postgres. This is the most invasive change in the long-term plan.
- **A real on-call rotation**: §10 of the runbook is informal until Phase 4. With more pipelines and more state, formal on-call becomes necessary.
- **Render-side verifier** (`OVERSEER-RENDER-VERIFIER`): pick a headless browser library (Playwright vs Selenium vs HTTP-only HTML parsing), implement the rendered-page checks from the synthesis §4.
- **Auto-repair patterns** (Armstrong's gate, partially open): try-the-obvious-fix patterns for the three named cases — build crashes mid-write, tombstoned PNU with stale dependents, sync event past unresolved threshold. Move these from "human review by default" to "auto-retry, then human review."

---

## §5 — What We'll Have at the End (vs. now)

If everything ships — Phase 1 (done), Phase 2 (done), Phase 3 v1 + v1.1 (TBD), Phase 4 (TBD long-term):

**Capabilities we have now:**
- For 760 article-epistemic records, full hash-pinned provenance from any rendered article page back to its support set.
- For Article Finder candidates, automatic sync of accept_candidate state into KA with drift detection.
- Two-page Streamlit dashboard surfacing AF→KA pipeline state and overseer health.
- A strict verifier of 17 checks runnable in seconds.
- An operations runbook a junior operator could follow.
- 241 tests pinning the behaviour.

**Capabilities we DO NOT have now, that the full overseer would provide:**

1. **PNU pipeline integration through the overseer.** The `pnu_row` artefact kind is registered but no PNU builder writes through the overseer's contracts. PNU changes are detected by content_hashes diffing, not via a proper pipeline_registry-tracked source. After full ship, any PNU update would automatically cascade staleness to dependent epistemic records, queue rebuilds, and verify under the strict contract.

2. **Article-detail JSON builder integration.** `article_detail_json` is a registered kind. The existing `scripts/build_ka_adapter_payloads.py` writes JSON but not through the overseer. After full ship, every article-detail JSON would have a `latest_build_run_id`, a `support_set_id`, and a verified hash on the artefact registry.

3. **Topics, DYK cards, search index, reports** — none of these have an artefact kind yet. After Phase 4 they'd each be first-class overseer participants with their own builders, their own kinds, their own dependency edges back to the article-epistemic records they derive from.

4. **LLM enrichment with verified provenance.** Currently zero LLM artefacts exist in the lifecycle DB. After Phase 3 v1 ships, every LLM-generated piece of content (backing prose, content equivalence verdicts, vocabulary canonicalizations) carries a paired `llm_invocations` row with model name, prompt template hash, source packet hash, grounding verdict, human review decision, and worker surface.

5. **Cross-system release gate.** Currently `release_eligible` is a boolean on the `article_epistemic_records` row (companion contract) but no release process consults it. After full ship, the release process would call `can_promote()` (already implemented in `overseer/repair_loop.py`) before promoting any artefact, refusing on stale required artefacts, blocking completion-queue items, or last-mile production probe failures.

6. **Audit trail strong enough to publish.** After full ship, "where did this claim on the article page come from?" answerable from the DB in one query: claim_id → claim_origin → support_set → support_set_members → original sources (with hashes at capture time). If anything in that chain changes, the claim is marked stale automatically.

7. **An operational pattern for adding new pipelines.** Each new pipeline kind is: one artefact_kinds row + one pipeline_registry row + one builder + one or two tests. After the first three or four pipelines, this becomes a known cost.

**What we will NOT have, even at full ship:**

- Real-time updates (the model is async-tick-based, not event-driven).
- Multi-region or multi-machine reliability (single SQLite DB, single host).
- A general-purpose data-engineering platform (this is overseer for KA, not Airflow or Dagster).
- Automated repair of every failure mode (Armstrong's gate is partially open; most failures still route to human review).

---

## §6 — Will the Overseer Manage the Many Pipelines?

This is your real question. Honest answer in three parts.

### 6.1 By design, yes

The synthesis P12 invariant requires `artefact_kinds` to be registered, not hardcoded. The `pipeline_registry` table declares inputs and outputs per pipeline. The reconciler pattern from Phase 2 demonstrates how a peer system (Article Finder) can be integrated without modifying that peer's code. The native-write pattern from Phase 1 demonstrates how a pipeline owned by the same repo can write through the overseer contracts. **The mechanism is general.**

### 6.2 In practice today, no — only one pipeline writes through it

Seven `artefact_kinds` are registered. Only one builder (`article_epistemic_builder`) actually writes through the overseer's update_with_hashes + fencing-token + support-set contracts. The other six kinds are placeholders:

| Kind | Status | Who writes it today | Cost to integrate |
|---|---|---|---|
| `article_epistemic_record` | Active | Phase 1 builder via overseer | done |
| `pnu_row` | Registered, not written | PNU pipeline (separate; not yet integrated) | medium (≈1 sprint) |
| `article_detail_json` | Registered, not written | `scripts/build_ka_adapter_payloads.py` | medium (≈1 sprint to wrap existing builder in overseer contracts) |
| `article_finder_candidate` | Active (Phase 2) | Reconciler bridge (no native AF write) | done as bridge |
| `abstract` | Active (Phase 2) | Reconciler bridge | done as bridge |
| `pdf_artifact` | Active (Phase 2) | Reconciler bridge | done as bridge |
| `ocr_artifact` | Active (Phase 2) | Reconciler bridge | done as bridge |

So the picture is: **the overseer manages article-epistemic records natively, and observes Article-Finder-side state via a bridge. The other pipelines in the system (PNUs, article-detail JSON building, anything else that produces derived content) are not yet integrated.**

### 6.3 What full coverage would actually require

To answer your question with "yes, fully," each remaining pipeline needs:

**PNU pipeline integration** — there's a PNU registry and a PNU builder somewhere in the broader Atlas codebase. Integration means:
- Register the actual PNU builder in `pipeline_registry`.
- Have the PNU builder call `artefact_registry.update_with_hashes()` with a fencing token for each PNU it writes.
- Wire the invalidator so a PNU semantic-hash change marks dependent article-epistemic records stale automatically.
- Cost: probably one sprint. The mechanism is built; the wiring is new.

**Article-detail JSON builder integration** — `scripts/build_ka_adapter_payloads.py` (and friends) currently write JSON payload files to `data/ka_payloads/`. Integration means:
- Refactor that builder to take a fencing token and write through `artefact_registry.update_with_hashes`.
- Add a `pipeline_registry` row.
- Each JSON file's hash becomes the artefact's `semantic_hash`.
- Cost: probably one sprint.

**Topics, DYK cards, search-index entries, reports** — each is its own pipeline. Each needs an artefact_kind, a builder, a pipeline_registry row, and tests. Cost: roughly one sprint per pipeline.

Total integration work for "many pipelines under the overseer's management" at the current sprint cadence: 4–6 sprints (≈2–3 months) IF you decide each pipeline is worth integrating. The Larson scope audit (OVERSEER-SCOPE-AUDIT) is the right gate for that decision — the question "does this pipeline justify the integration cost?" needs an honest answer per pipeline.

### 6.4 The risk Larson flagged

The risk is not technical. The mechanism works. The risk is that the overseer becomes the answer to every question, and over-engineering creeps in. If a pipeline produces 5 artefacts per month, integrating it under the overseer adds maintenance cost without giving back proportional value. The Larson "earning its keep" memo, when written, should be honest about which pipelines genuinely benefit from overseer management and which are fine being managed manually.

My recommendation: integrate PNUs and article-detail JSON in the next two sprints (after the 30-day operational window). These are the highest-value pipelines because they're directly upstream of the article-epistemic records the overseer already manages — closing the loop makes the existing investment more valuable. Topics, DYK, search-index, reports: defer to Phase 4, and only integrate the ones that have a real production failure mode that the overseer would catch.

### 6.5 The yes-or-no answer

**Yes, the overseer is capable of managing many pipelines, and the mechanism is in place. No, it does not currently manage many pipelines — it manages one fully (article-epistemic) and one via bridge (Article Finder). Bringing the rest under management is per-pipeline integration work, not architectural change.** The Phase 4 plan and the OVERSEER-SCOPE-AUDIT memo will name which pipelines are worth integrating and which are not.

---

## §7 — Honest Risks and Limitations

What I would tell another engineer reading this for the first time.

1. **Single SQLite DB on a single host.** Not a problem today. Will be a problem when concurrent writers from multiple pipelines need to write simultaneously. The Postgres migration is a Phase 4 escape hatch; it's not free.

2. **The dashboard reads AF and KA via two different connections.** It works because each is read-only from the dashboard's perspective. If the dashboard ever needs to write (e.g., "approve this drift event" button), the write path needs to share the connection with the reconciler to avoid lock contention.

3. **No real-time pipeline monitoring.** The dashboard polls (manual Refresh or 30-second cache). There's no push notification when an AF paper hits accept_candidate. For a research workload this is fine. For a production user-facing system this would be inadequate.

4. **The 30-day operational window is real.** I cannot accelerate it without simulating data, which defeats the purpose. If you need a Phase 3 decision faster, the path is to compress the window with explicit acknowledgment that the decision is on less data.

5. **The runbook assumes one operator.** If two people try to triage completion-queue items simultaneously, the `assigned_to` field is the only protection and it's not enforced atomically. The Phase 4 on-call rotation work would harden this.

6. **AE integration is one-way today** — the reconciler reads AF, registers candidates in KA, but AE writes back into AF without going through the overseer. When Phase 3 lights up, AE submissions to the overseer need to be a real bidirectional integration. This is non-trivial work; the `accept_submission()` entry point is specified but not implemented.

7. **The verifier checks the structural shape of data, not its semantic correctness.** A paper whose article_epistemic_record claims something false will pass all 17 checks if the structural invariants hold. The overseer is an integrity layer, not a truth layer.

---

## §8 — The Single Most Important Decision Pending

After everything: the most consequential decision in the queue is whether Phase 3 resumes. That decision is gated on:

- Tasks A and F producing real activity on the dashboard.
- 30 days of operational data accruing.
- An honest answer from you to: "Has the existing Article Eater anti-cheat contract absorbed the LLM-governance need, or is a KA-side governance layer still required?"

Everything else — the panel-gate work items, the Phase 4 plans, the scope audit, the PNU integration — flows from that answer. If Phase 3 dies, the panel gates die with it (they're conditions for resumption, not work for its own sake). If Phase 3 resumes, the panel gates are the binding work-package.

The most operationally useful thing you can do this week: run Task A or Task F so the dashboard is observing real traffic. That makes the 30-day window meaningful. Without it, the window accumulates idle-state telemetry, which is not the same thing.

---

## §9 — Document Inventory

For navigation:

| Document | Purpose |
|---|---|
| `docs/HANDOFF_DEPENDENCY_OVERSEER_2026-05-23.md` | Original handoff, sets scope |
| `docs/DEPENDENCY_OVERSEER_EXPERT_PANEL_BRIEF_2026-05-23.md` | Brief for the design panel |
| `docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md` | Synthesis with B1–B12, P1–P28, R1–R10, OR1–OR10 |
| `docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md` | Phase 1 engineering contract |
| `docs/SPRINT_OVERSEER_PHASE_1_COMPLETION_2026-05-23.md` | Phase 1 ship report |
| `docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md` | Phase 2 engineering contract |
| `docs/SPRINT_OVERSEER_PHASE_2_COMPLETION_2026-05-23.md` | Phase 2 ship report |
| `docs/DEPENDENCY_OVERSEER_PHASE_3_SPEC_2026-05-23.md` | Phase 3 engineering contract (PAUSED) |
| `docs/DEPENDENCY_OVERSEER_RUTHLESS_PANEL_REVIEW_2026-05-24.md` | Ten-expert review; recommended pause |
| `docs/DEPENDENCY_OVERSEER_POST_PANEL_PAUSE_PLAN_2026-05-24.md` | What we'd do during the pause |
| `docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md` | AF pipeline diagram + dashboard spec |
| `docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md` | Operations runbook |
| `docs/DEPENDENCY_OVERSEER_STATE_OF_THE_BUILD_2026-05-25.md` | This document |
| `TASKS.md` (root) | Task ledger; "2026-05-24" section has post-panel work |
| `TOPIC_PROGRESS.md` (root) | Topic-level progress; TOP-OVERSEER, TOP-OVERSEER-2, TOP-OVERSEER-PAUSE |
| `ka_overseer_dashboard.py` (root) | Streamlit dashboard (run: `streamlit run ka_overseer_dashboard.py`) |

Source code is in `overseer/`. Tests in `tests/test_overseer_*.py`. Schema in `contracts/schemas/dependency_overseer/`. Migration history in `scripts/migrations/`.

---

## §10 — One Paragraph

The dependency overseer is partly built and operationally honest about what it is. Phase 1 (article-epistemic records) and Phase 2 (Article Finder bridge) ship and pass their own verifier 17/17. Phase 3 (LLM governance) was specified, then paused after a ten-expert panel review identified that we'd built a governance layer for a reality we hadn't yet operated. The post-panel work — observability tables, criterion switch, two-page Streamlit dashboard, operations runbook — closes the operational-visibility gap the panel named. The system is now waiting on you to trigger real Article Finder traffic and on 30 days of operational data to accrue, after which the Phase 3 resume decision becomes empirical rather than speculative. The mechanism for managing many pipelines exists; today the overseer manages one fully and one via bridge; bringing the others under management is per-pipeline integration work measured in sprints, not architectural redesign. The biggest open question is whether Phase 3 is needed at all; the answer comes from data, and the data takes a month.
