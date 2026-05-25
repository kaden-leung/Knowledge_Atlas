# Codex Handoff — Collapse the 90-Day Wait via Real-Time Decision Simulator

**Date:** 2026-05-25
**From:** CW (Claude Code, Opus 4.7 1M) — primary author of the dependency overseer
**For:** Codex (or any AI worker capable of building a Streamlit sim + Python event generator)
**Owner:** DK (Professor David Kirsh)

This handoff document is self-contained. Read this and the four artifacts named in §10 and you should have everything you need to build. Do not try to discover the context independently; the discovery cost is high and the relevant docs are explicitly named below.

---

## §1 — The Problem

The dependency overseer's panel review (`docs/DEPENDENCY_OVERSEER_RUTHLESS_PANEL_REVIEW_2026-05-24.md`) returned 0 unconditional go and 6 pause-and-fix votes. Two of the most pointed critiques (Majors §7 and Larson §11) demanded operational data before any further Phase 3 (LLM enrichment governance) work: ≥30 days of real traffic against Phase 1+2 before the resume decision.

That decision is the single most consequential item in the project's queue (see `docs/DEPENDENCY_OVERSEER_STATE_OF_THE_BUILD_2026-05-25.md` §8). Phase 3 currently has a 544-line implementation spec and 11 panel gates queued. Whether to ship, redesign, or kill it depends on what operating Phase 1+2 reveals.

**The problem**: Article Finder has been mostly idle since 2026-05-10. There is no incoming traffic to observe. Waiting 30 calendar days for AF to "do something" would accumulate idle-state telemetry, not the operating data the panel demanded. The 30-day clock is real but vacuous unless AF is producing real events.

**The opportunity**: simulate AF traffic at realistic distributions, route the simulated events through the existing overseer machinery (which works — 241/241 tests, live verifier 17/17), and surface real-time decisions to DK as the simulated AF state evolves. DK's decisions on the simulated decisions become the empirical record the Phase 3 decision needs. The simulator does not replace real data; it generates *decision-grade* data faster than the real world is generating it.

The deliverable Codex is being asked to build: **a Streamlit-driven AF-traffic simulator that runs scenarios on an adjustable clock, surfaces operator-decision prompts in real time, captures DK's decisions with timing and rationale, and produces a decision log the Phase 3 resume-or-kill memo will cite.**

---

## §2 — What Already Exists (and Why You Don't Need to Rebuild It)

The overseer is built and operating. Specifically:

- **Dependency overseer Phase 1**: schema (22 tables), Stage 1 builder for article-epistemic records, 17-check strict verifier, repair loop, lease/fencing-token discipline, watchdog, completion queue.
- **Dependency overseer Phase 2**: Article Finder read-only connector, async reconciler with drift detection, six-state candidate PDF state machine, two more verifier checks.
- **Observability layer (shipped 2026-05-24)**: `verifier_run_history` and `reconciler_event_log` tables, recording wired into `verify_strict()` and reconciler `tick()`.
- **Streamlit dashboard (`ka_overseer_dashboard.py`, 2026-05-24)**: two pages — AF→KA Pipeline Flow + Overseer Health & Activity.
- **Operations runbook (`docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md`)**: 13 sections naming the operator's decision points.

The reconciler points at `/Users/davidusa/REPOS/Article_Finder_v3_2_3/data/article_finder.db` by default. That live AF DB has 16,257 papers; 754 carry `atlas_intake_decision='accept_candidate'` (the new reconciler criterion); 438 carry `ae_corpus_match_status='matched'`. The most recent AF write timestamp is 2026-05-10.

**Do not rebuild any of the above.** Your simulator is a NEW component that produces events for the existing machinery to consume.

---

## §3 — The Conceptual Architecture

```
                       ┌──────────────────────────────────┐
                       │                                  │
        ┌─────────────►│  Simulated AF DB                 │◄────────────┐
        │              │  (separate from real AF.db)      │             │
        │              │  Schema: a subset of real AF     │             │
        │              │  schema sufficient for reconciler│             │
        │              └──────────────────────────────────┘             │
        │                            ▲                                  │
        │                            │ writes events on a clock         │
        │                            │                                  │
        │              ┌─────────────┴──────────────────┐               │
        │              │  Scenario Engine               │               │
        │ tick         │  Reads scenario script         │               │
        │ (sec/min/hr) │  Generates time-stamped events │               │
        │              │  (new candidate, status flip,  │               │
        │              │   title drift, etc.)           │               │
        │              └────────────────────────────────┘               │
        │                            ▲                                  │
        │                            │                                  │
        │              ┌─────────────┴──────────────────┐               │
        │              │  Sim Streamlit App             │               │
        │              │  - Scenario picker             │               │
        │              │  - Clock control (play/pause/  │               │
        │              │     accelerate/step)           │               │
        │              │  - Decision prompts            │               │
        │              │  - Decision log viewer         │               │
        │              └────────────────────────────────┘               │
        │                            ▲                                  │
        │                            │ DK interacts                     │
        │                            │                                  │
        │              ┌─────────────┴──────────────────┐               │
        │              │  DK (Operator)                 │               │
        │              │  Sees prompts; makes decisions │               │
        │              │  per the runbook               │               │
        │              └────────────────────────────────┘               │
        │                                                               │
        │              ┌────────────────────────────────┐               │
        │              │  EXISTING: KA lifecycle DB     │◄──────────────┘
        │              │  (use a separate sim instance) │   reads sim AF
        │              │  Reconciler / verifier / etc.  │   produces KA-side state
        │              └────────────────────────────────┘
        │                            │
        │                            ▼
        │              ┌────────────────────────────────┐
        └──────────────│  EXISTING dashboard            │
                       │  (ka_overseer_dashboard.py)    │
                       │  shows AF→KA pipeline state    │
                       └────────────────────────────────┘
                                     │
                                     ▼
                       ┌────────────────────────────────┐
                       │  Decision log file             │
                       │  (JSONL, one entry per decision│
                       │   with timestamp, scenario,    │
                       │   prompt, decision, rationale, │
                       │   time_to_decide)              │
                       └────────────────────────────────┘
```

Key boundaries:
- **The simulator writes to a NEW sim-AF DB**, not the real `/Users/davidusa/REPOS/Article_Finder_v3_2_3/data/article_finder.db`. Read-only access to real AF is fine for reference; writes are forbidden.
- **The simulator uses a NEW sim-KA lifecycle DB** (e.g., `data/sim_pipeline_lifecycle_full.db`), not the real `160sp/pipeline_lifecycle_full.db`. The real DB has 13 live `article_finder_candidate` artefacts from earlier smoke tests; do not pollute it with simulator output.
- **The simulator uses the existing reconciler, verifier, repair loop** — just pointed at the sim DBs. You do not rebuild overseer logic; you produce inputs and observe outputs.

---

## §4 — What "Real-Time Decision" Means Concretely

The runbook (`docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md`) enumerates seven classes of operator decision. The simulator should generate scenarios that produce each class. Here is the list, with the dashboard widget that surfaces each one:

| Decision class | What triggers it | Where it appears | Operator action |
|---|---|---|---|
| **BLOCKING completion-queue triage** | a `completion_queue` row with `severity='blocking'` (e.g., signature drift, fencing-token monotonicity violation) | Page 2 "Completion queue" + "Open BLOCKING items" expander | resolve / waive / escalate |
| **Signature drift resolution** | a `cross_db_sync_events` row flips to `status='unresolved'` because AF signature changed | Page 2 "Signature drift events" list | accept new signature (mark matched) / roll back AF / escalate |
| **Verifier failure investigation** | `verify_strict()` returns `overall_passed=False`; one or more of 17 checks fail | Page 2 "Verifier health" Failed count > 0 | read the checks_json, identify offending data, decide rebuild vs tombstone vs migration |
| **Stale artefact handling** | `artefact_registry.freshness_status='stale'` and `active=1` | Page 2 "Stale active artefacts" metric | enqueue rebuild / tombstone / accept staleness |
| **Stuck-paper triage** | AF paper parked at `edge_case` / `manual_review` / `needs_pdf_text` for > 7 days | Page 1 "Stuck papers" section | nudge / reroute / give up |
| **Cascade-alert acknowledgment** | a source change touches > 100 dependents (currently the threshold); raises `severity='high'` completion-queue row | Page 2 "Completion queue" high count | batch-rebuild / defer / kill the source change |
| **Soft-stuck worker review** | progress_marker unchanged > 5×heartbeat_interval (P25); medium-severity completion-queue row | Page 2 medium queue items | wait / kill worker / restart |

Each decision the simulator generates should match one of these classes, surface in the dashboard widget the runbook directs DK to, and capture DK's choice + rationale + time-to-decide.

---

## §5 — Recommended Build (Codex's deliverable)

I recommend a single Streamlit app, single Python file or two, that does:

### 5.1 A sim-AF DB constructor

A Python module `sim/sim_af_db.py` that creates a SQLite DB with the AF schema subset the reconciler reads:

```sql
CREATE TABLE papers (
    paper_id TEXT PRIMARY KEY,
    doi TEXT,
    title TEXT,
    canonical_paper_id TEXT,
    status TEXT,
    atlas_intake_decision TEXT,
    ae_corpus_match_status TEXT,
    updated_at TEXT,
    created_at TEXT,
    source TEXT,
    abstract TEXT,
    pdf_path TEXT,
    pdf_sha256 TEXT,
    ae_run_id TEXT,
    atlas_primary_topic TEXT
);
```

The schema mirrors enough of real AF to drive Pages 1+2 of the dashboard. (Full real AF has 72 columns; you only need ≈15.)

The constructor seeds the sim DB from a snapshot of real AF state, OR from a synthetic distribution, OR empty. Caller's choice via a Streamlit dropdown.

### 5.2 A scenario engine

A Python module `sim/scenarios.py` with named scenarios. Each scenario is a list of timed events. An event is:

```python
@dataclass
class SimEvent:
    at_offset_seconds: int   # seconds after scenario start
    kind: str                # e.g., 'new_candidate', 'flip_intake', 'drift_title'
    paper_id: str
    payload: dict            # event-kind-specific
```

The engine runs the scenario against a clock. The clock can be:
- **Real-time** (1 second per second)
- **Accelerated** (60×, 600×, 3600× — meaning 1 day in 24 minutes, 2.4 minutes, 24 seconds)
- **Stepwise** (advance one event at a time on a button press)

### 5.3 Scenario library (at least 5 named scenarios)

These are concrete and should be implemented:

1. **`steady_inflow`** — 50 new candidates per 8-hour AF "workday," 20% reach `accept_candidate` within 48h of arrival, rest stay candidate. Tests the dashboard's rate widgets and the "stuck paper" detector.

2. **`accept_wave`** — over 30 minutes (sim time), 100 papers flip to `atlas_intake_decision='accept_candidate'`. Tests the reconciler-bridge widget closing.

3. **`drift_storm`** — over 5 minutes, 12 already-synced papers have their titles edited (simulating a publisher metadata correction). Tests the drift-detection + completion-queue flow under multiple simultaneous drifts.

4. **`cascade_spike`** — a single source artefact changes its semantic_hash; 150 dependents already exist. Tests the cascade-bound alert + batched-rebuild decision.

5. **`pipeline_jam`** — 25 papers reach `atlas_intake_decision='needs_pdf_text'` and stay there. After 7 sim-days, they trip the stuck-paper detector. Tests the §6 "stuck paper" decision class.

Each scenario should have a one-paragraph description visible in the Streamlit picker so DK knows what they're about to run.

### 5.4 Streamlit sim app: `ka_overseer_simulator.py`

Place at repo root next to `ka_overseer_dashboard.py`. Pages:

- **Page 1 — Scenario Runner**: scenario picker, clock control (play / pause / accelerate / single-step), elapsed-time display, "events fired so far" counter, "decisions pending" badge.
- **Page 2 — Decision Queue**: when the dashboard widgets (in `ka_overseer_dashboard.py`) detect a decision-requiring state, this page surfaces a prompt. Each prompt shows: the dashboard widget context, the runbook procedure for this decision class, a free-form rationale text box, and N action buttons (resolve / waive / escalate / etc.). DK picks one. Choice + rationale + time-to-decide go to the decision log.
- **Page 3 — Decision Log Viewer**: tabular view of decisions made so far. Filterable by scenario, decision class, outcome. Exportable as JSONL.

### 5.5 Decision log

A JSONL file at `data/sim_decisions/<scenario>_<timestamp>.jsonl`. Each line:

```json
{
  "decision_id": "dec:<uuid>",
  "scenario": "drift_storm",
  "clock_at": "2026-05-25T14:23:45Z",
  "sim_elapsed_seconds": 120,
  "real_elapsed_seconds": 2.0,
  "decision_class": "signature_drift_resolution",
  "trigger_event_id": "rev:<uuid>",
  "trigger_summary": "Paper PDF-A title edited; signature drift detected by reconciler tick at sim:00:02:00",
  "dashboard_widget": "Page 2 / Signature drift events",
  "runbook_section": "§8",
  "available_actions": ["accept_new_signature", "roll_back_af", "escalate"],
  "chosen_action": "accept_new_signature",
  "rationale": "Title correction is a normal publisher metadata update; not suspicious.",
  "time_to_decide_seconds": 47.2,
  "operator_id": "dk"
}
```

This file is the artifact the Phase 3 resume-or-kill memo will cite.

### 5.6 Integration with the existing reconciler

The sim app should call the existing reconciler `tick()` after each scenario event-batch, pointed at the sim AF DB + sim KA lifecycle DB. The dashboard (Page 1/2 of `ka_overseer_dashboard.py`) should optionally point at the sim KA DB via an env var or sidebar override, so DK can have one browser tab on the simulator (driving events) and another on the dashboard (observing).

Or — your design choice — embed the dashboard widgets inside the simulator's Streamlit pages so it's a single app. Simpler for the user; more code to write. Pick one.

---

## §6 — Open Design Decisions (for Codex to weigh)

Each of these is a real choice with no obviously-right answer. The handoff is meant to give context, not pre-decide.

1. **Single app or two-tab setup?** Single app is simpler for DK; two-tab keeps `ka_overseer_dashboard.py` unchanged. I'd lean two-tab — the existing dashboard works and we don't want to invasively edit it. The simulator points its own AF/KA reads at sim DBs while the existing dashboard reads real DBs by default; both can run on different ports.

2. **Real-time vs accelerated default?** Accelerated (60×) for early development, with a clearly-labeled "real-time" mode for the final decision-quality run. The decision log should record both elapsed scales so analysis can adjust.

3. **How to surface "decisions pending"?** A badge in the sidebar with a count; clicking it goes to the Decision Queue page. Don't auto-pop-up; that breaks the operator's flow.

4. **What happens if DK doesn't decide in time?** If the scenario clock keeps running while DK is mid-decision, the queue can pile up unrealistically. Recommendation: when a decision is pending, the clock auto-pauses (DK can override). The "time_to_decide_seconds" then measures real-world deliberation time, which is what matters for runbook-tuning purposes.

5. **Should the sim modify the SAME KA lifecycle DB the dashboard reads, or a separate sim instance?** Strongly recommend separate. The real `160sp/pipeline_lifecycle_full.db` has 13 article_finder_candidate artefacts from prior smoke tests; you don't want to pollute or perturb it. The migration from `contracts/schemas/dependency_overseer/dependency_overseer.sql` + `observability_layer.sql` is what builds an empty sim KA DB.

6. **How to handle scenario branching based on DK's decision?** Simplest: scenarios are linear; DK's decisions are recorded but don't alter future events. More realistic: future events depend on past decisions (e.g., if DK escalated a drift, the next 3 drifts are followed up faster). Recommend starting linear; add branching if the linear data turns out to be insufficient for the Phase 3 decision.

7. **How long does a decision-grade scenario run?** Recommendation: a "session" is a 60–90 minute interaction in real time, covering 1–7 simulated days. DK runs 5–10 sessions over a week. That's 50–100 simulated days of decision data in 5–10 hours of DK's real time. Compresses the 30-day window into a working week.

8. **What constitutes "enough" data for the Phase 3 decision?** Recommendation: ≥40 decisions across at least 3 decision classes, with at least one scenario run for each of the 5 library scenarios in §5.3. If that turns out to be insufficient, expand.

---

## §7 — What the Resulting Decision Log Should Enable

After 5–10 sessions, the JSONL decision log feeds a Phase 3 resume-or-kill memo. The memo answers questions the panel review put on the table:

- **Majors**: how often does the verifier flip pass/fail under realistic operation? Where are the high-cardinality dimensions in actual use?
- **Larson**: how much of the operator's time is spent on each of the 17 verifier checks? Which produce no real signal? (Candidates for deletion in the scope audit.)
- **Fournier**: is the 5-minute daily routine realistic? When does it exceed 15 minutes and why?
- **Mitchell**: do we encounter situations where LLM governance would change the operator's decision? If not — Phase 3 dies. If yes — Phase 3 redesign vs resume becomes informed.
- **Akidau**: are there scenarios where event-time matters (late data, out-of-order changes) that the current processing-time model handles poorly?

The decision log makes these questions answerable. Today they are unanswerable.

---

## §8 — Success Criteria (what "done" looks like)

A successful Codex deliverable:

1. `sim/sim_af_db.py` builds a fresh sim AF DB with the schema in §5.1; idempotent.
2. `sim/scenarios.py` implements all 5 named scenarios from §5.3.
3. `ka_overseer_simulator.py` launches via `streamlit run ka_overseer_simulator.py`. Pages 1–3 exist and work.
4. Running scenario `accept_wave` against a fresh sim KA DB produces 100 article_finder_candidate artefacts in the sim KA DB; the existing dashboard (pointed at the sim KA DB) shows the gap close in real time.
5. Running scenario `drift_storm` produces signature drift events; the dashboard surfaces them; DK can record decisions on them; decisions land in the JSONL log.
6. At least one full decision session has been run (DK + Codex + simulator) covering at least 2 scenarios; the decision log has ≥10 entries.
7. The existing 241 overseer tests still pass — your work does not touch `overseer/`, `tests/test_overseer_*.py`, or `ka_overseer_dashboard.py` except via clearly-scoped read paths.

Stretch goals (nice if achievable in the same session):

- A "session report" markdown file generated at session end, summarizing decisions made, time spent, decision-class distribution, and anomalies. Becomes Phase 3 memo raw material.
- Scenario authoring help — a JSON schema for scenario files so DK can write new scenarios without touching Python.
- Replay mode — given a decision log, replay the same scenario with the same decisions and confirm the outcome is identical (regression test for the sim itself).

---

## §9 — What Codex Must NOT Do

1. **Do not modify the real AF DB** at `/Users/davidusa/REPOS/Article_Finder_v3_2_3/data/article_finder.db`. Read-only access is fine.
2. **Do not modify `160sp/pipeline_lifecycle_full.db`**. Use a separate sim KA DB.
3. **Do not modify code under `overseer/`** unless absolutely necessary and clearly scoped. The 241 tests must continue to pass at every commit.
4. **Do not modify `ka_overseer_dashboard.py`** to add sim-specific logic. The dashboard works against any KA lifecycle DB via the connection helper; if you need it pointing at the sim DB, parameterize the connection, don't rewrite the widgets.
5. **Do not add heavy dependencies**. Native Streamlit only; no plotly, no streamlit-autorefresh, no streamlit-extras. The pause plan was explicit about "light Streamlit." If you genuinely need plotly for the decision-log chart, add it as an OPTIONAL import with a fallback to `st.dataframe`.
6. **Do not invent your own runbook**. The decision classes are in §4 above and the actions per class come from `docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md`. If you find a decision class the runbook doesn't cover, surface it back to DK rather than guessing.
7. **Do not claim the sim produces real data.** Every decision log entry should carry a `is_simulated: true` flag. The Phase 3 memo will need to disclose that the data is simulated. Hiding this would defeat the panel-review discipline.
8. **Do not skip the operations runbook integration**. When the simulator surfaces a decision prompt, the prompt must reference the relevant runbook section (e.g., "Runbook §7 — Triaging the completion queue"). This is how the sim tests whether the runbook actually works.

---

## §10 — Required Reading (≈90 minutes total)

In this order:

1. **`docs/DEPENDENCY_OVERSEER_STATE_OF_THE_BUILD_2026-05-25.md`** (352 lines, ~20 min) — the situation, what's built, what's pending. Read every section.
2. **`docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md`** (396 lines, ~20 min) — the AF pipeline stages, what the dashboard shows, what data sources are needed. §2 (the boxology diagram) is the most important.
3. **`docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md`** (264 lines, ~15 min) — the runbook. Every section names a decision class and how to handle it. §7 (completion-queue triage) and §8 (signature drift) are the most relevant for simulated decisions.
4. **`ka_overseer_dashboard.py`** (408 lines, ~15 min) — read the code. Page 1 (`page_pipeline_flow`) is the AF→KA bridge view; Page 2 (`page_overseer_health`) is the verifier + queue view. The simulator should make these widgets light up on simulated events.
5. **`docs/DEPENDENCY_OVERSEER_POST_PANEL_PAUSE_PLAN_2026-05-24.md`** §4.4 "Story mode simulator" (10 lines, ~2 min) — this was the deferred design that this Codex deliverable resurrects with the real-time-decision twist.

Skip-unless-needed:

- The panel review (`DEPENDENCY_OVERSEER_RUTHLESS_PANEL_REVIEW_2026-05-24.md`) — relevant only if Codex wants to understand why the 90-day wait was imposed.
- The synthesis (`DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md`) — relevant only if Codex needs to understand the architectural invariants. The dashboard + runbook are sufficient to build the sim.
- The Phase 1/2/3 implementation specs — the simulator does not depend on them.

---

## §11 — Where to Start

I'd suggest this order of work (Codex):

1. Confirm the required-reading list is digested and the boxology + decision-class table make sense. If anything is unclear, ask DK before writing code.
2. Land an empty sim KA DB by running the existing migration against a fresh SQLite file. Confirm `streamlit run ka_overseer_dashboard.py` works pointed at that DB (it should show all zeros).
3. Build `sim/sim_af_db.py` first — schema + a seed_from_snapshot function. Smoke test by writing 5 rows.
4. Build `sim/scenarios.py` with one scenario (`accept_wave`). Run it manually; confirm the existing reconciler picks it up.
5. Build `ka_overseer_simulator.py` Streamlit app with Page 1 (scenario runner) — clock control, scenario picker, status display. No decision capture yet. Confirm `accept_wave` runs end-to-end.
6. Add Page 2 (decision queue) — surface drift events, BLOCKING items. Add the decision capture form. Confirm a drift in the `drift_storm` scenario produces a prompt.
7. Add Page 3 (decision log viewer). Confirm decisions persist in JSONL.
8. Add the other 4 scenarios.
9. Run a real session with DK; refine UI based on his feedback.

Estimated effort: 1–2 dedicated sessions if Codex is up to speed on the existing code; 2–3 if not.

---

## §12 — Handoff Q&A (anticipated questions)

**Q: Why not just wait the 30 days?**
A: Because AF is idle and waiting doesn't generate data. The 30-day clock was nominal; the panel actually wanted ≥30 days of real operating signal. We can produce that signal faster via simulation + real DK decisions.

**Q: Why have DK make decisions on simulated events? Isn't that contrived?**
A: Because the decisions ARE what we need to study. The panel asked "is Phase 3 needed?" The answer comes from observing what kinds of decisions a real operator faces in operation. The decisions are real even if the triggering events are simulated.

**Q: Should the simulator also simulate AE (Article Eater)?**
A: Phase 1+2 don't need AE — they read AF and write KA-side state. Phase 3 would involve AE submitting LLM artefacts. For this deliverable, leave AE alone. If the Phase 3 resume memo says we need an AE simulator too, that's a separate handoff.

**Q: What if DK's decisions during simulation are nothing like what he'd do in production?**
A: Then we've learned that the runbook is wrong or the dashboard surfaces the wrong things. That itself is a Phase 1+2 finding the panel would care about. The decision log surfaces this.

**Q: What if the simulator finds a bug in the overseer?**
A: Excellent. Report it. Fix it in `overseer/` with a proper test. The simulator is also a stress test of the existing build.

**Q: Can the simulator help with Article Eater workload too?**
A: Same answer as the AE question above. Out of scope for this deliverable; possible follow-up.

**Q: What's the deadline?**
A: There isn't one. The whole point is to compress the 90-day wait, but compressing it by a week is still a win. Take the time you need to build it well; don't ship a half-working sim that produces unreliable decision data.

---

## §13 — One Paragraph Summary

The overseer's Phase 3 decision is the most consequential pending choice in the dependency-overseer track and is gated on ≥30 days of operational data the panel demanded. Real AF traffic isn't coming on its own. This handoff asks Codex to build a Streamlit-based AF traffic simulator with 5 named scenarios, an adjustable clock, and real-time decision prompts that route to the existing dashboard widgets and runbook procedures, capturing DK's decisions in a JSONL log. The log becomes the empirical foundation the Phase 3 resume/redesign/kill memo will cite. Constraints: do not modify the real AF DB, the real KA lifecycle DB, the overseer code, or the existing dashboard's widgets; produce a separate sim infrastructure that uses the existing machinery via parameterized connections. Required reading is ≈90 minutes across 5 documents named in §10. Estimated build effort: 1–2 sessions. Start by reading the required-reading list and confirming the decision-class table makes sense before writing code.
