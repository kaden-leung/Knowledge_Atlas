# Dependency Overseer Simulator + Service-Grade Supervision Integration

**Date:** 2026-05-25  
**Author:** Codex  
**Audience:** DK  
**Purpose:** state plainly where the AF traffic simulator effort stands, what is missing, and how the emerging service-grade supervisor should be designed into it from the beginning.

---

## §1 — Present State

The current state is mixed:

- the **dependency overseer core** is real and operating;
- the **dashboard** is real;
- the **operations runbook** is real;
- the **AF traffic simulator handoff** is real and quite strong;
- the **AF traffic simulator implementation** does not yet appear to exist.

Evidence:

- present:
  - `/Users/davidusa/REPOS/Knowledge_Atlas/ka_overseer_dashboard.py`
  - `/Users/davidusa/REPOS/Knowledge_Atlas/docs/CODEX_HANDOFF_AF_TRAFFIC_SIMULATOR_2026-05-25.md`
  - `/Users/davidusa/REPOS/Knowledge_Atlas/docs/DEPENDENCY_OVERSEER_STATE_OF_THE_BUILD_2026-05-25.md`
  - `/Users/davidusa/REPOS/Knowledge_Atlas/docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md`
- absent:
  - `ka_overseer_simulator.py`
  - `sim/sim_af_db.py`
  - `sim/scenarios.py`

So the project is **not stalled conceptually**. It is stalled at the ordinary next engineering step: turning a good handoff into running code.

---

## §2 — What the Handoff Gets Right

The handoff is strategically sound.

Its strongest claims are correct:

1. **The operational-data bottleneck is real.**
   AF traffic is too sparse to generate decision-grade evidence for the Phase 3 resume decision on a reasonable timescale.

2. **A simulator is the right response.**
   The simulator is not being asked to fake production truth. It is being asked to generate a stream of operator decisions against the already-built overseer machinery.

3. **The boundaries are disciplined.**
   The handoff correctly forbids:
   - writing to the real AF DB;
   - polluting the real KA lifecycle DB;
   - rebuilding the overseer core;
   - rewriting the dashboard widgets.

4. **The deliverable is concrete.**
   The named scenarios, pages, decision log format, and success criteria are sufficiently specific to build against.

In short: this is not a vague product memo. It is a serious engineering brief.

---

## §3 — What Is Missing From the Handoff

The handoff is strong on **domain simulation**, but comparatively weak on **operational supervision**.

That omission is understandable, because the handoff is about the simulator. But it matters.

The simulator will itself become a small distributed system. Even in a modest first version it has:

- a simulated AF DB;
- a simulated KA lifecycle DB;
- a scenario clock;
- a scenario engine;
- reconciler ticks;
- verifier runs;
- a Streamlit operator surface;
- a decision queue;
- a JSONL decision log.

Those components can fail, drift, stall, or mislead independently of the overseer logic they are meant to exercise.

Therefore the simulator needs not just features, but governance.

---

## §4 — Why the Service-Grade Supervisor Belongs Here

The service-grade supervisor has a necessary role to play.

Not because the simulator is “big,” but because its purpose is epistemic. It exists to generate evidence for an architectural decision. Therefore its own operation must be trustworthy enough that the resulting evidence is worth reading.

The supervisor’s role is to answer questions such as:

- is the simulator clock actually advancing?
- is the scenario engine firing events when it says it is?
- is the reconciler ticking against the **sim** DBs rather than the real ones?
- is the decision queue draining, or merely accumulating?
- are the dashboard widgets reading the same state the simulator is mutating?
- are the decision logs complete, ordered, and replayable?
- did a scenario pause because DK was thinking, or because the process silently died?

Without a supervisor, one can easily produce something persuasive-looking that is not dependable enough to serve as evidence.

So, yes: the service-grade supervisor is not optional decoration. It is part of the apparatus.

---

## §5 — Control-Plane Lessons Already Learned Elsewhere

The substitution-graph control-plane work has already taught several lessons that should be applied here immediately.

### 5.1 State names must be explicit

Natural language states such as `idle`, `done`, or “clean stopping point” create managerial confusion.

The simulator and its worker-like components should use explicit states such as:

- `starting`
- `ready`
- `running`
- `paused_for_operator`
- `paused_for_error`
- `waiting_for_reconciler`
- `decision_pending`
- `standing_down`
- `crashed`

### 5.2 Transitions matter more than labels

Most failures are failures of transition, not of isolated state.

The supervisor should track transitions such as:

- scenario selected -> scenario initialized
- clock running -> event fired
- event fired -> reconciler tick run
- reconciler tick run -> dashboard-visible change
- decision surfaced -> decision answered
- decision answered -> scenario resumed

### 5.3 Presence and activity are different

A component may be:

- alive but blocked,
- alive but paused by policy,
- alive and productive,
- absent but still reflected in stale state.

The supervisor must distinguish these.

### 5.4 Reporting must fail soft

A malformed heartbeat or log record should degrade visibility, not destroy it.

The supervisor should treat observability inputs as potentially imperfect and recover gracefully where possible.

### 5.5 Queue authority must be explicit

The simulator must not quietly invent its own “extra” routing logic once it is running.

Queue and decision authority should be explicit:

- scenario engine owns event injection;
- reconciler owns sync logic;
- operator owns runbook decisions;
- supervisor owns liveness and escalation judgments.

---

## §6 — What the Supervisor Should Govern in the Simulator

The first supervisor for this track should govern six things.

### 6.1 Process registry

Registered supervised components:

- `sim_clock`
- `scenario_engine`
- `sim_af_db_writer`
- `reconciler_tick_runner`
- `verifier_runner`
- `decision_queue_surface`
- `decision_log_writer`
- optional `dashboard_probe`

For each:

- role
- expected heartbeat interval
- current state
- last progress time
- restart policy

### 6.2 Heartbeats and observed heartbeats

Each component should emit:

- `heartbeat_at`
- `last_progress_at`
- `state`
- `details_json`

The supervisor should also record:

- `last_heartbeat_observed_at`

This avoids a familiar deception: trusting stale self-reported time without recording when the supervisor actually saw it.

### 6.3 Transition log

The supervisor should write a durable transition history:

- `from_state`
- `to_state`
- `reason`
- `component`
- `changed_at`

This becomes the real audit trail of the simulator’s own operation.

### 6.4 Decision-prompt lifecycle

Each operator decision prompt should have an explicit lifecycle:

- `raised`
- `visible`
- `acknowledged`
- `answered`
- `expired`
- `suppressed`

This is crucial. Otherwise one cannot tell whether a quiet period means “no decisions were needed” or “decisions were needed but not surfaced.”

### 6.5 Clock and replay integrity

The supervisor should track:

- sim elapsed seconds
- real elapsed seconds
- event count fired
- decision count pending
- whether the scenario is deterministic under replay

The simulator’s epistemic value depends heavily on this.

### 6.6 DB-target integrity

The supervisor should continually record which DBs are in use:

- sim AF DB path
- sim KA DB path
- dashboard DB target
- reconciler DB target

This is not ornamental. Pointing one process at the real DB by accident would invalidate the exercise.

---

## §7 — Recommended Architecture

The recommended design is:

### Layer A — Existing overseer core

Leave it largely alone.

- lifecycle DB schema
- reconciler
- verifier
- repair loop
- dashboard widgets

### Layer B — Simulator

Build this as the domain-event engine.

- `sim/sim_af_db.py`
- `sim/scenarios.py`
- `ka_overseer_simulator.py`

### Layer C — Service-grade supervisor

Build this as a thin but explicit control plane for the simulator apparatus.

It should not replace the simulator. It should govern it.

Recommended modules:

- `sim_supervisor/supervisor_db.py`
- `sim_supervisor/component_registry.py`
- `sim_supervisor/heartbeat.py`
- `sim_supervisor/transitions.py`
- `sim_supervisor/decision_prompt_registry.py`
- `sim_supervisor/status_report.py`

Recommended storage:

- a dedicated SQLite DB, e.g.
  `/Users/davidusa/REPOS/Knowledge_Atlas/data/sim_supervisor.db`

Recommended outputs:

- human-readable markdown status
- machine-readable JSON status
- optional Streamlit “supervisor health” page

---

## §8 — Minimal First Slice

The first sensible slice is not the whole supervisor. It is the minimal supervision that makes the simulator trustworthy enough to begin operating.

### Slice 1

Build:

1. process/component registry
2. heartbeat table
3. transition table
4. decision-prompt lifecycle table
5. one markdown status report

This gives us:

- liveness
- freshness
- prompt visibility
- explicit state changes

That is enough to prevent the worst class of silent failures.

### Slice 2

Add:

1. DB-target integrity checks
2. clock drift and stalled-clock detection
3. replay metadata
4. operator-attention queue for failed or neglected prompts

### Slice 3

Add:

1. supervisor-runbook integration
2. automatic restart/stand-down actions for simulator components
3. session-summary generation

---

## §9 — How This Changes the Simulator Build Order

The handoff’s suggested order is sound, but it should be amended slightly.

Recommended order:

1. read the required documents
2. land empty sim AF DB and sim KA DB
3. build one scenario and run it manually
4. build the minimal supervisor slice
5. build the Streamlit simulator UI
6. wire decision capture
7. add remaining scenarios
8. run supervised sessions with DK

This is better than building the full UI first, because it prevents the familiar error of producing a vivid front-end atop an operationally opaque back-end.

---

## §10 — Concrete Assessment

My present judgment of the overall development state is:

- **dependency overseer core**: substantially real and credible
- **dashboard and runbook**: real and useful
- **simulator concept and handoff**: strong
- **simulator implementation**: not yet begun in a visible way
- **service-grade supervision for the simulator**: not yet designed into the repo

So the program is not immature. But it is not yet at the point where one can say “the simulator is underway.” It is at the point where one can say “the simulator is correctly specified and should now be built.”

---

## §11 — Recommended Next Action

The next rational move is:

1. create the sim DB scaffolds;
2. build the first scenario (`accept_wave`);
3. build the minimal supervisor slice alongside it, not afterward.

That will produce an apparatus worth trusting, rather than a merely impressive toy.

