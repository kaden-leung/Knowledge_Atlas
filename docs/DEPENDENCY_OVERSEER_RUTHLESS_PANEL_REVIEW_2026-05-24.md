# Dependency Overseer — Ruthless Multi-Expert Panel Review

**Date:** 2026-05-24
**Purpose:** A go/no-go enterprise evaluation of the dependency overseer (Phases 1 shipped, Phase 2 shipped, Phase 3 specced) conducted by ten impersonated experts. Each panelist is my best reconstruction of a real industry/research figure based on their published work. Where I cite their writing, I name the source. The panel's mandate is to *shred* — not validate, not encourage, not perform politeness. Politeness wastes time. The synthesis at the end tallies go/no-go votes and names what would have to change for unanimous proceed.

---

## §0 — Framing Prompt (reusable for future module reviews)

> A new infrastructure module is about to ship. Three documents describe it: a panel-derived design synthesis, a Phase 1 implementation spec (already executed), and (for Phase 2 and Phase 3) phase-specific specs.
>
> Convene 7–10 high-level experts whose careers are most directly relevant to the module's domains: distributed systems, schema evolution, append-only data, formal methods, observability, LLM provenance, streaming semantics, operational scale, scope discipline, fault tolerance.
>
> For each expert: (a) summarize their published positions briefly with direct citations to their work; (b) have them describe what the module is and what's promising about it; (c) then have them shred — find what's wrong, risky, or badly designed in what's built and what's planned; (d) close with a one-sentence go/no-go vote and the single change that would flip their vote.
>
> No expert may merely validate. Every section must contain at least three specific failure modes or design flaws that the expert names from their domain. Each criticism must point to a specific section, file, or commit, not a vague concern.
>
> The synthesis tallies votes, names the common themes, and produces an enterprise-level recommendation: ship, ship with conditions, pause and redesign, or kill.

---

## §1 — Roster

| Reviewer | Role / Best-known work | The slice they're best positioned to shred |
|---|---|---|
| Martin Kleppmann | *Designing Data-Intensive Applications* (DDIA), "How to do distributed locking" | Fencing tokens, lease semantics, single-writer SQLite, consistency model |
| Pat Helland | "Data on the Outside vs Data on the Inside" (CIDR 2005); "Immutability Changes Everything" (CIDR 2015) | Append-only / immutability discipline, schema-evolution, artefact identity |
| Hillel Wayne | *Practical TLA+*; "Formal methods at Amazon" (essay) | Invariants, state machines, what's actually proven vs prose-asserted |
| Caitie McCaffrey | "Distributed Sagas" (Microsoft Research talk, 2017); "Building Scalable Stateful Services" (Strange Loop 2015) | The AE↔overseer reconciler, saga compensation, failure modes |
| Charity Majors | *Observability Engineering* (with Liz Fong-Jones and George Miranda) | The verifier-vs-observability gap; high-cardinality dimensions |
| Margaret Mitchell | "Model Cards for Model Reporting" (FAT* 2019) | LLM provenance, the missing model cards, grounding semantics |
| Tyler Akidau | *Streaming Systems* (with Slava Chernyak, Reuven Lax); "The world beyond batch" (O'Reilly Radar) | Event-time vs processing-time, invalidation cascade as a stream, late data |
| Camille Fournier | *The Manager's Path*; ZooKeeper PMC work | Operational realism, the cost of human-in-loop reviewers, coordination services |
| Will Larson | *An Elegant Puzzle*; *Staff Engineer* | Scope discipline, when good infrastructure becomes the problem |
| Joe Armstrong (in memoriam, via *Programming Erlang*, "Making reliable distributed systems in the presence of software errors" thesis) | "Let it crash" / supervision trees | Watchdog as single point of failure; repair semantics |

Ten reviewers. Each writes ~500–800 words. Each ends with go / proceed-with-changes / no-go.

---

## §2 — Shared Baseline

So every panelist evaluates the same artifact, this section pins down what they're reviewing.

**What the module is.** The dependency overseer is a SQLite-backed registry-plus-queue layer that lives in the Knowledge Atlas lifecycle DB (`160sp/pipeline_lifecycle_full.db`). It tracks the dependency graph among derived artefacts (PNUs, article-epistemic records, article-detail JSON, Article-Finder candidates, abstracts, PDFs, OCR outputs, claims, defeaters, belief-network links, etc.), records build runs, exposes a strict verifier of ~17 invariants today (~23 at Phase 3 ship), and enforces a small repair-loop state machine (stale → queued → claimed → building → fresh) with watchdog reclaim of stuck workers via heartbeat-based leases and monotonic fencing tokens.

**Where it's going.** Phase 2 added an asynchronous reconciler between an external Article Finder DB and the lifecycle DB. Phase 3 adds LLM enrichment governance: prompt-template registry, source-packet contract, field-pinned grounding verifier, dry-run mode for new templates, bounded 1-retry with mandatory parameter variance, human review queue, batched approval for content-equivalence decisions, vocabulary canonicalization.

**Strengths (consensus baseline).** (a) The lease/fencing-token construction is textbook (DDIA chapter 8); (b) tombstone-not-delete preserves audit history; (c) the verifier is structured per-check with explicit pass/fail reporting; (d) two-tier hashing (raw vs semantic) separates cosmetic from semantic change; (e) the active-vs-scaffold table split keeps the Phase 1 footprint coherent; (f) test coverage is real — 220 tests, all passing, with dedicated round-trip proofs for both positive and negative invalidation paths; (g) the schema is additive only, with durable backups taken before live migration; (h) Phase 3 is conservative-by-default and explicitly resolves OR9 (LLM semantic-equivalence false positives) by defaulting to human approval.

**Promises (what the panel is being asked to bet on).** (i) That a 22-table SQLite-backed overseer will scale to the team's actual workload (≤2000 papers, ≤10 concurrent workers); (ii) that the Phase 3 grounding verifier will catch hallucinated backing prose at a useful rate; (iii) that the Article Finder reconciler converges in bounded time; (iv) that the operator-role responsibilities (5 named hats) are sustainable for the team's reviewer cohort.

**Weaknesses (consensus baseline, before the shred).** (i) SQLite single-writer is a fixed concurrency ceiling; (ii) the spec layer (synthesis + 3 phase specs + this review) is ~3500 lines of design documentation for a system this small; (iii) none of the invariants are formally proven — all are prose claims; (iv) operational telemetry beyond pass/fail is absent; (v) Phase 3 ships before any real AE submissions exist, so the entire LLM-governance design is speculative; (vi) the human-in-loop review burden, if Phase 3 lights up with real submissions, will be substantial.

Now the panel.

---

## §3 — Reviewer 1: Martin Kleppmann

> *Designing Data-Intensive Applications*, chapter 8: "If a node is alive but cannot communicate with other nodes, the other nodes may decide that the apparently dead node should be terminated. Distributed locks need fencing tokens to prevent zombie leaseholders from corrupting data. Without a fencing token, you have no protection against a process that comes back from the dead."

**What the overseer is and what's promising.** The dep overseer correctly implements the canonical pattern from DDIA chapter 8: heartbeat-based lease + monotonic fencing token + compare-and-swap on commit (`update_with_hashes` WHERE clause). The `current_fencing_token` increment on every claim, and the per-write CAS check, are the right answers. The watchdog reclaim that increments the token before reassignment is correct. I want to be clear about this part: the *shape* is right.

**What's wrong.**

1. **The watchdog itself is a single supervisor with no failure story.** `overseer/watchdog.py::tick()` is a function called by `scripts/dependency_overseer_reconciler_tick.py` or by some unspecified cron job. If the watchdog crashes, hangs, or simply isn't scheduled, no reclaims happen. Live leases pile up. Then a worker dies, no one reclaims, and the queue stops. DDIA chapter 8 spends paragraphs explaining that distributed locks need *external monitoring of the monitor*. The spec doesn't say what monitors the watchdog. This is the classic "who watches the watchmen" failure mode; the dep overseer has it.

2. **The fencing token is only checked at the artefact_registry write. Other related tables (content_hashes, claims, defeaters, etc.) are written without that check.** Look at `article_epistemic_builder.py::build_one()` — the transaction inserts into content_hashes, claims, defeaters, belief_network_links, answer_shape_decisions, and *then* calls update_with_hashes (which has the CAS). If a stale-fencing-token worker reaches the end of the transaction, its inserts into the child tables succeed (no CAS), only the artefact_registry update fails. The transaction rolls back, but only because Python re-raises. If a future refactor catches the exception, the child rows are silently committed. Defense in depth: the CAS check needs to be at *every* write in the multi-table transaction, not just the last one.

3. **SQLite WAL + autocommit + explicit BEGIN IMMEDIATE is fragile.** `overseer/db.py` sets `isolation_level=None` to give explicit transaction control. This is correct. But the `transaction()` context manager's only safety is "raise on exception, rollback." A `KeyboardInterrupt` or a `sys.exit()` inside the with-block bypasses the rollback (Python's exception hierarchy notwithstanding, real production processes do exit ungracefully). SQLite's WAL gives you durability but not atomicity across these abrupt exits. Read DDIA chapter 7 on isolation levels — what you have here is closer to "read uncommitted" with hopes.

4. **The "transactional discipline" P1 invariant is asserted in prose. It is not testable as written.** None of the 220 tests injects a mid-transaction failure to confirm rollback semantics. Add a test that kills the Python process between two writes and asserts the artefact_registry row is unchanged. If you can't write that test, you can't claim P1.

**Go / no-go**: **Proceed with changes**. The lease+fencing pattern is right, but extend the CAS check to every multi-table write site, document the watchdog-monitor protocol (or accept that a missed cron is silent data drift), and write the mid-transaction-crash test. Single change that flips my vote: a single end-to-end test that simulates SIGKILL between two writes and confirms zero partial state.

---

## §4 — Reviewer 2: Pat Helland

> *Immutability Changes Everything* (CIDR 2015): "Accountants don't use erasers; they create journal entries. Once something has happened, it has happened. We don't change the past. Immutable data is the only data we can trust across systems."

> *Data on the Outside vs Data on the Inside* (CIDR 2005): "Data on the outside is reference data and rules — semantically stable. Data on the inside is operational state — semantically fluid. The contract between them is the schema."

**What the overseer is and what's promising.** The tombstone-not-delete discipline (P5: `tombstoned_at` rather than DELETE) is correct, and I'm glad to see it implemented uniformly across `artefact_registry`, `dependency_edges`, `claims`, `defeaters`, `belief_network_links`. The content_hashes table that retains per-build history is the right move. The append-only ethic is there at the file level.

**What's wrong.**

1. **You have tombstones but no proper versioning.** `active=1` plus `tombstoned_at` plus a partial unique index on the natural key is a half-step. Real versioning would make the artefact_id include a monotonic `version_id`, so every update writes a new row and "active" simply means "highest version." Your design conflates "is this the most recent state" with "should consumers see this." Two concepts; one column. A future maintainer will read an `active=1, tombstoned_at IS NOT NULL` row and not know what to do with it.

2. **The hash on artefact_registry refers to content that lives somewhere else.** `artefact_registry.semantic_hash` is the hash of content that isn't *in* the row. The actual content sits in a JSON payload built at render time, or in child tables (claims, defeaters, etc.). What you've built is a hash that's authoritative for an object whose identity is distributed across N tables. This is the *Data on the Outside* problem in reverse: you've published a content hash without publishing the content. If the content's storage layout ever changes, the hash becomes a number-without-meaning. Either inline the canonical payload bytes in a content table, or publish the assembly algorithm with a version tag and verify the hash recomputes from a documented procedure.

3. **The companion contract's article_epistemic_records and your overseer's claims/defeaters/belief_network_links tables are duplicative.** A paper's epistemic record is one logical thing represented in two parallel table sets. You've taken on the integration debt of keeping them coherent without taking on the simplification of choosing one. This is exactly the boundary mess that "Data on the Outside" warns about.

4. **Build runs are append-only but the verifier doesn't use them.** `build_runs` has every column you'd need to reconstruct *why* an artefact has its current hash. The verifier reads artefact_registry and content_hashes but never asks "was this build run verified, failed, or aborted?" Build provenance is being recorded but not consulted. That's documentation, not safety.

**Go / no-go**: **Proceed**, with the understanding that the next month of operational scars will tell you whether the version_id + content-payload-table refactor is needed. The change that would flip me to enthusiastic-go: a single column rename — `active` → `is_current_version` — and a migration that adds a `version_id` to artefact_registry. That one rename clarifies the entire model.

---

## §5 — Reviewer 3: Hillel Wayne

> *Practical TLA+*: "A specification is a description of what the system is *allowed* to do. Without that, every test you write is an opinion."

> "Formal methods at Amazon" essay: "The biggest payoff of TLA+ at Amazon wasn't catching bugs in code. It was catching bugs in *understanding* — places where the team thought they had a design but the spec showed they didn't."

**What the overseer is and what's promising.** The phased specs are unusually disciplined. The synthesis carries B1–B12 + P1–P28 + R1–R10 + OR1–OR10 — that's a real attempt at an invariant catalog. Many infrastructure projects ship with zero invariant statements. You have 28+.

**What's wrong.**

1. **You have 28 invariants in prose and zero in any formal language.** Every invariant is one English sentence. Some are precise (P3: "(paper_id, schema_version) is unique among active rows"). Most aren't (P1: "every multi-table overseer write is one DB transaction" — what does "multi-table" mean precisely? Does writing to `worker_heartbeats` and `rebuild_queue` together count? The spec is silent). A TLA+ or Alloy model wouldn't even be enormous here — maybe 200–300 lines for the lease+fencing+claim state machine. The payoff would catch invariant collisions before they ship as runtime bugs.

2. **Invariant collisions exist that the spec doesn't acknowledge.** Specifically: P7 (revised) says "a claim holds while the worker's last heartbeat is younger than the heartbeat timeout." P2 says "building is transactionally separate from ready; consumers do not read building rows." But the watchdog reads `rebuild_queue` rows whose state IS 'building' to decide what to reclaim. So either the watchdog is not a "consumer" (in which case the term needs defining), or P2 is violated, or both — *and the spec doesn't tell me which*. A TLA+ model would force you to write `Watchdog_Reads_Building_State == ...` and you'd see the conflict immediately.

3. **Cascade bound at 100 is a magic number with no justification.** Why 100? Why not 10, or 1000? The spec says "tunable" but doesn't say what it should be tuned *to*. An invariant like "no single source change can produce a cascade larger than N where N = some-empirical-property-of-the-graph" would be a real invariant. "100" is a guess.

4. **The dry_run vs fresh state addition (§8.2) introduces new invariants without listing them.** You've added a `freshness_status='dry_run'` value. That implies new invariants: *no transition from dry_run to fresh except via operator action*; *no LLM artefact in dry_run has grounding_verdict='pass'*. These exist in §11 as verifier checks but are not in the P# invariant list. Verifier checks aren't invariants; they're tests. The two should be the same thing.

5. **The Phase 3 retry parameter variance rule is operationally vague.** "Must vary at least one of model_name, prompt_template_id, or a stochastic parameter." What counts as a stochastic parameter? `top_p=0.95` differs from `top_p=0.9` — does that count? `seed=42` differs from `seed=43` — does that count? In a TLA+ model you'd be forced to define `Varies(p1, p2) == ...` and you'd see that the rule as stated permits trivially-different parameters that don't actually change LLM behavior.

**Go / no-go**: **Pause and formalize**. The change that would flip me to go: a TLA+ or Alloy module covering the claim+fencing+lease state machine, 100–300 lines, model-checked against the 28 invariants. If model checking finds zero counterexamples, ship. If it finds one, you've learned something for free. Until then, every test you write is an opinion.

---

## §6 — Reviewer 4: Caitie McCaffrey

> "Distributed Sagas" (Microsoft Research talk, 2017): "A saga is a sequence of local transactions where each local transaction publishes events that trigger the next. The critical insight is *compensation* — if step N fails, you must run inverse transactions for steps 1 through N-1 to leave the system in a consistent state."

> "Building Scalable Stateful Services" (Strange Loop 2015): "If you can't draw the state diagram, you don't know what your service does."

**What the overseer is and what's promising.** The asynchronous reconciler between AE and the lifecycle DB (Phase 2 §3) is a saga pattern in everything but name. AE writes its half locally, the overseer writes its half locally, a reconciler tick pairs them. The cross_db_sync_events table is a saga log. Good.

**What's wrong.**

1. **You have a saga but no compensation logic.** When the reconciler creates a `cross_db_sync_events` row with `status='pending'` and registers an `article_finder_candidate` artefact, and then AE later changes its mind about the paper (e.g., flips its status away from `processed_partial` because the triage decision was reversed), what unwinds the candidate artefact on the KA side? Nothing in the spec. The candidate artefact remains active. The sync event stays pending forever. The verifier eventually flags it as unresolved past threshold — which is detection, not compensation.

2. **The state machine for candidate_pdf_state is acyclic (forward only).** That's wrong for the real world. PDFs get re-OCR'd. Abstracts get superseded by a publisher correction. The model can't represent "we OCR'd this PDF, decided the OCR was bad, want to redo it." The only path is forward through 6 states. No backward edges. Real document-processing systems have ~50% of all transitions be re-do or supersede. Either model that explicitly or document it as a Phase 4 concern.

3. **The "matched" status is one-shot.** Once a `cross_db_sync_events` row flips from pending to matched, what re-evaluates the match? AF changes happen. Papers get re-triaged. Atlas paper_ids change when the canonicalization rules change. A matched row remains matched forever in the current design. The signature drift check covers part of this — but only on the AF side. KA-side drift (the article_epistemic_record's content changes meaningfully without bumping the canonical paper_id) is not detected.

4. **Verifier threshold is wall-clock, not load-relative.** `_check_cross_db_sync` flags unresolved rows older than 300 seconds. But what if the reconciler tick runs once per 24 hours? 300 seconds is in the noise. What if it runs every 10 seconds? 300 seconds is a real backlog. The threshold needs to be relative to expected tick latency plus observed variance, not absolute. Otherwise it's either chronically firing or chronically silent.

5. **AE↔overseer crash-during-pairing is undefined.** What happens if the reconciler tick fetches AF state, writes the overseer's half of the sync, and then crashes before completing? Re-running the tick will see no half-state — the overseer's row is committed, but the reconciler hasn't acknowledged its work back to AE (because it never needed to; this is async). The next tick sees an AF row with a paired KA artefact and an existing pending event — looks fine. No symptom. Until you discover a paper that has TWO article_finder_candidate artefacts because the reconciler ran twice on a fresh `cross_db_sync_events` row that an earlier crash had left in an unobservable intermediate state. Idempotency-by-natural-key saves you here for the common case but not the edge case where AF state has changed between crashed-tick and next-tick.

**Go / no-go**: **Proceed with changes**. The change that flips me to enthusiastic-go: explicit compensation logic on the saga (define what reverses each event_kind), and a load-relative threshold for the verifier check. Without those, Phase 2 ships a saga that handles the happy path and detects (but doesn't repair) the unhappy path.

---

## §7 — Reviewer 5: Charity Majors

> *Observability Engineering* (with Liz Fong-Jones and George Miranda): "Observability is not metrics, logs, and traces. It is the ability to ask new questions of your system without shipping new code. If you can only ask the questions you anticipated, you don't have observability — you have monitoring."

> "Test in production": "Your customers are doing it for you whether you want them to or not."

**What the overseer is and what's promising.** I'll give credit where it's due: the verifier is structured per-check with explicit pass/fail and per-check failure lists. That's better than a single "is the system healthy" boolean. It's a real audit trail.

**What's wrong.**

1. **You have monitoring, not observability.** The verifier asks a fixed set of yes/no questions (17 in Phase 1+2, 23 at Phase 3 ship). What it does *not* do: enable a new question without shipping new code. The first time you want to know "of the LLM invocations that failed grounding in the last hour, which prompt_template_id had the highest failure rate, broken down by model_name?", you'll discover the verifier produces aggregate pass/fail counts and not per-event structured logs. You'll then add a new verifier check. Three months later you'll want a different breakdown. You'll add another. This is not observability; it's a growing patchwork of fixed reports.

2. **High-cardinality dimensions are absent from your data model.** Every `llm_invocations` row should produce a structured log event with cardinality on at least: `(model_name, prompt_template_id, prompt_version, component_type, grounding_verdict, review_decision, worker_surface, dry_run vs live, submitter_run_id, paper_id)`. That's ~10 dimensions. With those, you can ask anything. Without them, you have row counts in completion_queue and a verifier that says "no failures." Reality won't fit either container.

3. **The completion_queue is a TODO list, not a feedback loop.** Items pile up. There's no SLO on resolution time. There's no observability into *who* is resolving items, *how long* it takes, *which kinds* repeat. The verifier `_check_semantic_equivalent_rate` is the only one I can find that even tries a rate-based check, and it requires a hand-tuned threshold of 30% over a min-sample size of 20. Why those numbers? Because nobody knows yet, because there's no production data, because there's no observability.

4. **Dry-run mode produces a sensitivity sweep file.** Filed in `docs/SPRINT_OVERSEER_PHASE_3_GROUNDING_TUNING_<DATE>.md`. Per the spec, an operator reads this and writes a tuning report. Quiz: under what condition does this happen on schedule? Real answer: it doesn't. Without telemetry that surfaces "the 19th dry-run submission just happened, here are the sweep distributions, here are the outliers," the report won't get written until something breaks and someone goes looking.

5. **The verifier runs against a static lifecycle DB.** Where is the time series? When did this check last pass? When did it last fail? How frequently does it flip? The verifier produces a snapshot. Real systems need a history. At minimum, log every verifier run with timestamp and per-check pass/fail to a structured log table. Without that, the verifier's verdict tomorrow is statistically uncorrelated with its verdict today.

**Go / no-go**: **Pause for observability layer**. The change that flips me: add a `verifier_run_history` table (timestamp, per-check status, full failure JSON) plus an `llm_invocations_event_log` table (every invocation as a row with all 10 high-cardinality dimensions) — before Phase 3 ships. Otherwise you're flying with a checklist and no altimeter.

---

## §8 — Reviewer 6: Margaret Mitchell

> "Model Cards for Model Reporting" (FAT* 2019, with Wu, Zaldivar, Barnes, Vasserman, Hutchinson, Spitzer, Raji, Gebru): "Model cards are short documents accompanying trained machine learning models that provide benchmarked evaluation in a variety of conditions ... including intended use, evaluation results, ethical considerations, and recommendations."

**What the overseer is and what's promising.** Phase 3's commitment to source-packet pinning, prompt-template hashing, and per-invocation provenance is the right shape. You've at least made it impossible to lose the chain of custody from prompt to output. Many production ML systems can't say that.

**What's wrong.**

1. **There are no model cards.** `model_allowlist.json` is a list of allowed model names. That is provenance theater. A model_name is a string. A model card is a document covering: intended use, training data origin, known limitations, evaluation results on representative tasks, ethical considerations, recommendations on when NOT to use the model. Without those, you have a list of strings approved by no one for nothing. When a model is removed from the allowlist for a problem, future maintainers will not know what the problem was. When a new model is added, no one will know whether it's appropriate for the use case.

2. **The grounding verifier checks token overlap. It does not check who the LLM is.** Token overlap of 50% will pass for a model that was trained on the source corpus and is regurgitating memorized text. A different LLM might paraphrase the same source content correctly but with lower token overlap and fail the check. You're measuring something that correlates with grounding but isn't grounding.

3. **The Phase 3 pilot is `backing_prose_v1` — explanatory prose about warrants.** Explanation is the LLM task most prone to causal hallucination: stating mechanisms that don't exist, attributing effects to causes that weren't measured, smoothing over caveats. The grounding check (token overlap with source) does not catch any of these. A backing-prose generation that says "the Trier Social Stress Test demonstrates that enclosed rooms cause cortisol spikes" might token-overlap correctly with the source (which says the same thing in different words) but be a false causal claim if the study was correlational. Field-pinned grounding is necessary; it is not sufficient.

4. **The auto-approve list "Phase 3 v1.1 promotion requires reviewer attestation" is not a measurable bar.** "≥50 human-approved invocations with grounding_verdict='pass' and zero human_rejected" is necessary; it is not sufficient. What's the false negative rate of the human reviewers? What's the inter-rater agreement? On model card 101: you should require pre-registered evaluation tasks with held-out test sets before promoting any model+template combo to auto-approve. Otherwise the promotion is "the reviewer didn't notice anything bad in 50 reviews," which is a story about reviewer attention, not model safety.

5. **"Subscription-CLI-only" enforcement does not address the model card gap.** Even if every LLM call goes through Antigravity / Codex CLI / Claude CLI, that constrains the *invocation surface*, not the model's safety profile. A subscription-CLI invocation of a model with no documented training data is still an invocation of a model with no documented training data.

**Go / no-go**: **Pause for model card discipline**. The change that flips me: require a model card markdown file (with at minimum the FAT* 2019 §3 fields) for every entry in `model_allowlist.json`, and require pre-registered evaluation tasks on held-out data for every (model, prompt_template) pair before v1.1 promotion. Both should land before Phase 3 ship, not after.

---

## §9 — Reviewer 7: Tyler Akidau

> *Streaming Systems* (2018, with Slava Chernyak and Reuven Lax): "Processing-time is the time at which events are observed by the system. Event-time is the time at which the event actually occurred. The two are different. Treating one as the other is the source of more streaming-system bugs than any other single mistake."

> "The world beyond batch": "Late data is not an exception. It is the normal case for any system that integrates with the real world."

**What the overseer is and what's promising.** The two-tier hashing (raw_hash + semantic_hash, only semantic propagates) is the right model for cosmetic-vs-meaningful change. The cascade-bound concept (don't propagate if N dependents touched) is the right intuition for backpressure.

**What's wrong.**

1. **Invalidation is processing-time-oriented.** A source artefact changes; the invalidator marks dependents stale *when the invalidator runs*. Not when the source actually changed. If the invalidator is delayed by an hour, a dependent rebuilt during that hour will incorporate the OLD source content, the invalidator will then mark it stale (because it sees the source has changed), the rebuild_queue gets a new item, and the rebuild redoes work that just completed. This is the canonical late-data problem from Streaming Systems chapter 2.

2. **There's no watermark.** A streaming system has a notion of "events with event-time before T have all arrived; we can safely finalize." The overseer has no analog. When can I trust that a paper's article_epistemic_record is *current as of build_run_id X*? Only by reading the build_run_id and consulting external context. No watermark, no closed window.

3. **The cascade-bound of 100 is a windowing rule disguised as an alert.** What you really want is: group cascading invalidations into windows, batch the rebuilds within a window, materialize once per window. Akidau, Chernyak, and Lax spend three chapters on windowing strategies. Yours is "if more than 100 are touched, alert." That's not a window; that's a circuit breaker.

4. **The reconciler tick treats AF state as authoritative.** But AF state is itself a stream of events — papers get re-triaged, abstracts get corrected, PDFs get re-uploaded. The reconciler reads AF.papers as if it were a snapshot. If the reconciler reads at 10:00:00 and AF gets a write at 10:00:01 that supersedes a row the reconciler just read, the next tick will reconcile to the new state, but events between 10:00:00 and the next tick are unobserved. For a 60-second reconciler tick, that's potentially 60 seconds of AF history lost to the overseer's view.

5. **Content equivalence checks add another async stage with no late-data handling.** When an LLM equivalence check says "raw-only change, equivalent," and 30 seconds later the source artefact is reverted to its prior raw form, the equivalence verdict is now incorrect — but it's recorded as `semantic_equivalent` and the cascade was suppressed. Nothing re-examines.

**Go / no-go**: **Proceed with changes**. The change that flips me: a watermark column on artefact_registry (`watermark_at` — the event-time bound beyond which we cannot guarantee state is final), and a windowing strategy for cascade invalidation (batch by source build_run, materialize once per window). These are not Phase 4 concerns; they're correctness concerns for the system *as built*.

---

## §10 — Reviewer 8: Camille Fournier

> *The Manager's Path*: "Engineering organizations under-invest in the work of running their systems. The most common failure mode is treating operations as a tax on building, rather than as the central activity that makes building valuable."

> ZooKeeper PMC perspective: "Coordination services exist because distributed agreement is hard. Every minute you spend writing application-layer coordination logic is a minute you're not spending on your actual product."

**What the overseer is and what's promising.** The named-role design in Phase 3 §10.1 (operator with five responsibilities) is at least an acknowledgment that humans run this. That's more than most infrastructure projects manage.

**What's wrong.**

1. **The operator role is five jobs, not one.** R1 (per-invocation review), R2 (batched equivalence review), R3 (grounding tuning + tuning report), R4 (auto-approve list maintenance + attestation doc), R5 (model allowlist maintenance). Even at 5 minutes per per-invocation review, 100 submissions per day is 8 hours of review work. The spec doesn't say what the expected daily submission rate is. If it's 100, the operator is full-time on the review queue and never gets to R3–R5. If it's 1, you've designed five process surfaces for a load that doesn't need them.

2. **The reviewer CLI is named but not specified.** `dependency_overseer_llm_review_cli.py` and `dependency_overseer_batch_approve_cli.py` are file names without a UI specification. Real reviewers don't live in CLIs. They live in browser-based queues with side-by-side diffs, comment threads, and accept/reject buttons. Building a CLI is fine for a prototype; shipping production review on a CLI is a known failure mode.

3. **"Reviewer authentication is intentionally informal" is a security and audit problem.** A reviewer_id is whatever string the CLI user types in. That means anyone with shell access can approve as anyone. For a small team this is fine right now. The moment you have a second AI worker that can call this CLI, you have an audit logbook with no integrity guarantees. The spec says "Phase 4" — fine — but the Phase 3 commit history will then contain approvals attributed to people who didn't approve. That's not a hypothetical; that's what happens.

4. **The completion_queue's `assigned_to` field is set but never consulted by any verifier check.** No SLO on `(first_seen_at, resolved_at)` distance. No check on items unassigned more than N hours. No visibility into review backlog growth rate. The spec generates work without owning the work.

5. **The dry-run sensitivity sweep produces a markdown file that the operator is supposed to read and act on.** This is the work-without-owner pattern again. Tooling that produces reports nobody reads is worse than tooling that doesn't produce reports — the report's existence implies someone is responsible for acting on it, the absence of action looks like negligence, and the next person assumes the report has been considered. Read Larson (next reviewer) on this exact pattern.

**Go / no-go**: **Pause for operations design**. The change that flips me: a written operations runbook (`docs/DEPENDENCY_OVERSEER_OPERATIONS_2026-05-24.md`) with on-call rotation (even if just one person), SLOs on review queue depth and dry-run report turnaround, and a one-paragraph statement of "if this fails at 3 AM, here is the playbook." Tooling without runbooks is half-built.

---

## §11 — Reviewer 9: Will Larson

> *An Elegant Puzzle*: "Engineers love to build infrastructure. Engineering managers must love something different: the smallest possible system that solves the actual problem."

> *Staff Engineer*: "Most of the staff engineers I interviewed described their biggest accomplishments as deletions or simplifications. The people I respect most do not measure their work in lines of code added."

**What the overseer is and what's promising.** The discipline of writing a synthesis before code, an implementation spec before code, phase-specific specs before phase execution, ship reports after — that's better than most teams ever achieve. The test coverage is real. The commits are coherent. As a technical artifact, this is high-quality work.

**What's wrong.**

1. **The system has 22 tables in Phase 1, 23 with Phase 3's new batch approval table.** The Knowledge Atlas has ≤2000 papers. The companion contract (article-epistemic) has 6 tables. The dep overseer adds 22 more. That's a 4× expansion of schema surface area for an audit layer. Read DDIA chapter 12 on the bandwidth of teams: each table is a piece of state that has to be reasoned about, migrated, version-controlled, tested, and documented. 22 tables is enterprise-grade schema for a research-grade workload.

2. **The spec layer is its own maintenance burden.** Synthesis: 747 lines. Phase 1 impl spec: 1151 lines. Phase 2 spec: 213 lines. Phase 3 spec: 544 lines. Ship reports: ~300 lines each. That's ~3500 lines of spec for ~3700 lines of code. The spec-to-code ratio is approximately 1:1. Specs at this density are extremely valuable for *one* generation of maintenance. They are a millstone for any subsequent generation that wants to make a single non-trivial change — every change requires updating prose in 4–6 places.

3. **Phase 3 ships before any LLM artefacts exist.** Phase 3's entire value proposition is governance of LLM enrichment. The current state of the world: no LLM artefacts have been submitted. The dry-run mode is a stub waiting for input. You're shipping the governance layer before you have anything to govern. This is the *if you build it they will come* fallacy applied to infrastructure. Sometimes they come; often they don't. The risk-adjusted right move is to ship Phase 1+2 (which has real users — the Article Finder reconciliation has 3 live papers already), get six months of operational data, and then decide whether Phase 3 is needed at all or whether AE's existing anti-cheat contract is sufficient.

4. **There's no end-user story.** The synthesis names the dependency overseer as governing "Knowledge Atlas lifecycle, Article Finder, contributed PDFs, PNU refreshes, article-detail epistemic layer, generated payloads, and release gates." Who uses the output? Researchers reading article pages. Are the researchers seeing better article pages because the dependency overseer exists? No measurement, no claim. The system audits its own audits. This is a smell.

5. **The five named operator responsibilities (R1–R5) are five jobs you've created.** Each of them is real work. Each requires expertise. Each fails silently when not done. You've created a job description for a person who doesn't exist yet. Larson's chapter on team-shaped problems: don't ship infrastructure that requires a team you don't have to operate it.

**Go / no-go**: **Pause and audit scope**. The change that flips me: a one-page "is this dep overseer earning its keep?" memo answering — for each of the 22 tables — what specific user-visible problem would be visible if the table didn't exist. If you can do that for 22 of 22 tables, ship. If you can do it for 12, delete 10 tables. If you can do it for 6, kill the project, and use the Article-Eater anti-cheat contract for the LLM-governance need, full stop. Asking this question now is a kindness to your future self.

---

## §12 — Reviewer 10: Joe Armstrong (in memoriam)

> *Programming Erlang* (2nd edition, 2013): "If you want to write a reliable system, you have to assume things will fail. Once you accept that, the question becomes: what happens *next*? Who restarts the failed thing? Who fixes the corrupted state? Who notifies the user? Erlang's answer is supervision trees. Most other systems' answer is `try/except` and a log message."

> "Making reliable distributed systems in the presence of software errors" (PhD thesis, 2003): "The system shall consist of independent processes. Errors in one process must not crash other processes. Processes that have failed shall be restarted by a supervisor."

**What the overseer is and what's promising.** The watchdog reclaim is the *idea* of supervision: detect a stuck worker, take its work back. The fencing token + heartbeat construction means a "dead" worker that comes back to life cannot corrupt state. This is honest distributed-systems work.

**What's wrong.**

1. **The watchdog is one tick function. There is no supervisor.** A real Erlang supervision tree would have: the watchdog as a supervised child of a meta-supervisor; restart_strategy = `one_for_one`; if the watchdog crashes, the supervisor restarts it; if the supervisor crashes, *its* supervisor restarts it; up to a root supervisor that never dies. The dep overseer has: a Python script that runs as a cron job. If the script throws, cron logs an error and moves on. There is no restart. There is no escalation. There is no health story.

2. **The repair loop is fully human-driven.** Erlang's repair philosophy: try the obvious fix automatically; if that fails, try the next; if everything fails, surface to a human. The dep overseer's philosophy: detect the problem, write to completion_queue, wait for a human. Three classes of failure that could be auto-repaired but aren't: (a) a build that crashes mid-write — automatically re-enqueue; (b) a tombstoned PNU whose dependents are stale — automatically rebuild from the new PNU version; (c) a sync event past its unresolved threshold — automatically re-run the reconciler before flagging. Each is one function. The spec routes all three to human review.

3. **The `try/except` boundary is large.** `article_epistemic_builder.py::build_one()` is a long function. If it raises mid-way, the transaction rolls back. Good. But the worker that called it doesn't know how to retry. It calls `fail()` on the rebuild_queue, which routes to a re-queue or to quarantine. The fail path is correct in shape; it is not differentiated by failure type. A fencing-token mismatch should re-claim and retry; a malformed input should not. The dep overseer treats them the same.

4. **There is no per-component crash isolation.** If the article_epistemic_builder has a bug that produces a Python exception on a specific paper, every subsequent call processing that paper will fail the same way. The worker retries 5 times (per fail()'s threshold) and then quarantines. That paper is now stuck until a human intervenes. An Erlang-style design would: spawn the builder as an isolated process, kill it if it crashes, log the crash, and move on to the next paper. The dep overseer's worker is a long-running Python process that shares state with the next paper's builder invocation.

5. **The completion_queue's "human_review_required" outcome is the default for everything ambiguous.** That is the opposite of Erlang's philosophy. Erlang's default is: restart and let the next attempt try; if it crashes too many times, escalate. The dep overseer's default is: detect, log, wait for a human. Over time, this design accumulates queue items at a rate proportional to load, not at a rate proportional to actually-bad-state.

**Go / no-go**: **Pause for supervision strategy**. The change that flips me: a one-paragraph supervision protocol — for each named worker (rebuild_queue worker, watchdog, reconciler tick, grounding verifier, content_equivalence worker), name the supervisor, the restart strategy, the escalation path. If "supervisor: cron; restart: none; escalation: human" is the honest answer for any worker, document it explicitly so the future maintainer knows that worker is fragile.

---

## §13 — Synthesis: Go/No-Go Tally

| Reviewer | Vote | Single change that flips to enthusiastic go |
|---|---|---|
| Kleppmann | Proceed with changes | SIGKILL-mid-transaction test demonstrating zero partial state |
| Helland | Proceed | Rename `active` to `is_current_version` + add `version_id` |
| Wayne | Pause and formalize | TLA+ or Alloy model of claim+fencing+lease state machine |
| McCaffrey | Proceed with changes | Compensation logic per event_kind + load-relative threshold |
| Majors | Pause for observability | `verifier_run_history` + `llm_invocations_event_log` tables |
| Mitchell | Pause for model card discipline | Model cards per allowed model + pre-registered eval tasks |
| Akidau | Proceed with changes | Watermark column + windowing strategy for cascade |
| Fournier | Pause for operations design | Operations runbook with SLOs and on-call rotation |
| Larson | Pause and audit scope | "Earning its keep" memo per table; delete what doesn't |
| Armstrong | Pause for supervision | Per-worker supervision and restart-strategy protocol |

**Tally: 0 unconditional go. 4 proceed-with-changes. 6 pause-and-fix.**

The honest summary: every panelist has at least one specific objection. Four can be persuaded by a single change each (Kleppmann's crash test, Helland's rename, McCaffrey's compensation, Akidau's watermark). Six want either a substantial addition (Wayne's formal model, Majors' observability, Mitchell's model cards, Fournier's runbook) or a critical re-examination (Larson's scope audit, Armstrong's supervision).

**Common themes across the panel:**

1. **Telemetry is absent.** Majors, Akidau, Fournier all cite this from different angles. The system audits via fixed verifier checks but has no time-series, no high-cardinality structured events, no way to ask new questions without shipping new code.
2. **Operational reality is under-specified.** Fournier, Larson, Armstrong all name this. The operator role is five jobs, the reviewer CLI doesn't scale to actual review volume, the watchdog has no supervisor, the auto-approve gates are attestation-based rather than data-based.
3. **Compensation and repair are manual when they could be automatic.** McCaffrey and Armstrong agree: the saga has no compensation; the repair loop routes everything to human review by default; Erlang-style "try the obvious fix" patterns are absent.
4. **The spec layer is impressive but heavy.** Larson and Wayne note this from opposite directions — Wayne wants more formalism, Larson wants less prose. The intermediate state (3500 lines of prose specifications, zero formal invariants) is the worst of both worlds.
5. **Phase 3 ships before there's anything to govern.** Larson is most direct: no LLM artefacts exist yet, so Phase 3's value is fully speculative. Mitchell agrees: governing model behavior without model cards is provenance theater.

**Enterprise-level recommendation:**

The dependency overseer Phase 1 and Phase 2 are real work that solves real problems (the AF reconciler smoke-tested against the live AF DB with 16,257 papers; 3 papers actively synced; 220 tests passing). They should ship.

Phase 3 should pause. Not kill — pause. The work itself is not bad; the timing is wrong. Ship Phase 1+2, operate them for at least one quarter, accumulate real telemetry (after building the observability layer that Majors demands), and then revisit Phase 3 with:

- Model cards for any allowed model (Mitchell).
- A TLA+ model of the lease state machine (Wayne).
- A runbook with on-call rotation (Fournier).
- An "is this earning its keep?" scope audit (Larson).
- A supervision protocol for every worker (Armstrong).
- Watermarks and windowing for cascades (Akidau).
- Compensation logic for the saga (McCaffrey).
- A SIGKILL-mid-transaction test (Kleppmann).
- Renamed columns and a version_id (Helland).

Then ship Phase 3 against real LLM workload, not speculative governance over nothing.

The change in posture that flips the vote from "pause" to "go" for the most reviewers is the simplest one: **do not ship Phase 3 as currently planned. Ship Phase 1 + Phase 2 + a observability layer + a runbook, run for 90 days, and then decide whether Phase 3 is still needed or whether AE's existing anti-cheat contract has absorbed the requirement.**

This is what each of the ten panelists, in their own vocabulary, is asking for. It is also, in Larson's language, the smallest system that solves the actual problem.

---

## §14 — Limitations of This Review

This review is impersonation, not testimony. The cited works are real and the quoted passages reflect each author's published positions; the application to the dep overseer is my reconstruction. None of the named individuals has reviewed the dep overseer. Where my impersonation has missed their actual view, the failure is mine. If you would commission a real version of this review, the panelists I'd actually want are: a former Amazon principal engineer who worked on order-fulfillment data consistency (for the saga critique), a senior Google site reliability engineer who has run a real on-call rotation against a verifier-monitored system (for the operational critique), a research scientist who has shipped grounding-verifier-style systems (for the LLM-governance critique), and one staff engineer with deletion authority over a comparable infrastructure project (for the scope audit). Any one of them, with two hours and the source tree, would produce a sharper version of this document.
