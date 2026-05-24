# Dependency Overseer Panel Synthesis

Date: 2026-05-23
Input: `docs/DEPENDENCY_OVERSEER_EXPERT_PANEL_BRIEF_2026-05-23.md`
Companion contract: `docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md`
Handoff: `docs/HANDOFF_DEPENDENCY_OVERSEER_2026-05-23.md`

## Executive Decision

The panel proceeds with the dependency-overseer direction but rejects the brief as a drop-in implementation contract. Six structural changes are required before any schema migration is written.

The replacement implementation principle is:

> The overseer is a **typed artefact registry with hash-pinned support sets**, not a global ETL framework. Every derived artefact in the Atlas must have (a) a stable artefact ID, (b) a typed kind registered in a kind registry, (c) a support set whose members are themselves registered artefacts (not file paths or prose), and (d) a content hash recomputable by code from the support set. Anything that cannot satisfy those four properties is not yet an overseer participant and must be quarantined behind a registration completion item.

The first implementation must be a strict registry-and-freshness gate on the article-epistemic pipeline and its PNU support, with the Article Finder bridge and the LLM-governance layer designed in parallel but built in later phases.

## Reviewer Roster

Six reviewers were simulated, matching the brief:

- **Reviewer A** — Lead Backend Systems Engineer (schema, transactions, migrations)
- **Reviewer B** — Data Pipeline / Workflow Engineer (queues, retries, claims, incremental rebuilds)
- **Reviewer C** — Contract / Schema Specialist (JSON schemas, vocabularies, strict verifiers)
- **Reviewer D** — Large-System / Platform Architect (extensibility, cross-pipeline, Article Finder, monitoring)
- **Reviewer E** — Epistemic / Knowledge-Representation Specialist (claims, warrants, defeaters, belief network)
- **Reviewer F** — LLM Governance / Provenance Specialist (grounding, source packets, review queues, prompt audit)

Each reviewer answers the brief's ten review prompts in order, then returns the brief's nine-section structured verdict. The synthesis pass at the bottom of this document consolidates accepted invariants, rejected suggestions, the final DB schema, the verifier contract, the repair loop, the phased implementation plan, and open risks.

---

## Reviewer A: Lead Backend Systems Engineer

### 10 Review Prompts

1. **What invariant is missing?** Atomicity. Every overseer write must touch at least three tables together (`artefact_registry`, `dependency_edges`, `content_hashes`) and the brief never declares that those writes are one transaction. Without `BEGIN ... COMMIT` discipline a crashed builder will leave dangling edges and ghost hashes.
2. **What state transition is ambiguous?** The transition from `building` to `verified` when the builder process dies mid-write. The brief implies the verifier will catch it later, but the registry will already report the partial artefact as present. Required: a `building` state must be transactionally separate from the `ready` state, and a `building` row older than `lease_expires_at` must be tombstoned, not promoted.
3. **What failure would not be detected?** Time-of-check/time-of-use drift during a long rebuild. A builder reads a support-set member, hashes it, and writes the derived artefact — but the source mutated between read and hash. Brief has no input-fingerprint capture at the claim moment.
4. **What repair loop could corrupt or launder bad data?** A `force_fresh` repair that updates `freshness_status` without recomputing hashes. Also a deterministic rebuild that uses a non-deterministic input order (e.g., directory listing) — the same content produces different hashes, oscillating staleness.
5. **What should block deployment?** Any record whose `payload_hash` does not recompute from its `support_set_hash` plus builder version. Any orphan edge. Any duplicate active record per `(paper_id, schema_version)`.
6. **What can be repaired automatically?** Tombstone-then-rebuild of single records whose support set is fresh. Reclaim of expired-lease queue items. Hash recomputation when only the hashing rule version changed (with explicit hash-rule-version tag).
7. **What must be queued for extraction or human review?** Any record whose support set names a source artefact that is itself missing or `tombstoned_at IS NOT NULL`. Any orphan edge (the source disappeared but the derived artefact still references it).
8. **What is over-engineered?** The brief implies a generic "rebuild queue" that can run anything. For Phase 1 the only rebuild kind needed is `article_epistemic_record`. A second kind table for queue items is unnecessary until Phase 2.
9. **What is under-specified?** Migration sequencing. The brief lists tables but says nothing about how to land them across an already-running pipeline. Required: introduce tables empty, run a shadow build for one week with `release_eligible=false`, then flip the release gate.
10. **What is the smallest implementation that proves the design?** A single PNU change visibly invalidates exactly the article-epistemic records that listed that PNU in their support set, queues rebuilds, executes them, and the verifier confirms `support_set_hash` recomputes — all under one Python entrypoint with a single sqlite DB.

### Verdict

Proceed with changes.

### Missing Invariants

- Every multi-table overseer write is exactly one DB transaction.
- `building` is a transactional state distinct from `ready`; no consumer reads a `building` row.
- `(paper_id, schema_version, active=true)` is a unique constraint at DB level.
- `build_run_id` is globally unique across builder restarts (UUID, not a counter).
- A `tombstoned_at` timestamp is set on supersession; rows are not deleted.
- Input fingerprint captured at claim time matches recomputed fingerprint at write time, or the write is rejected.

### Ambiguous State Transitions

- `queued → claimed`: requires lease + lease_owner; current brief calls it implicit.
- `claimed → building → verified`: needs explicit `building` row separate from `verified` row.
- `verified → fresh`: only after support hashes recompute equal to recorded support hashes.
- `fresh → stale`: triggered by any support-set member hash change, regardless of source pipeline.
- `stale → queued`: must be enqueued by an invalidation tick, not by builders.
- Crashed-mid-build: must tombstone, not promote.

### Failure Modes Not Detected

- Time-of-check/time-of-use drift during long builds.
- Concurrent builders writing the same `(paper_id, schema_version)` row.
- Hash-prefix collisions when ID shortening is used (`sha256[:16]` has practical collision risk only at very large N, but the verifier should still uniqueness-check).
- Rebuild storms that exhaust the queue worker for hours while serving stale content.
- Schema drift across builder versions where the same support set produces different payload hashes.

### Required Schema Changes

- `artefact_registry(artefact_id PRIMARY KEY, kind, entity_type, entity_id, field_path, created_at, tombstoned_at, latest_build_run_id, content_hash, freshness_status, schema_version)`.
- `dependency_edges(parent_artefact_id, child_artefact_id, edge_kind, edge_hash, created_at, tombstoned_at, PRIMARY KEY (parent_artefact_id, child_artefact_id, edge_kind))`.
- `content_hashes(artefact_id, build_run_id, content_hash, input_fingerprint, hashed_at)`.
- `build_runs(build_run_id PRIMARY KEY, builder_name, builder_version, started_at, finished_at, status, input_snapshot_hash, record_count, success_count, failure_count)`.
- Unique partial index `UNIQUE (paper_id, schema_version) WHERE active = 1` on `article_epistemic_records`.
- SQLite must run in WAL mode with `PRAGMA foreign_keys = ON`; Postgres preferred long-term but not required for Phase 1.

### Required Verifier Changes

- Referential integrity: every `dependency_edges` endpoint resolves to a present `artefact_registry` row.
- Active-record uniqueness: no two active records share `(paper_id, schema_version)`.
- Hash recompute equality: for every active derived artefact, `content_hash == recompute(support_set, builder_version)`.
- Build-run idempotency: rerunning a build with the same `input_snapshot_hash` produces the same `content_hash`.
- No `building` row older than `lease_expires_at` may be reachable from a `ready` query.

### Required Repair/Completion Changes

- Tombstone-and-rebuild, not in-place overwrite.
- Repair attempts increment `attempt_count`; threshold (e.g., 5) routes to human review.
- Hashing-rule-version bumps require a controlled re-hash pass, recorded in `build_runs` with a `rehash` builder name.

### Minimum Viable Implementation

A single Python script that:

1. Registers PNU rows and article-epistemic records as artefacts.
2. Captures support sets at claim time.
3. On a PNU hash change, marks dependent records `stale` and enqueues rebuilds.
4. Rebuilds deterministically and re-hashes.
5. A verifier asserts `support_set_hash` recomputes and `(paper_id, schema_version)` uniqueness holds.

### Blocking Concerns

- Without transactional discipline the brief is unsafe at any scale beyond a single worker.
- The brief never names the database engine. SQLite single-writer concurrency is a real constraint; the panel recommends declaring SQLite WAL for Phase 1 and accepting one-writer-at-a-time builds.

---

## Reviewer B: Data Pipeline / Workflow Engineer

### 10 Review Prompts

1. **What invariant is missing?** Lease-and-claim enforcement on the rebuild queue. The brief says "rebuild queues" without naming the semantics. Workers must claim with a lease, lose the lease on expiry, and the server (not the worker) must reclaim.
2. **What state transition is ambiguous?** What happens when a support-set member changes mid-rebuild. Two reasonable answers — (a) abort, (b) finish and queue another — must be picked explicitly, and the brief does not.
3. **What failure would not be detected?** Silent retry exhaustion: a queue item that has retried five times and is now ignored, with no alert. Also "stale forever" — an item that no worker can complete because a source artefact is missing, but nothing routes it to human review.
4. **What repair loop could corrupt or launder bad data?** "Auto-resolve stale rebuilds older than N hours" — laundering. Or a repair worker that runs a different builder version than the canonical one, producing a fresh hash that doesn't match canonical rebuild output.
5. **What should block deployment?** Any queue item in `building` past lease expiry. Any queue depth older than the configured oldest-allowed age. Any worker reporting heartbeat older than the heartbeat threshold while holding a claim.
6. **What can be repaired automatically?** Expired-lease reclaim. Single-record rebuild on a single PNU change. Re-enqueue on transient I/O failure. Re-validation of `content_hash` after a verifier deems it dirty.
7. **What must be queued for extraction or human review?** Repeated rebuild failures past `attempt_count >= threshold`. Cascading-invalidation explosions where one source change touches > `cascade_alert_threshold` derived artefacts (default 100). Rebuilds blocked by a missing upstream source.
8. **What is over-engineered?** Backpressure logic for Phase 1. One worker process with bounded concurrency suffices for 760 articles. Backpressure becomes real at Phase 4 (topics, DYK, search).
9. **What is under-specified?** The cascade model. The brief says "rebuilds for only the affected article epistemic components and payloads" without defining the cascade rule. Required: cascade depth is bounded by the dependency-edge depth from the changed artefact, and batch the leaves rather than process them one at a time.
10. **What is the smallest implementation that proves the design?** Two queue states (queued, done), one lease semantic with 10-minute expiry, one worker, and a verifier that confirms a PNU change invalidates exactly the records listing that PNU and that all enqueued items reach `done` within one heartbeat cycle.

### Verdict

Proceed with changes.

### Missing Invariants

- Claimed queue items are invisible to other workers until release or expiry.
- Lease expiry is enforced by the queue server (or by a watchdog tick), never trusted to workers.
- Each rebuild operates on an input fingerprint captured at claim; if inputs change during the rebuild, the write is rejected and a new rebuild is queued.
- Cascading invalidation depth and breadth are bounded; rebuilds beyond the cascade threshold are batched and an alert is raised.
- A heartbeat older than the heartbeat threshold revokes the claim automatically.

### Ambiguous State Transitions

- `stale → queued → claimed → building → verified → fresh`: every arrow must be explicit; the brief stops at `stale` and `rebuild queues`.
- `building → failed`: what counts as failure (exception? hash mismatch? verifier rejection?) must be enumerated.
- A second invalidation that arrives while a build is in flight: brief is silent; panel choice is "let current build finish, then re-queue with the new fingerprint".
- A queue item with `attempt_count >= threshold` moves to `quarantine`, not silent `done`.

### Failure Modes Not Detected

- Silent retry exhaustion without alerting.
- "Stale forever" because a source is permanently missing.
- A worker that holds a claim past lease expiry but the server still treats it as claimed.
- Cascading rebuild storms that exhaust workers and serve stale to readers.
- A queue table row that was deleted (manually or by buggy cleanup) while the artefact is still stale.

### Required Schema Changes

- `rebuild_queue(queue_id, artefact_id, reason, severity, first_seen_at, last_seen_at, attempt_count, state, lease_owner, lease_expires_at, input_fingerprint_at_claim, last_error)`.
- Index on `(state, lease_expires_at)` for stale-claim reaping.
- Cascade-alert configuration in a single config row.
- `worker_heartbeats(worker_id, last_heartbeat_at, current_claim)`.

### Required Verifier Changes

- Queue-depth verifier: oldest queued item age must be below the configured ceiling.
- "No claim without lease" check.
- "No write to `artefact_registry` from a worker without a corresponding `build_runs` row whose `status=verified`".
- Cascade-bound check: no single invalidation touched more than the threshold without an alert recorded.

### Required Repair/Completion Changes

- Each repair run captures input snapshot at claim; results are written only if the snapshot is still current.
- Repair failure increments `attempt_count`; crossing threshold routes to `quarantine`, not silent retry.
- Cascade explosion guard batches rebuilds at the leaf level rather than processing one at a time.

### Minimum Viable Implementation

`rebuild_queue` with two effective states (queued, done) plus a transient `claimed`; one worker; 10-minute lease; a watchdog tick that reaps expired claims; a verifier that runs after each rebuild and rejects if input fingerprint drifted.

### Blocking Concerns

- Without lease/claim discipline, parallel workers will corrupt state.
- The cascade rule is the single largest source of operational risk; without bounding and batching, a PNU registry hash change can stampede the system.

---

## Reviewer C: Contract / Schema Specialist

### 10 Review Prompts

1. **What invariant is missing?** Every status field has an enum constraint at the DB level (`CHECK` in SQLite, enum type in Postgres), not only code-level. Otherwise schemas drift silently when a new code path emits an unlisted value.
2. **What state transition is ambiguous?** The set `{absent, missing, not_extracted, not_applicable, source_missing}` is six ways to say nothing. The brief mixes them. Required: a single decision tree resolves which value applies.
3. **What failure would not be detected?** Loose JSON: a builder emits a key not in the schema, the verifier passes loose validation, and the consumer ignores the extra key. Strict additional-properties=false is required.
4. **What repair loop could corrupt or launder bad data?** Auto-coercion: a builder writes the string `"true"`, a repair pass coerces to bool true, and the value is silently wrong. Also auto-supplying an `absence_reason` like `"auto_inferred_empty"` to satisfy the verifier.
5. **What should block deployment?** Any schema violation. Any unknown status value. Any empty content without a matching `absence_reason`. Any payload hash that diverges from the DB-derived payload.
6. **What can be repaired automatically?** A schema-version bump that adds nullable fields with documented defaults. A rename of a deprecated status value when the migration script is the only source of the rename.
7. **What must be queued for extraction or human review?** Any vocabulary addition. Any new component type. Any builder that emits a previously-unseen `source_mode`. Any schema_version migration.
8. **What is over-engineered?** Per-component JSON schemas for every component type in Phase 1. One schema per record kind suffices; per-component-type schemas can come in Phase 2.
9. **What is under-specified?** The single canonical vocabulary registry. Status values are listed in prose across the brief and the article-epistemic spec; they need to land in one machine-readable file, e.g. `schemas/status_vocabularies.json`.
10. **What is the smallest implementation that proves the design?** One Pydantic model per record kind; strict mode on; one validator that fails loud on additional properties; one vocabulary file referenced by all writers and verifiers.

### Verdict

Proceed with changes.

### Missing Invariants

- Status enums are enforced at DB level, not only at code level.
- Empty array or empty object is illegal without a paired `absence_reason` drawn from a controlled vocabulary.
- Schema versions are string tags, frozen at release; old records remain valid in their original version.
- A single canonical `schemas/status_vocabularies.json` is the source of truth for every status field across pipelines.
- Backward compatibility rule: schema-version bumps add fields nullable; renames go through a migration with both old and new fields temporarily present.

### Ambiguous State Transitions

- `absent` vs `missing` vs `not_extracted` vs `not_applicable` vs `source_missing` — must collapse to a documented set with a decision tree.
- `freshness_status=unknown` vs `extraction_status=absent`: panel rules `unknown` is only used before first build; `absent` is used after a build finds nothing to extract.
- `render_status=hidden` vs `render_status=block_article`: panel rules `hidden` removes the section; `block_article` prevents the whole article from rendering.
- Empty `components.defeaters[]` with no `absence_reason` is a hard error, not a quiet pass.

### Failure Modes Not Detected

- Schema drift: builder emits a key not in schema, loose JSON validation passes.
- Vocabulary drift: a new code path emits a status value that doesn't appear in the vocabulary file.
- Type coercion silently changes value semantics.
- Payload-DB divergence: payload regenerated stale while the DB row was repaired.
- A component type that has no registered field policies but writes content.

### Required Schema Changes

- `schemas/status_vocabularies.json` as a single source of truth.
- `schemas/component_types.json` listing every component type with its required status enums, render policy default, and field policy.
- A Pydantic model per record kind with strict mode and `extra = "forbid"`.
- An `absence_reasons` enum file shared by every artefact kind.

### Required Verifier Changes

- Strict JSON schema validation: `additionalProperties: false`, all required keys present, all enum values resolve.
- Vocabulary-membership check at write time: every status field value must appear in `schemas/status_vocabularies.json`.
- Absence-reason audit: every empty content field has a non-empty `absence_reason` from the controlled list.
- Payload/DB equality: the JSON payload's `payload_hash` must equal the DB row's `payload_hash`.
- Schema-version sanity: every active record references a known schema version; deprecated versions raise an audit, not a silent failure.

### Required Repair/Completion Changes

- Schema violations route to quarantine, not auto-coercion.
- New vocabulary values land via a migration script, not by silent acceptance.
- Payload/DB divergence triggers a regenerate-from-DB action with a verifier on the regenerated payload.

### Minimum Viable Implementation

One `schemas/status_vocabularies.json`, one `schemas/component_types.json`, one Pydantic model per record kind, one strict validator entrypoint that exits non-zero on any violation.

### Blocking Concerns

- Without strict schemas, anti-cheat invariants leak silently; the contract reduces to prose.
- The status-vocabulary file must land before the first builder writes a row, or the project starts in a polluted state.

---

## Reviewer D: Large-System / Platform Architect

### 10 Review Prompts

1. **What invariant is missing?** Artefact kinds are registered, not hardcoded. Without a kind registry the overseer is implicitly an article-epistemic-layer tool; topics, DYK cards, search index, reports, and PNU registry refreshes will all bypass it.
2. **What state transition is ambiguous?** Article Finder candidate PDF → Atlas paper. At what moment does the lifecycle DB become the canonical owner? The brief lists candidate states but does not name the boundary that transfers ownership.
3. **What failure would not be detected?** A new pipeline writes derived artefacts but never registers them; the overseer reports the system healthy while the new pipeline drifts. Also: Article Finder local DB and lifecycle DB drift on the same paper without any cross-DB reconciler flagging it.
4. **What repair loop could corrupt or launder bad data?** "Reconcile from production" — pulling production state back into staging legitimizes drift instead of fixing it. Also a cross-DB join repair that hides which side was authoritative.
5. **What should block deployment?** Any derived artefact in production whose `kind` is not registered. Any topic page, DYK card, or report referencing a stale article-epistemic record. Any last-mile production probe failure (HTTP non-200, console error, asset 404, payload hash divergence).
6. **What can be repaired automatically?** Single-source-of-truth refreshes from the lifecycle DB to Article Finder local DB. Asset republishing on hash divergence. Page rerender on payload-hash mismatch.
7. **What must be queued for extraction or human review?** Discovery of an unregistered artefact kind. Cross-DB drift where the lifecycle DB and Article Finder disagree on a paper's canonical hash. Production probe failures whose remediation is not in the automatic catalogue.
8. **What is over-engineered?** The brief implies the overseer should cover topics, DYK, search, and reports from day one. Phase 1 should cover the article-epistemic + PNU + abstract dependency only.
9. **What is under-specified?** The Article Finder peer-DB contract. The brief says "formally related local DB" without naming the sync direction, the conflict-resolution rule, or the heartbeat. Required: lifecycle DB is canonical for accepted Atlas papers; Article Finder is canonical for candidate state; the bridge is a typed sync event log.
10. **What is the smallest implementation that proves the design?** One `artefact_kinds` table, one `pipeline_registry` table, registration of three kinds (PNU, article-epistemic-record, article-detail-JSON), and one cross-DB sync verifier that asserts the Article Finder candidate PDF state and the lifecycle DB candidate state agree on every candidate.

### Verdict

Proceed with changes.

### Missing Invariants

- Artefact kinds are registered in `artefact_kinds`, not hardcoded; the overseer rejects writes for unregistered kinds.
- Every pipeline that produces overseer artefacts is registered in `pipeline_registry` with declared inputs and outputs.
- Article Finder is canonical for candidate state; the lifecycle DB is canonical for accepted Atlas paper state; the boundary is the `accept_candidate` event, written to both DBs in one logical transaction (event log on each side, with a reconciler verifying matched event pairs).
- Topics, DYK cards, search index, and reports must register as artefact kinds before they may consume overseer-managed inputs; they do not have to be implemented yet.
- Last-mile production checks are first-class verifier outputs, not after-thoughts.

### Ambiguous State Transitions

- Article Finder candidate → Atlas paper acceptance: must produce one `accept_candidate` event with both sides reflecting it.
- A PNU registry refresh: must produce one `registry_snapshot` event with a registry-level hash and per-row hashes; row-level invalidation cascades from per-row hash changes, not from the registry-level hash alone.
- Atlas paper retirement or merge: must tombstone every derived artefact for that `paper_id` and produce a tombstone event consumed by Article Finder.
- Production rerender vs staging republish: must be distinct events with distinct verifiers.

### Failure Modes Not Detected

- Unregistered-kind drift: a new pipeline writes derived artefacts that never enter the overseer.
- Cross-DB drift on the same paper without a reconciler.
- A topic page or DYK card serving a stale article-epistemic record because topics/DYK aren't in the overseer's freshness model.
- Production probe absence: an article page returns HTTP 200 but `payload_hash` in production differs from staging — no verifier detects it.

### Required Schema Changes

- `artefact_kinds(kind_name PRIMARY KEY, owner_pipeline, support_rule_module, schema_version, active)`.
- `pipeline_registry(pipeline_name PRIMARY KEY, version, declared_outputs, declared_inputs, last_seen_at)`.
- `cross_db_sync_events(event_id PRIMARY KEY, event_kind, lifecycle_payload_hash, article_finder_payload_hash, status, created_at, resolved_at)`.
- `last_mile_production_checks(check_id, artefact_id, check_kind, status, evidence_json, created_at)`.

### Required Verifier Changes

- "No derived artefact in production without `artefact_kinds.active=true`".
- "All declared outputs of all registered pipelines exist as artefacts or have completion-queue entries".
- "Cross-DB sync events have no `status=unresolved` older than the configured threshold".
- "Production payload hash equals release payload hash for every active record" (last-mile).

### Required Repair/Completion Changes

- Unregistered-artefact discovery produces a `register_kind` completion item, not auto-registration.
- Cross-DB drift produces a `reconcile_paper` completion item with explicit winner rule (lifecycle DB wins for accepted-state; Article Finder wins for candidate-state).
- Production-probe failure produces a `republish` action whose verifier runs after republish completes.

### Minimum Viable Implementation

`artefact_kinds` + `pipeline_registry` with three registered kinds (PNU, article-epistemic-record, article-detail-JSON); one Article Finder sync verifier; one last-mile production probe per article page that runs after release.

### Blocking Concerns

- Without `artefact_kinds`, the overseer is implicitly a one-pipeline tool and the brief's "global" claim is unsupported.
- Without an Article Finder peer-DB contract with conflict-resolution rules, bidirectional drift is the default failure mode.

---

## Reviewer E: Epistemic / Knowledge-Representation Specialist

### 10 Review Prompts

1. **What invariant is missing?** Defeater target typing. The brief says defeaters are tracked but never enforces that each defeater has a `target_kind` in {claim, warrant, method, measurement, interpretation, generalizability, mechanism, application}. A generic "defeater" without target silently loses epistemic content.
2. **What state transition is ambiguous?** Canonical-claim-text drift. If `canonical_claim_text` is reformatted by a new normalizer, `claim_id` (derived from sha256 of canonical text) changes. The brief gives no rule for whether that creates a new claim, supersedes the old one, or is forbidden.
3. **What failure would not be detected?** Concept drift hidden behind ID stability: the same `claim_id` survives a tokenizer change but the canonical text no longer reflects the same paper claim. Conversely, an `original_text` change that preserves the canonical claim spawns a new `claim_id`.
4. **What repair loop could corrupt or launder bad data?** Auto-targeting unmapped defeaters by keyword heuristic. Mapping `attack_count > 0` rows to fabricated defeater targets to satisfy the verifier.
5. **What should block deployment?** Any defeater row without a `target_kind`. Any claim_id with more than one active canonical_claim_text in the same active record. Any `belief_network_link` referencing a retired PNU without `freshness_status=stale`.
6. **What can be repaired automatically?** Re-canonicalization that preserves `claim_id` under a versioned normalizer rule. Re-fetching PNU support when a stale flag fires and the upstream PNU hash already exists. Recomputing `support_count` and `attack_count` from the active rows when the count basis is `derived_from_rows`.
7. **What must be queued for extraction or human review?** Unmapped attacks. Claims with `epistemic_status=unknown` after the deterministic rules ran. Belief-network contexts where the PNU upstream returns ambiguous edges. Answer shape `unknown` after rule trace shows no rule fired with confidence.
8. **What is over-engineered?** Full Toulmin reconstruction in Phase 1. The companion contract already defers this; the panel concurs. Phase 1 ships primary claim + claim rows + evidence strength + defeater presence/absence + answer-shape decision; full warrants and qualifiers wait.
9. **What is under-specified?** The `claim_origin` field. Where did the canonical claim text come from? `structured_core_finding`, `top_claims_row`, `article_level_main_conclusion`, `science_summary_core_finding`, or `not_extracted`. The brief sequences the selection but does not require recording which rule fired.
10. **What is the smallest implementation that proves the design?** Tables for `claims` (with claim_id, paper_id, canonical_claim_text, original_text, claim_origin), `defeaters` (with target_kind), `belief_network_links` (with pnu_id, pnu_version_hash). Primary-claim selection rule producing a `claim_origin` value on every active record.

### Verdict

Proceed with changes.

### Missing Invariants

- Every defeater has a non-null `target_kind` in the controlled enum.
- `claim_id` is derived from a versioned canonicalizer and the canonicalizer version is recorded on the row; canonicalizer changes go through a migration that retains old claim IDs as `superseded_by`.
- A claim's `epistemic_status` is owned by the DB row, not synthesized at render time.
- Every belief-network link includes the PNU's version hash at the time of linking.
- Every primary-claim assignment records the rule that fired (the `claim_origin` value).

### Ambiguous State Transitions

- Canonical-claim-text reformatting: must preserve `claim_id` under a versioned normalizer; rewrites that change semantics produce a new `claim_id` with `superseded_by` link.
- `attack_count > 0` with no mapped defeater rows: must mark `absence_reason=attack_count_without_mapped_rows`, not silently pass.
- PNU edge update: invalidates the belief-network context component, not the primary-claim component, unless the edge directly supports the primary claim.
- Answer-shape change between builds: produces a new build_run_id row; `answer_shape_decisions` retains the prior decision with `superseded_at`.

### Failure Modes Not Detected

- Concept drift under stable claim_id.
- Orphan warrants (no claim references them but the warrant row stays).
- Belief-network context listing a retired PNU.
- Evidence strength silently upgraded by a future LLM pass that bypasses the field-policy guard.

### Required Schema Changes

- `claims(claim_id PRIMARY KEY, paper_id, canonical_claim_text, canonicalizer_version, original_text, claim_scope, claim_type, claim_polarity, assertion_status, epistemic_status, claim_origin, superseded_by, created_at, tombstoned_at)`.
- `warrants` and `warrant_claim_edges` with edge_kind in {supports, undercuts, rebuts, qualifies}; deferred to Phase 2.
- `defeaters(defeater_id, claim_id, target_kind, content_json, support_set_id, created_at, tombstoned_at)`.
- `belief_network_links(record_id, claim_id, pnu_id, pnu_version_hash, edge_kind, created_at, tombstoned_at)`.
- `answer_shape_decisions(record_id, shape, rule_id, rule_version, rule_trace_json, created_at, superseded_at)`.

### Required Verifier Changes

- "Every defeater has a non-null `target_kind`."
- "Every `claim_id` resolves to one and only one canonical_claim_text in the active record."
- "No belief_network_link references a tombstoned PNU without `freshness_status=stale`."
- "Answer shape `unknown` is allowed only when `rule_trace_json` shows no rule fired with confidence."
- "Every active record records a `claim_origin` for its primary claim."

### Required Repair/Completion Changes

- Unmapped defeater rows route to `human_review_required`, not auto-target inference.
- Canonicalizer-version bump goes through a migration that retains claim IDs.
- Belief-network stale items refresh from the upstream PNU registry rather than synthesize.

### Minimum Viable Implementation

`claims` + `defeaters` + `belief_network_links` + `answer_shape_decisions`. Primary-claim selection rule emits `claim_origin`. `attack_count_without_mapped_rows` absence reason is supported. No warrants, no qualifiers, no Toulmin reconstruction in Phase 1.

### Blocking Concerns

- Without target-typed defeaters the system silently degrades to "some attacks somewhere".
- Without canonicalizer-version recording, claim history is unrecoverable across reword passes.

---

## Reviewer F: LLM Governance / Provenance Specialist

### 10 Review Prompts

1. **What invariant is missing?** Source-packet pinning at the hash level. Every LLM call must declare its source packet (the exact list of source artefact IDs allowed as grounding) and hash it; if either the packet members or any member's hash changes, the LLM output is stale.
2. **What state transition is ambiguous?** A `human_approved` LLM artefact whose source packet later changes. Brief is silent; panel rules: it becomes `stale` and routes back to review, retaining the approval as historical evidence on the tombstoned row.
3. **What failure would not be detected?** A grounding score that is high but cites the wrong fields (semantic grounding without field-pinned grounding). Also a prompt-template update that did not bump `prompt_version`, so old hash collisions look valid.
4. **What repair loop could corrupt or launder bad data?** "Auto-re-prompt on grounding failure" without manifest pinning — the rerun may ground to different sources than the original request, producing a plausible answer that satisfies the verifier but answers a slightly different question.
5. **What should block deployment?** Any LLM artefact whose `worker_surface` is not in `{antigravity_subscription, codex_cli_subscription, claude_cli_subscription, google_ai_api}`. Any LLM artefact missing model name, prompt template hash, source packet hash, or output hash. Any LLM artefact writing to a forbidden field. Any LLM artefact in production with `review_status` outside `{machine_verified, human_approved}`.
6. **What can be repaired automatically?** Re-prompt with refreshed source packet when the only change is a member's content hash. Re-grounding when the grounding rule version bumped. Tombstone-and-re-issue when the prompt template version bumped.
7. **What must be queued for extraction or human review?** Grounding failures. New prompt template versions. New model name. Any LLM artefact targeting a previously-unseen component type. Any LLM artefact whose review threshold is configured to require human approval.
8. **What is over-engineered?** A general prompt-template registry with versioning, hashing, and approval workflow in Phase 1. Phase 1 should ship the contract and a single dummy template; the real templates land with Stage 2.
9. **What is under-specified?** The forbidden-fields enforcement layer. The companion contract lists fields LLMs may not generate; the brief doesn't say where the enforcement happens. Required: at write time in the artefact_registry insert path, not only at design time in code review.
10. **What is the smallest implementation that proves the design?** Tables for `llm_invocations`, `prompt_templates`, `source_packets`. One dummy prompt template. One grounding verifier. One field-policy enforcement check at write time. No LLM artefacts in production until Stage 2.

### Verdict

Proceed with changes.

### Missing Invariants

- Every LLM call records: model_name, prompt_template_id, prompt_template_hash, source_packet_id, source_packet_hash, input_hash, output_hash, grounding_verdict, reviewer_id (nullable), review_decision, worker_surface, created_at.
- Source packet members are typed artefact IDs from `artefact_registry`, not free-form prose.
- Forbidden-field enforcement happens at write time; the artefact_registry insert path checks the field policy for the target field and rejects LLM writes to `extracted_only`, `deterministic_only`, or `human_only` policies.
- Subscription-CLI-only enforcement: `worker_surface` for any LLM artefact must be in the allowed set; direct provider SDK calls are rejected at write time.
- An LLM artefact whose source packet member hash changes goes `stale` automatically.

### Ambiguous State Transitions

- `human_approved` LLM artefact whose source packet changes: stale, route to review, retain the approval on the tombstoned row.
- `machine_checked` → `rejected`: artefact is tombstoned but the `llm_invocations` row is retained for audit.
- `unreviewed` LLM artefact: never serves in production; render layer hides it.
- A grounding failure with high semantic-similarity score but wrong field targeting: the verifier marks `grounding_verdict=field_pinned_failure`, not `grounding_verdict=pass`.

### Failure Modes Not Detected

- Field-pinned grounding bypassed by semantic-only similarity.
- Prompt-template content changed without `prompt_version` bump.
- Direct SDK call slipping in via a non-CLI script.
- Bulk approval of stale LLM artefacts during a review-queue clear.

### Required Schema Changes

- `llm_invocations(invocation_id PRIMARY KEY, artefact_id, model_name, prompt_template_id, prompt_template_hash, source_packet_id, source_packet_hash, input_hash, output_hash, grounding_verdict, reviewer_id, review_decision, worker_surface, created_at)`.
- `prompt_templates(prompt_template_id, prompt_version, prompt_template_hash, allowed_field_policies, created_at, active)`.
- `source_packets(source_packet_id PRIMARY KEY, members_json, source_packet_hash, created_at)` — members reference artefact_registry rows.
- A foreign key from every LLM-produced artefact to an `llm_invocations` row.

### Required Verifier Changes

- "Every LLM artefact in production has a paired `llm_invocations` row with `grounding_verdict=pass` and `review_decision in (machine_approved, human_approved)`."
- "No `llm_invocations` row has `worker_surface` outside the allowed set."
- "Field-policy enforcement: no LLM artefact targets a field whose policy is not in `prompt_templates.allowed_field_policies`."
- "Source packet members all resolve to active `artefact_registry` rows; if any member is tombstoned, the LLM artefact is stale."

### Required Repair/Completion Changes

- Failed grounding routes to a completion queue with the source packet for human review.
- Stale source packet triggers a re-prompt with refreshed packet, producing a new `invocation_id`.
- Rejected LLM output is tombstoned but retained for audit (referenced by `invocation_id`).

### Minimum Viable Implementation

`llm_invocations` + `prompt_templates` + `source_packets` tables; one dummy prompt template; one grounding verifier; field-policy enforcement at write time; no production LLM artefacts in Phase 1.

### Blocking Concerns

- Without source-packet manifests with hash pins, LLM grounding is decorative.
- Without write-time enforcement of forbidden fields, the SDK-bypass risk is large and silent.

---

## Synthesis Pass

The synthesis consolidates the six reviewers into one accepted contract.

### 1. Accepted Invariants

Combined with the brief's original twelve, the panel accepts the following invariants. The numbering is fresh; brief invariants are tagged `B#`, panel additions are tagged `P#`. Items marked `(revised post-panel)` or `(added post-panel)` reflect targeted refinements made after the synthesis closed but before the implementation spec begins; they address mechanism-level questions that the original consolidation left implicit (in particular, the meaning of "stuck" and the lease/atomicity boundary).

**Carried from brief:**

- B1. No derived artefact is current merely because it exists.
- B2. A derived artefact is current only if every required support hash matches the hash used when it was computed.
- B3. Every derived artefact has a support set.
- B4. Every support-set entry names a registered artefact, not a file path or prose.
- B5. Every content-producing pipeline writes to the lifecycle DB before deployable JSON is generated.
- B6. Every verification failure triggers repair, completion, honest missing-state marking, or a blocking report.
- B7. Missing source content must not be invented to satisfy a verifier.
- B8. LLM-generated content is labelled as synthesis, never as extracted fact.
- B9. LLM use records model, prompt ID, prompt hash, input hash, output hash, source fields, and review status.
- B10. Candidate/contributed PDFs are tracked before they become accepted Atlas articles.
- B11. Article Finder's local DB owns operational candidate state; the lifecycle DB owns canonical audit state.
- B12. A release does not promote with stale required artefacts, payload-DB divergence, or last-mile production failure.

**Added by the panel:**

- P1. Every multi-table overseer write is one DB transaction.
- P2. `building` is a transactional state distinct from `ready`; consumers do not read `building` rows.
- P3. `(paper_id, schema_version)` is unique among active rows of any record kind.
- P4. `build_run_id` is globally unique (UUID); reruns produce new IDs.
- P5. `tombstoned_at` supersedes deletion; rows are retained for audit.
- P6. Input fingerprint is captured at claim time and revalidated at write time; mismatches reject the write.
- P7 (revised post-panel). A claim holds as long as the worker's last heartbeat is younger than the heartbeat timeout. The watchdog reclaims only after the heartbeat stream goes silent for the full timeout window, not on a wall-clock lease expiry. Heartbeat interval and heartbeat timeout are distinct numbers (e.g., interval 30 s, timeout 5 min) so that network jitter, GC pauses, and long but normal builds do not cause false eviction. "Stuck" means "no longer heartbeating," not "taking longer than expected"; a mid-transaction worker that keeps heartbeating retains its claim.
- P8. Cascading invalidation depth and breadth are bounded; rebuilds beyond the cascade threshold are batched and an alert is recorded.
- P9. Status enums are enforced at DB level via `CHECK` (SQLite) or enum type (Postgres), and against `schemas/status_vocabularies.json`.
- P10. Empty content is illegal without a paired `absence_reason` drawn from a controlled vocabulary.
- P11. Schema versions are string tags frozen at release; old records remain valid in their original version.
- P12. Artefact kinds are registered in `artefact_kinds`; the overseer rejects writes for unregistered kinds.
- P13. Pipelines that produce overseer artefacts are registered in `pipeline_registry` with declared inputs and outputs.
- P14. Article Finder ↔ lifecycle DB sync events appear in `cross_db_sync_events`; canonical-ownership rules: Article Finder owns candidate state, lifecycle DB owns accepted-paper state.
- P15. Last-mile production checks (HTTP 200, asset 200, no console error, payload-hash equality) are first-class verifier outputs.
- P16. Every defeater has a non-null `target_kind`.
- P17. `claim_id` is derived from a versioned canonicalizer; canonicalizer-version changes go through migration with `superseded_by`.
- P18. Every primary-claim assignment records the `claim_origin` rule that fired.
- P19. Every belief-network link records the PNU version hash at the time of linking.
- P20. Every LLM call records the full invocation provenance (model, template, packet, input, output, grounding verdict, review decision, worker surface).
- P21. Forbidden-field enforcement happens at write time in the artefact_registry insert path.
- P22. Subscription-CLI-only enforcement: LLM `worker_surface` values are restricted to the allowed set; direct provider SDK calls are rejected at write time.
- P23. Source-packet hash pinning: an LLM artefact whose source-packet member hash changes becomes stale automatically.
- P24 (added post-panel). Every claim increments a monotonic `fencing_token` recorded on the queue row and on the target `artefact_registry` row. Every write to `artefact_registry` carries the claim's fencing token; writes whose token is less than the artefact's `current_fencing_token` are rejected at the DB layer. This closes the residual race where a temporarily-slow worker wakes up and tries to commit after the watchdog has already started a replacement, and removes the atomicity invariant's dependence on clock synchronization. With P7 and P24 in place there is no atomicity-vs-lease conflict: lease loss is defined precisely (no heartbeat), and fencing tokens protect writes even in the corner case where a worker resumes after being declared dead.
- P25 (added post-panel, Phase 2). Heartbeats carry a progress marker — current task, current phase, last-processed input hash. Identical markers for N consecutive intervals route the worker to soft-stuck review, distinguishing "process alive, work thread wedged" from "process gone." Phase 1 ships liveness-only detection (P7); progress-stuck detection lands in Phase 2 because the progress-marker plumbing on the worker side is more invasive than liveness-only heartbeats.
- P26 (added post-panel, second synthesis). Vocabularies split into two kinds. *Closed enums* (freshness_status, severity, queue state, defeater target_kind, worker_surface, grounding_verdict, review_decision, claim_origin, edge_kind, event_kind, check_kind, answer_shape) reflect the overseer's own state machine; they are fixed at design time, enforced as DB `CHECK` constraints, and changes go through migration. *Open vocabularies* (method names, measure names, instrument and psych-test names, construct labels, abstract source labels) reflect the empirical world the system describes; they are managed in a new `vocabulary_registry` table that accepts new values on first sight with provenance, is seeded from canonical libraries (PsychoPy at Phase 1 ship; NIH CDE and related later), and supports asynchronous canonicalization — deterministic matching in Phase 1, LLM-aided canonicalization in Phase 3 under the LLM-governance contract. `schemas/status_vocabularies.json` governs only the closed set.
- P27 (added post-panel, second synthesis). Every derived artefact carries two hashes: `raw_hash` over the whole content and `semantic_hash` over a normalized form. Only `semantic_hash` changes propagate invalidation. A raw-only change is recorded in `content_hashes` (history retains both hashes per build_run) but does not enqueue rebuilds. Phase 1 implements deterministic normalization only — whitespace, key ordering, documented case-insensitive fields, documented order-insensitive lists — pinned by a `normalization_rule_version`. Phase 3 adds an LLM-adjudicated `content_equivalence_checks` stage for borderline cases, governed by the LLM-provenance contract (P20–P23). The cascade-bound alert from P8 fires on `semantic_hash` changes only. Phase 1's safe default is "cascade when in doubt": anything outside the documented normalization rules counts as semantic and propagates.
- P28 (added post-panel, second synthesis). Phase 1 tables split into *active* (migration lands them and the Phase 1 builder writes rows) and *scaffold-only* (migration lands them with shape but no rows are written until the gating phase activates them). The split is fixed at Phase 1 ship so that foreign keys, verifier code paths, and migration ordering land once. Active in Phase 1 (17): `artefact_registry`, `dependency_edges`, `content_hashes`, `support_sets`, `support_set_members`, `build_runs`, `rebuild_queue`, `worker_heartbeats`, `artefact_kinds`, `pipeline_registry`, `vocabulary_registry`, `claims`, `defeaters`, `belief_network_links`, `answer_shape_decisions`, `completion_queue`, `last_mile_production_checks`. Scaffold-only in Phase 1 (5): `cross_db_sync_events` (Phase 2), `llm_invocations` (Phase 3), `prompt_templates` (Phase 3), `source_packets` (Phase 3), `content_equivalence_checks` (Phase 3).

### 2. Rejected Suggestions, with Reasons

The following ideas surfaced during review but the panel declines them in Phase 1.

- **R1. Per-component JSON schemas for every component type.** Reason: one schema per record kind suffices in Phase 1. Per-component schemas land in Phase 2 once the component-type set is stable.
- **R2. Backpressure logic for the rebuild queue.** Reason: at 760 articles and one worker, queue depth is bounded. Backpressure becomes real at Phase 4 (topics, DYK, search index, reports).
- **R3. Full Toulmin reconstruction (warrants, qualifiers, backing).** Reason: deferred per the companion contract. Phase 1 ships primary claim + claim rows + evidence strength + defeater presence/absence + answer-shape decision.
- **R4. Auto-targeting unmapped defeaters by keyword heuristic.** Reason: laundering of epistemic content. Unmapped defeaters route to human review.
- **R5. Auto-resolve stale rebuilds older than N hours.** Reason: laundering. Long-running stale items must reach human review or quarantine.
- **R6. "Reconcile from production" repair.** Reason: legitimizes drift. Reconcile direction is staging → production (canonical lifecycle DB → published asset), never the reverse.
- **R7. Auto-coerce schema violations.** Reason: silently changes semantics. Violations route to quarantine.
- **R8. Generic LLM "re-prompt on failure" without manifest pinning.** Reason: may ground to different sources than the original request. Every re-prompt produces a new invocation with explicit source-packet pinning.
- **R9. Postgres in Phase 1.** Reason: existing Atlas operates on SQLite; the panel accepts SQLite WAL for Phase 1 with one writer at a time. Postgres is the Phase 4 candidate when concurrent writers become necessary.
- **R10. Direct provider SDK calls from any overseer-touching script.** Reason: bypasses subscription-CLI contract. Rejected at write time.

### 3. Final DB Schema

The Phase 1 lifecycle DB extends the article-epistemic schema with the following overseer tables. SQLite WAL is the engine of record; types are SQLite-native (TEXT, INTEGER, REAL); enums are enforced via `CHECK` constraints whose value lists derive from `schemas/status_vocabularies.json`.

Per P28, the tables below are partitioned into *active* and *scaffold-only* in Phase 1. Active tables receive writes from the Phase 1 builder; scaffold-only tables land empty and are activated in Phase 2 or Phase 3. Each table heading below indicates its Phase 1 status. Per P26, closed-enum fields (severity, state, target_kind, etc.) use `CHECK` constraints derived from `schemas/status_vocabularies.json`; open-vocab fields (method names, measure names, instrument names, construct labels, abstract source labels) reference `vocabulary_registry` rows by value rather than constraining the column. Per P27, every derived artefact carries both `raw_hash` and `semantic_hash`; only `semantic_hash` propagates invalidation.

**Core overseer tables:**

- *Active (Phase 1).* `artefact_registry(artefact_id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, field_path TEXT, schema_version TEXT NOT NULL, latest_build_run_id TEXT, raw_hash TEXT, semantic_hash TEXT, current_fencing_token INTEGER NOT NULL DEFAULT 0, freshness_status TEXT CHECK(freshness_status IN ('fresh','stale','unknown','building')), created_at TEXT NOT NULL, tombstoned_at TEXT, active INTEGER NOT NULL DEFAULT 1, UNIQUE(entity_type, entity_id, field_path, schema_version) WHERE active = 1)`. Writes to this table must satisfy a `WHERE current_fencing_token = :worker_token` clause; the `worker_token` is the fencing token assigned to the queue row when the claim was made. The token is also updated on the artefact row at successful write time so subsequent writes from the same worker continue to validate.
- `dependency_edges(parent_artefact_id TEXT NOT NULL, child_artefact_id TEXT NOT NULL, edge_kind TEXT NOT NULL CHECK(edge_kind IN ('supports','derived_from','depends_on','grounds')), edge_hash TEXT NOT NULL, created_at TEXT NOT NULL, tombstoned_at TEXT, PRIMARY KEY (parent_artefact_id, child_artefact_id, edge_kind), FOREIGN KEY (parent_artefact_id) REFERENCES artefact_registry(artefact_id), FOREIGN KEY (child_artefact_id) REFERENCES artefact_registry(artefact_id))`.
- *Active (Phase 1).* `content_hashes(artefact_id TEXT NOT NULL, build_run_id TEXT NOT NULL, raw_hash TEXT NOT NULL, semantic_hash TEXT NOT NULL, normalization_rule_version TEXT NOT NULL, input_fingerprint TEXT NOT NULL, hashed_at TEXT NOT NULL, PRIMARY KEY (artefact_id, build_run_id), FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id))`. Retains the full hash history per build_run, so a raw-only change (same `semantic_hash`, new `raw_hash`) is recorded but does not enqueue rebuilds. A query against this table answers "did anything cosmetic change since build_run X" and "did anything semantic change since build_run X" independently.
- `support_sets(support_set_id TEXT PRIMARY KEY, support_set_hash TEXT NOT NULL, members_json TEXT NOT NULL, created_at TEXT NOT NULL)`.
- `support_set_members(support_set_id TEXT NOT NULL, member_artefact_id TEXT NOT NULL, member_hash_at_capture TEXT NOT NULL, PRIMARY KEY (support_set_id, member_artefact_id), FOREIGN KEY (support_set_id) REFERENCES support_sets(support_set_id), FOREIGN KEY (member_artefact_id) REFERENCES artefact_registry(artefact_id))`.
- `build_runs(build_run_id TEXT PRIMARY KEY, builder_name TEXT NOT NULL, builder_version TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL CHECK(status IN ('running','verified','failed','aborted','rehash')), input_snapshot_hash TEXT, record_count INTEGER, success_count INTEGER, failure_count INTEGER, report_json TEXT)`.

**Queue and worker tables:**

- `rebuild_queue(queue_id TEXT PRIMARY KEY, artefact_id TEXT NOT NULL, reason TEXT, severity TEXT NOT NULL CHECK(severity IN ('low','medium','high','blocking')), first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL CHECK(state IN ('queued','claimed','building','done','failed','quarantine')), lease_owner TEXT, fencing_token INTEGER NOT NULL DEFAULT 0, claimed_at TEXT, input_fingerprint_at_claim TEXT, last_error TEXT, FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id))`. Note the absence of `lease_expires_at`: lease validity is derived from `worker_heartbeats.last_heartbeat_at` together with `heartbeat_timeout_seconds`, not from a wall-clock expiry timestamp. A claim is valid iff `now() - last_heartbeat_at <= heartbeat_timeout_seconds`; if no heartbeat has yet been received, `now() - claimed_at <= heartbeat_timeout_seconds` is used as a bootstrap window.
- `worker_heartbeats(worker_id TEXT PRIMARY KEY, last_heartbeat_at TEXT NOT NULL, current_claim TEXT, heartbeat_interval_seconds INTEGER NOT NULL, heartbeat_timeout_seconds INTEGER NOT NULL, progress_marker TEXT, progress_marker_unchanged_since TEXT)`. The watchdog reclaims a claim only when `now() - last_heartbeat_at > heartbeat_timeout_seconds`. The `progress_marker` and `progress_marker_unchanged_since` columns may be populated by Phase 1 workers but are only acted on (soft-stuck routing per P25) in Phase 2.

**Registry and pipeline tables:**

- *Active (Phase 1).* `artefact_kinds(kind_name TEXT PRIMARY KEY, owner_pipeline TEXT NOT NULL, support_rule_module TEXT NOT NULL, schema_version TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)`.
- *Active (Phase 1).* `pipeline_registry(pipeline_name TEXT PRIMARY KEY, version TEXT NOT NULL, declared_outputs_json TEXT NOT NULL, declared_inputs_json TEXT NOT NULL, last_seen_at TEXT)`.
- *Active (Phase 1).* `vocabulary_registry(value_id TEXT PRIMARY KEY, kind TEXT NOT NULL, value TEXT NOT NULL, canonical_value TEXT, first_seen_in_paper TEXT, first_observed_at TEXT NOT NULL, first_observed_build_run_id TEXT, review_status TEXT NOT NULL CHECK(review_status IN ('candidate','canonical','synonym','rejected')), canonicalization_source TEXT, seeded_from TEXT, UNIQUE(kind, value))`. Seeded at Phase 1 ship from canonical libraries — PsychoPy first, then NIH CDE and related sources marked `review_status='canonical'` with `seeded_from` recording the library and version. New paper-introduced values land with `review_status='candidate'` and provenance fields populated (`first_seen_in_paper`, `first_observed_build_run_id`). A periodic normalization job links candidates to canonicals (deterministic match in Phase 1; LLM-aided via `content_equivalence_checks` in Phase 3) and updates the row to `review_status='synonym'` with `canonical_value` pointing at the canonical row of the same kind.

**Epistemic detail tables (Phase 1 subset):**

- `claims(claim_id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, canonical_claim_text TEXT NOT NULL, canonicalizer_version TEXT NOT NULL, original_text TEXT, claim_scope TEXT, claim_type TEXT, claim_polarity TEXT, assertion_status TEXT, epistemic_status TEXT, claim_origin TEXT NOT NULL CHECK(claim_origin IN ('structured_core_finding','top_claims_row','article_level_main_conclusion','science_summary_core_finding','not_extracted')), superseded_by TEXT, created_at TEXT NOT NULL, tombstoned_at TEXT)`.
- `defeaters(defeater_id TEXT PRIMARY KEY, claim_id TEXT NOT NULL, target_kind TEXT NOT NULL CHECK(target_kind IN ('claim','warrant','method','measurement','interpretation','generalizability','mechanism','application')), content_json TEXT NOT NULL, support_set_id TEXT, created_at TEXT NOT NULL, tombstoned_at TEXT, FOREIGN KEY (claim_id) REFERENCES claims(claim_id))`.
- `belief_network_links(record_id TEXT NOT NULL, claim_id TEXT NOT NULL, pnu_id TEXT NOT NULL, pnu_version_hash TEXT NOT NULL, edge_kind TEXT NOT NULL, created_at TEXT NOT NULL, tombstoned_at TEXT, PRIMARY KEY (record_id, claim_id, pnu_id, edge_kind))`.
- `answer_shape_decisions(record_id TEXT NOT NULL, shape TEXT NOT NULL CHECK(shape IN ('toulmin','field_map','comparison','mechanism','review_synthesis','mixed','unknown')), rule_id TEXT NOT NULL, rule_version TEXT NOT NULL, rule_trace_json TEXT, created_at TEXT NOT NULL, superseded_at TEXT, PRIMARY KEY (record_id, created_at))`.

**Cross-DB and last-mile tables:**

- *Scaffold-only (Phase 1; activated Phase 2).* `cross_db_sync_events(event_id TEXT PRIMARY KEY, event_kind TEXT NOT NULL CHECK(event_kind IN ('accept_candidate','registry_snapshot','tombstone_paper','reconcile_paper')), lifecycle_payload_hash TEXT, article_finder_payload_hash TEXT, status TEXT NOT NULL CHECK(status IN ('pending','matched','unresolved','reconciled')), created_at TEXT NOT NULL, resolved_at TEXT)`.
- *Active (Phase 1).* `last_mile_production_checks(check_id TEXT PRIMARY KEY, artefact_id TEXT NOT NULL, check_kind TEXT NOT NULL CHECK(check_kind IN ('http_200','asset_200','no_console_error','payload_hash_equal','mobile_layout','provenance_visible')), status TEXT NOT NULL CHECK(status IN ('pass','fail','skipped')), evidence_json TEXT, created_at TEXT NOT NULL, FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id))`.

**LLM governance tables (scaffold-only in Phase 1; activated Phase 3):**

- *Scaffold-only.* `llm_invocations(invocation_id TEXT PRIMARY KEY, artefact_id TEXT NOT NULL, model_name TEXT NOT NULL, prompt_template_id TEXT NOT NULL, prompt_template_hash TEXT NOT NULL, source_packet_id TEXT NOT NULL, source_packet_hash TEXT NOT NULL, input_hash TEXT NOT NULL, output_hash TEXT NOT NULL, grounding_verdict TEXT CHECK(grounding_verdict IN ('pass','field_pinned_failure','semantic_failure','not_run')), reviewer_id TEXT, review_decision TEXT CHECK(review_decision IN ('machine_approved','human_approved','rejected','pending')), worker_surface TEXT NOT NULL CHECK(worker_surface IN ('antigravity_subscription','codex_cli_subscription','claude_cli_subscription','google_ai_api')), created_at TEXT NOT NULL, FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id))`.
- *Scaffold-only.* `prompt_templates(prompt_template_id TEXT PRIMARY KEY, prompt_version TEXT NOT NULL, prompt_template_hash TEXT NOT NULL, allowed_field_policies_json TEXT NOT NULL, created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)`.
- *Scaffold-only.* `source_packets(source_packet_id TEXT PRIMARY KEY, members_json TEXT NOT NULL, source_packet_hash TEXT NOT NULL, created_at TEXT NOT NULL)`.
- *Scaffold-only.* `content_equivalence_checks(check_id TEXT PRIMARY KEY, artefact_id TEXT NOT NULL, prior_raw_hash TEXT NOT NULL, new_raw_hash TEXT NOT NULL, prior_semantic_hash TEXT NOT NULL, new_semantic_hash TEXT NOT NULL, equivalence_verdict TEXT NOT NULL CHECK(equivalence_verdict IN ('semantic_equivalent','semantic_distinct','unresolved')), llm_invocation_id TEXT, normalization_rule_version TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY (artefact_id) REFERENCES artefact_registry(artefact_id), FOREIGN KEY (llm_invocation_id) REFERENCES llm_invocations(invocation_id))`. When `equivalence_verdict='semantic_equivalent'` the cascade does not propagate and the artefact's `semantic_hash` is updated to the new value via a metadata-only write; when `'semantic_distinct'`, the cascade proceeds normally; `'unresolved'` routes the artefact to human review. When `equivalence_verdict='semantic_equivalent'` the cascade does not propagate and the artefact's `semantic_hash` is updated to the new value via a metadata-only write; when `'semantic_distinct'`, the cascade proceeds normally; `'unresolved'` routes the artefact to human review.

**Completion-queue table** (the article-epistemic spec's `article_epistemic_completion_queue` generalizes to the overseer):

- `completion_queue(queue_id TEXT PRIMARY KEY, artefact_id TEXT, paper_id TEXT, component_type TEXT, reason TEXT NOT NULL, severity TEXT NOT NULL CHECK(severity IN ('low','medium','high','blocking')), first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, attempt_count INTEGER NOT NULL DEFAULT 0, next_action TEXT, status TEXT NOT NULL CHECK(status IN ('open','in_review','resolved','waived')), assigned_to TEXT, resolved_at TEXT)`.

**Status vocabularies** are external to the DB: `schemas/status_vocabularies.json`, `schemas/component_types.json`, `schemas/absence_reasons.json`, `schemas/artefact_kinds.json`. The schema migration writes those files into version control before any DB changes.

### 4. Final Verifier Contract

The overseer ships two verifier entrypoints. Each must exit non-zero on any failure and emit a structured JSON report consumed by the release gate.

**Data verifier** — `python3 scripts/verify_dependency_overseer_contract.py --strict`:

- Referential integrity across `artefact_registry`, `dependency_edges`, `content_hashes`, `support_sets`, `support_set_members`, `build_runs`.
- Active-record uniqueness per `(entity_type, entity_id, field_path, schema_version)`.
- Hash recompute equality: both `raw_hash == recompute_raw(support_set, builder_version)` and `semantic_hash == recompute_semantic(raw_hash, normalization_rule_version)` hold for every active derived artefact.
- Semantic-hash propagation: a `rebuild_queue` row exists for an artefact only if its `semantic_hash` changed; raw-only changes (same `semantic_hash`, new `raw_hash`) appear in `content_hashes` history but produced no queue rows.
- Normalization-rule pinning: every `content_hashes` row records a `normalization_rule_version`; bumping the rule version requires a controlled re-hash pass recorded in `build_runs` with `builder_name='rehash_normalization'`, and the verifier rejects mixed rule versions in the active set.
- Build-run idempotency: rerunning a build with the same `input_snapshot_hash` and the same `normalization_rule_version` produces the same `raw_hash` and `semantic_hash`.
- Status-enum membership: every closed-enum field value matches `schemas/status_vocabularies.json`.
- Open-vocabulary coverage: every open-vocab value (method, measure, instrument/psych-test, construct, abstract-source label) referenced by an active artefact resolves to a `vocabulary_registry` row of the matching `kind`; new values are accepted on first sight but must have a non-null `first_observed_at` and `first_observed_build_run_id`.
- Vocabulary canonicalization integrity: every `vocabulary_registry` row with `review_status='synonym'` has a non-null `canonical_value` pointing at a row of the same `kind` with `review_status='canonical'`; no synonym chains longer than depth one (a synonym's canonical_value must itself be canonical).
- Absence-reason audit: every empty content has a non-empty `absence_reason` in the controlled list.
- Payload/DB equality: the JSON payload's `payload_hash` matches the DB row.
- Kind registration: every active artefact's `kind` resolves in `artefact_kinds`.
- Pipeline registration: every declared output of every registered pipeline appears as a registered artefact or has a `completion_queue` entry.
- Queue invariants: no claim whose owning worker's `last_heartbeat_at` is older than its `heartbeat_timeout_seconds` reachable from a `ready` query; every `claimed` or `building` row has a non-null `lease_owner` and `fencing_token`; oldest queued item age below configured ceiling.
- Fencing-token monotonicity: for every artefact, the sequence of fencing tokens assigned to its successive queue rows is strictly increasing; `artefact_registry.current_fencing_token` equals the token of the most recent successful write or claim, whichever is later; no two queue rows for the same artefact share a fencing token.
- Cascade-bound: no single invalidation event touched more than the cascade threshold without an alert in `completion_queue`.
- Defeater target-typing: every active defeater has a non-null `target_kind`.
- Claim canonicalization: every `claim_id` resolves to one and only one canonical text in the active record.
- Belief-network freshness: no link references a tombstoned PNU without `freshness_status=stale`.
- Answer-shape rule trace: every active `answer_shape_decisions` row has a non-empty `rule_trace_json` when `shape=unknown`.
- LLM provenance: every LLM artefact has a paired `llm_invocations` row with `worker_surface` in the allowed set, `grounding_verdict=pass`, and `review_decision in (machine_approved, human_approved)`.
- LLM field policy: no LLM artefact targets a field whose policy is not in `prompt_templates.allowed_field_policies`.
- Cross-DB sync: no `cross_db_sync_events` row with `status=unresolved` older than the configured threshold.

**Rendered verifier** — `python3 scripts/verify_dependency_overseer_render_contract.py --strict`:

- Article page renders the epistemic section.
- Primary claim visible.
- Evidence strength or missing-state explanation visible.
- Defeater section distinguishes missing from none.
- Provenance badges visible without hover.
- Stale and missing states render as warnings.
- No horizontal overflow at mobile fixture widths.
- No console errors.
- No failed network requests for required assets.
- Production payload hash matches release payload hash for every active record.

### 5. Final Repair Loop

The repair loop is one state machine, executed by a single watchdog tick plus on-demand verifier failure routing:

```text
verify
  ├── all_pass            → release_gate_allows
  ├── stale_detected      → enqueue rebuild (rebuild_queue) → claim → build → re-verify
  ├── missing_source      → enqueue completion_queue (severity=blocking) → block release
  ├── orphan_edge         → tombstone edge + enqueue completion_queue (severity=medium)
  ├── schema_violation    → tombstone artefact + enqueue completion_queue (severity=high)
  ├── grounding_failure   → tombstone LLM artefact + enqueue completion_queue (severity=high)
  ├── cross_db_drift      → enqueue cross_db_sync_events (status=unresolved) + reconcile workflow
  ├── last_mile_failure   → enqueue completion_queue (severity=blocking) + republish or block
  └── threshold_exceeded  → move queue row to quarantine + alert
```

Each repair action records a `verification_events` row with `repair_actions_json`. No repair action writes to the artefact registry directly; the rebuild path is `tombstone-then-build-then-verify`, never overwrite.

Promotion is blocked while any blocking completion-queue item is open, any stale required artefact remains, any payload-DB hash divergence is unresolved, or any last-mile production check is failing.

### 6. Phased Implementation Plan

The plan retains the brief's four phases and refines them with the accepted invariants and rejected suggestions above.

**Phase 0 — panel review and contract writing.** Complete with this synthesis. The next deliverable is a single implementation spec document derived from this synthesis: `docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md`. That spec restates accepted invariants, the final DB schema, the verifier contract, the repair loop, and the test plan in implementation-ready form. It is the work item for the next session.

**Phase 1 — minimum viable overseer over PNU and article-epistemic.**

- Land `schemas/status_vocabularies.json`, `schemas/component_types.json`, `schemas/absence_reasons.json`, `schemas/artefact_kinds.json` in git. These govern only closed enums per P26.
- Migrate the lifecycle DB to include the active and scaffold-only overseer tables listed in §3, per the P28 split.
- Seed `vocabulary_registry` from PsychoPy (and any other chosen canonical libraries) with `review_status='canonical'` and `seeded_from` populated, before any builder writes rows.
- Implement deterministic normalization rule v1 (whitespace, key ordering, documented case-insensitive fields, documented order-insensitive lists) with explicit `normalization_rule_version='v1'` pinning on every `content_hashes` write.
- Register three artefact kinds: `pnu_row`, `article_epistemic_record`, `article_detail_json`.
- Register the `article_epistemic_builder` pipeline.
- Implement the Stage 1 article-epistemic builder per the companion spec (deterministic only); the builder computes both `raw_hash` and `semantic_hash` and writes both via P27.
- Implement `verify_dependency_overseer_contract.py --strict`.
- Implement a single-worker rebuild queue with WAL-safe lease semantics (heartbeat-based, fencing-token-protected per P7/P24).
- Prove the round-trip: change one PNU row → exact set of dependent article-epistemic records goes stale on `semantic_hash` change → rebuilds enqueued → builder runs → verifier passes → payload-hash recomputes. Separately prove the negative case: a whitespace-only reformat of a PNU row produces a new `raw_hash` but the same `semantic_hash`, no rebuild is enqueued, and the cosmetic change is visible in `content_hashes` history.

**Phase 2 — Article Finder bridge, abstract handling, candidate PDF lifecycle.**

- Register `article_finder_candidate`, `abstract`, `pdf_artifact`, `ocr_artifact` as artefact kinds.
- Implement `cross_db_sync_events` reconciler.
- Implement abstract-source provenance per the companion contract's allowed sources.
- Wire the candidate PDF state machine (`metadata_only → abstract_only → candidate_pdf_unverified → pdf_verified → ocr_ready → extracted`).
- Add the Article Finder peer-DB sync verifier.
- Add progress-marker heartbeats and soft-stuck routing per P25, complementing the liveness-only detection shipped in Phase 1.

**Phase 3 — LLM enrichment governance.**

- Activate the LLM governance tables (`llm_invocations`, `prompt_templates`, `source_packets`); schema was landed in Phase 1 as scaffold per P28.
- Implement field-policy enforcement at the artefact_registry insert path.
- Implement the grounding verifier with field-pinned (not semantic-only) grounding.
- Implement the human-review queue with explicit reviewer ID, decision, and visible labels in the rendered layer.
- Pilot Stage 2 enrichment on one component type (backing prose), behind a release flag.
- Activate `content_equivalence_checks`: implement the LLM-adjudicated semantic-equivalence stage for borderline `raw_hash` changes that deterministic normalization rule v1 could not classify. Each check produces a paired `llm_invocations` row and feeds back into the cascade decision per P27.
- Implement LLM-aided canonicalization of `vocabulary_registry` candidates: an LLM-adjudicated step that links new paper-introduced method, measure, instrument, and construct names to canonical entries (or proposes new canonical entries), with the same source-packet pinning and review queue as other Stage 2 enrichment.

**Phase 4 — extend the overseer to topics, DYK cards, search index, reports, and release dashboards.**

- Register each as artefact kinds with declared inputs/outputs.
- Add backpressure logic to the rebuild queue.
- Consider Postgres migration when concurrent writers become operationally necessary.
- Add monitoring dashboards backed by `build_runs`, `rebuild_queue`, `completion_queue`, and `last_mile_production_checks`.

**Test plan (carried into Phase 1):**

- `tests/test_overseer_schema.py` — table presence, enum constraints, foreign keys.
- `tests/test_overseer_artefact_registry.py` — registration, kind validation, active-record uniqueness.
- `tests/test_overseer_support_sets.py` — hash recompute, member resolution, stale on member change.
- `tests/test_overseer_dependency_edges.py` — edge creation, tombstoning, no orphan endpoints.
- `tests/test_overseer_rebuild_queue.py` — lease semantics, expiry reclaim, input fingerprint at claim/write.
- `tests/test_overseer_invalidation.py` — PNU change invalidates exact set of dependent artefacts.
- `tests/test_overseer_cascade_bound.py` — cascade threshold detection and batching.
- `tests/test_overseer_completion_queue.py` — failure routing and quarantine.
- `tests/test_overseer_data_verifier.py` — every check in the verifier contract.
- `tests/test_overseer_release_gate.py` — promotion blocked under each failure class.
- `tests/test_overseer_render_contract.py` — rendered-page checks for the article-epistemic surface.

### 7. Open Risks

- **OR1. Cascade storms on PNU registry refresh.** A single registry-level hash change must not invalidate every dependent record. P27 sharpens the panel position: only `semantic_hash` changes propagate; raw-only changes (whitespace, ordering, documented case-insensitive reformatting) do not. Phase 1's deterministic normalization rule v1 catches the common formatting cases; Phase 3's `content_equivalence_checks` adjudicates borderline edits. The residual storm risk is that a tokenizer or canonicalizer change updates `semantic_hash` for many rows at once even when authors did not intend a semantic change; this is mitigated by the normalization-rule-version pinning rule (rule-version bumps go through a controlled re-hash pass, not in-place rewrites). The cascade-bound verifier catches violations of the per-row vs registry-level distinction.
- **OR2. SQLite single-writer concurrency.** Phase 1 accepts one writer at a time on WAL mode. The next pipeline that needs concurrent overseer writes (likely Phase 4 search index refresh) will force Postgres or a write-serializer queue. Decision deferred to the start of Phase 4.
- **OR3. Article Finder ownership boundary.** The `accept_candidate` event must succeed on both sides or neither, but the two databases are physically separate. The panel accepts dual-side event logs with a reconciler; an open question is whether the reconciler runs synchronously at the accept event or asynchronously. Defer to Phase 2 implementation.
- **OR4. Canonicalizer-version migration.** Bumping the canonicalizer creates new claim IDs unless explicitly preserved. The panel rules preservation via `superseded_by`. The risk is that a future canonicalizer change wants to actually split or merge claims, in which case `superseded_by` is the wrong model. Revisit if a real canonicalizer change requires semantic splits.
- **OR5. LLM grounding verifier accuracy.** Field-pinned grounding is hard to implement well. A grounding verifier that under-rejects produces hallucinations in production; one that over-rejects starves the review queue. The panel accepts an initial conservative threshold and a manual override path; tune in Phase 3.
- **OR9. Semantic-equivalence false positives.** The Phase 3 `content_equivalence_checks` stage adjudicates whether a `raw_hash` change is semantically equivalent. A false positive (LLM rules "equivalent" when the meaning actually drifted) launders content change into the system silently and is the most dangerous failure mode the LLM layer introduces. Mitigations: (a) every `content_equivalence_checks` row is paired with `llm_invocations` provenance and is reviewable; (b) the verdict `'unresolved'` is preferred over `'semantic_equivalent'` whenever the LLM's confidence is below threshold; (c) the verifier emits a human-review item when the fraction of `'semantic_equivalent'` verdicts on a given artefact kind in a build window exceeds an alerting threshold (indicates either a tokenizer change or LLM over-permissiveness). The conservative default until Phase 3 ship is that the `content_equivalence_checks` stage is opt-in per artefact kind.
- **OR10. Open-vocabulary coverage gaps.** The `vocabulary_registry` accepts new values on first sight, which is the intended adaptive behavior but means a typo or OCR error can land as a `'candidate'` row. Mitigations: (a) the normalization job (deterministic in Phase 1, LLM-aided in Phase 3) periodically links candidates to canonicals; (b) the rendered layer must distinguish `'candidate'` from `'canonical'` so consumers know the value is pending review; (c) a verifier alerts when the candidate-to-canonical ratio for any open-vocab kind exceeds threshold (suggests systematic ingestion drift).
- **OR6. Last-mile production probe fragility.** Production probe flakiness (transient HTTP failures, asset CDN hiccups) could block legitimate promotions. The panel accepts a retry-then-quarantine policy with a per-check retry budget; tune at Phase 1 ship.
- **OR7. Schema-version churn.** Frequent schema-version bumps fragment the audit history. The panel accepts a quarterly cadence cap on schema bumps unless an invariant violation forces an emergency bump.
- **OR8. Overseer becoming a single-point-of-failure.** Every pipeline now depends on the overseer DB being available and consistent. The panel accepts that single-DB risk in Phase 1 because the lifecycle DB already plays that role; nightly backups per the existing `scripts/backup_databases.py` policy must be extended to cover the new overseer tables before Phase 1 ships.

---

## Closeout

The panel completes its review with this synthesis. A second synthesis pass on 2026-05-23 folded in mechanism-level resolutions for four follow-up tensions raised after the initial close: lease semantics and atomicity (P7 revised, P24, P25), open vs closed vocabularies (P26), semantic-vs-raw cascade hashing (P27), and active-vs-scaffold table split (P28).

The next deliverable is the implementation spec document derived from this synthesis: `docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md`. No DB migrations, no builder code, and no verifier code may land before that spec is written and reviewed.

The synthesis records the accepted invariants (B1–B12, P1–P28), the rejected suggestions (R1–R10), the final DB schema (17 active + 5 scaffold tables, per P28), the verifier contract, the repair loop, the phased plan, the test plan, and the open risks (OR1–OR10). Together with the article-epistemic contract and the handoff, these documents constitute the contract for the dependency overseer.
