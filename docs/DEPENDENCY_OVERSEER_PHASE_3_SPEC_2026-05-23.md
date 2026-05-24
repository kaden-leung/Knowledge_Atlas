# Dependency Overseer Phase 3 Implementation Spec

Date: 2026-05-23
Status: Phase 3 implementation contract — LLM enrichment governance
Depends on:
- `docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md` (P20–P23, OR9)
- `docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md` (Phase 1)
- `docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md` (Phase 2)
- `docs/SPRINT_OVERSEER_PHASE_1_COMPLETION_2026-05-23.md`
- `docs/SPRINT_OVERSEER_PHASE_2_COMPLETION_2026-05-23.md`
- **Pre-existing LLM contract** (cross-referenced for binding rules):
  `/Users/davidusa/REPOS/Article_Eater_PostQuinean_v1_recovery/docs/SUBSCRIPTION_LLM_ORCHESTRATION_AND_ANTI_CHEAT_CONTRACT_2026-05-21.md`

Phase 3 activates the four LLM-governance scaffold tables landed in Phase 1 (`llm_invocations`, `prompt_templates`, `source_packets`, `content_equivalence_checks`) and adds enforcement: every LLM artefact in production must carry full provenance, must be field-pinned grounded, must come through a subscription-CLI worker surface, and must pass the field-policy check at the artefact_registry insert path. The most dangerous failure mode is **semantic-equivalence false positives** (OR9) — Phase 3 is conservative by design.

## 1. Scope

In scope for Phase 3:

- Activate the four LLM-governance scaffold tables (`llm_invocations`, `prompt_templates`, `source_packets`, `content_equivalence_checks`).
- Field-policy enforcement at the artefact_registry insert path (a write to a field whose `field_policy` is `extracted_only`/`deterministic_only`/`human_only` from an LLM-marked source is rejected at write time).
- Source-packet contract: every LLM invocation declares a typed manifest of allowed source artefact IDs (referenced from `support_set_members`); the source packet is hashed and pinned.
- Prompt-template registry: every prompt has a version, a template hash, and a list of `allowed_field_policies`. Template content changes require a new version row.
- Grounding verifier: every LLM-generated artefact must pass a **field-pinned** grounding check. Semantic similarity is NOT sufficient. Each generated sentence (or claim) must trace back to a specific field-path in a source packet member.
- Subscription-CLI-only enforcement: every `llm_invocations` row's `worker_surface` must be in the allowed set; direct provider SDK calls are rejected at write time.
- Human review queue: every Stage 2 LLM artefact starts at `review_status='pending'`; only a human reviewer (recorded with reviewer ID) can promote it to `human_approved`. Production serves only `human_approved` LLM artefacts (Phase 3 default) or `machine_approved` artefacts whose component_type is on an explicit auto-approve list (Phase 3 default: empty).
- Content equivalence checks: LLM-adjudicated semantic-vs-cosmetic decisions for borderline `raw_hash` changes. Conservative default verdict is `unresolved` when LLM confidence is below threshold.
- LLM-aided vocabulary canonicalization: the LLM proposes mappings from candidate vocabulary entries to canonical entries; mappings land at `review_status='candidate'` on the synonym row and require human approval to flip to `synonym`.
- New verifier checks: `llm_provenance`, `llm_field_policy`, `grounding_verdict_strict`, `content_equivalence_review_status`, `llm_artefact_in_production_review_status`.

Out of scope for Phase 3:

- Adding new LLM-eligible component types beyond `backing_prose` (the Phase 3 pilot). New types land in Phase 4 once the Phase 3 pilot is operationally proven.
- Full backfill of historical content equivalence decisions over the existing corpus.
- Automated re-prompting on grounding failure (Phase 3 ships the grounding verifier; re-prompt policy is configured later).
- Workflow UI for human review (Phase 3 ships the DB-level review queue; UI is a separate track).
- Topics, DYK cards, search-index, reports (Phase 4).

## 2. Pre-existing LLM Contract Alignment + Caller Architecture

The Article Eater repo already carries a substantial LLM anti-cheat contract: `SUBSCRIPTION_LLM_ORCHESTRATION_AND_ANTI_CHEAT_CONTRACT_2026-05-21.md`. Phase 3 of the overseer aligns with that contract rather than reinventing. Specifically:

- Allowed worker surfaces (from synthesis P22 and the existing contract): `antigravity_subscription`, `codex_cli_subscription`, `claude_cli_subscription`, `google_ai_api`. The overseer's `llm_invocations.worker_surface` CHECK constraint already enforces this enum.
- The existing contract has 12 last-mile success conditions (SC-SLO-1 through SC-SLO-12). Phase 3 maps every overseer verifier check that involves LLM artefacts to one or more SC-SLO conditions, so the two contracts compose cleanly.
- Job-packet / result-artefact orchestration is owned by the Article Eater side; the overseer side records provenance and enforces field-policy. The reconciler between the two systems (analogous to the AF reconciler in Phase 2) is a Phase 4 task.

### 2.1 LLM Caller Architecture (binding)

**Article Eater is the LLM orchestrator. The overseer never calls an LLM directly.** This is the single most important architectural decision in Phase 3, and the spec makes it explicit.

Flow for a Stage 2 LLM enrichment:

1. The overseer publishes a job packet to Article Eater's job inbox (or AE pulls from a queue) naming: the target artefact_id, the component_type to enrich, the source_packet_id (manifest of allowed grounding sources), the prompt_template_id, and the expected output schema.
2. Article Eater dispatches the job to a subscription-CLI worker (Antigravity / Codex CLI / Claude CLI per the AE orchestration contract).
3. The worker produces a result JSON artefact at AE's designated `output_path` per SUBSCRIPTION_LLM_ORCHESTRATION SC-SLO-2.
4. Article Eater's controller validates the result (schema, hashes, provenance) per SC-SLO-3 through SC-SLO-6.
5. AE submits the validated result to the overseer via `overseer/llm_submission.py::accept_submission(conn, result_json)`.
6. The overseer runs:
   - field-policy enforcement at the artefact_registry insert path (§6);
   - grounding verifier (§8);
   - records an `llm_invocations` row;
   - leaves `review_decision='pending'` unless the component_type is on the auto-approve list (§7).

The overseer does NOT itself spawn worker processes, call provider SDKs, or write to AE's filesystem. The `worker_surface` value on every `llm_invocations` row reflects what AE recorded; the overseer enforces the value is in the allowed enum but trusts AE for the actual surface used.

This decision keeps responsibilities clean: AE owns orchestration; the overseer owns provenance, verification, and release-gate enforcement.

## 3. Source Packet Contract

A source packet is a typed, hash-pinned manifest of source artefacts an LLM invocation is allowed to ground on. Every `llm_invocations` row references a `source_packets.source_packet_id`.

`source_packets` schema (already landed as scaffold in Phase 1):

```
source_packet_id      TEXT PRIMARY KEY
members_json          TEXT NOT NULL  -- canonical JSON array of {artefact_id, member_hash}
source_packet_hash    TEXT NOT NULL  -- SHA-256 over members_json
created_at            TEXT NOT NULL
```

Phase 3 enforces:

- Every `members_json` entry references an active `artefact_registry` row at write time.
- `source_packet_hash` is recomputed by the verifier; mismatches are blocking.
- If any member artefact is later tombstoned, the dependent LLM invocations are flagged stale; the grounding verifier will refuse to promote the LLM artefact.

`source_packets.capture()` is a new helper (`overseer/source_packets.py`) that:
- Validates every member artefact_id resolves in artefact_registry and is active.
- Computes the canonical members_json (sorted by artefact_id).
- Inserts (idempotent on `source_packet_id` derived from members).

## 4. Prompt Template Registry

`prompt_templates` schema (already landed):

```
prompt_template_id            TEXT PRIMARY KEY
prompt_version                TEXT NOT NULL
prompt_template_hash          TEXT NOT NULL
allowed_field_policies_json   TEXT NOT NULL  -- e.g., ["llm_enrichable"]
created_at                    TEXT NOT NULL
active                        INTEGER NOT NULL DEFAULT 1
```

Phase 3 enforces:

- Every active prompt template's `prompt_template_hash` recomputes from the template's stored content. Template content changes require a new `(prompt_template_id, prompt_version)` row; the old row is deactivated, not edited in place.
- `allowed_field_policies_json` is a JSON array of `field_policy` values the prompt is permitted to produce content for. The write-time field-policy check (§6) reads this.
- The Phase 3 pilot ships **one** active prompt template: `backing_prose_v1`. Allowed field policies: `["llm_enrichable"]`. Other templates are registered as inactive scaffolds for future activation.

Template content itself lives in `contracts/prompts/dependency_overseer/<template_id>_v<version>.md` (new directory). The hash is SHA-256 over the markdown content bytes.

## 5. LLM Invocation Contract

`llm_invocations` schema (already landed):

Every Stage 2 LLM call produces exactly one `llm_invocations` row at write time. Required field combinations enforced by the verifier:

- `artefact_id` must resolve in `artefact_registry`.
- `model_name` must be in the allowed set (config-driven; recommended initial set: `claude-opus-4-7-1m`, `claude-sonnet-4-6`, `gpt-5.2-codex`, `gemini-3.1-pro-high`).
- `prompt_template_id` + `prompt_template_hash` must resolve in `prompt_templates` with matching hash AND `active=1`.
- `source_packet_id` + `source_packet_hash` must resolve in `source_packets` with matching hash.
- `worker_surface` must be in the CHECK-enforced enum.
- `grounding_verdict` defaults to `not_run`; can flip to `pass`, `field_pinned_failure`, or `semantic_failure`.
- `review_decision` defaults to `pending`; can flip to `machine_approved`, `human_approved`, or `rejected`.

`overseer/llm_invocations.py` exposes:
- `record(conn, artefact_id, model_name, prompt_template_id, source_packet_id, input_hash, output_hash, worker_surface) -> invocation_id`
- `set_grounding_verdict(conn, invocation_id, verdict)`
- `set_review_decision(conn, invocation_id, reviewer_id, decision)`
- `get(conn, invocation_id)`

## 6. Field-Policy Enforcement at Write Time

The artefact_registry insert/update path gains a `source_mode` hint and a check against the component_type's `field_policy`:

- `source_mode` values per `schemas/status_vocabularies.json`: `extracted`, `deterministic_derived`, `llm_generated`, `human_entered`, `missing`.
- For each component-type field, `component_types.json` declares `default_field_policy` (one of `extracted_only`, `deterministic_only`, `llm_enrichable`, `human_only`).
- Write-time check: if `source_mode='llm_generated'` and `field_policy != 'llm_enrichable'`, the write is rejected with `FieldPolicyViolation`.

`overseer/artefact_registry.py::update_with_hashes()` gains an optional `source_mode` parameter (default `deterministic_derived`). The Stage 2 LLM-enrichment write path passes `source_mode='llm_generated'`.

A new module `overseer/field_policy.py` exposes:
- `enforce_at_write(conn, *, component_type, field_path, source_mode) -> None` (raises `FieldPolicyViolation`)
- `lookup_field_policy(component_type, field_path) -> str`
- Loads from `component_types.json` (Phase 1 contract).

## 7. Human Review Queue

Phase 3 makes the existing `completion_queue` carry human-review items in a new shape: `next_action='llm_review_required'` plus an `assigned_to` reviewer ID. The review-decision flow:

1. LLM invocation produces an `llm_invocations` row with `review_decision='pending'`.
2. The artefact is **not** marked `freshness_status='fresh'` until a human reviewer approves it OR an auto-approve list explicitly permits machine-only approval for that component_type.
3. A reviewer calls `set_review_decision(conn, invocation_id, reviewer_id, 'human_approved' | 'rejected')`.
4. On `human_approved`, the artefact's freshness flips to `fresh` (in a Phase 3 transaction that also updates the lifecycle DB record).
5. On `rejected`, the LLM artefact is tombstoned but the `llm_invocations` row is retained for audit.

Auto-approve list lives in `contracts/schemas/dependency_overseer/llm_auto_approve.json`. **Phase 3 v1 ships this file empty (every Stage 2 LLM artefact requires human approval).** A Phase 3 v1.1 follow-up adds a component-type pilot to the auto-approve list: candidate is `provenance_summary` (mechanical, low-novelty content where the LLM mostly stitches existing artefact fields together). The v1.1 promotion requires:

- ≥ 50 human-approved invocations of the candidate component_type with `grounding_verdict='pass'` and zero `human_rejected`.
- A reviewer attestation in `docs/SPRINT_OVERSEER_PHASE_3_V1_1_AUTO_APPROVE_DECISION_<DATE>.md` naming the reviewer cohort and the candidate's empirical safety profile.
- A reversible config: removing a kind from the auto-approve list reverts every subsequently-written artefact to `review_decision='pending'` immediately.

The Phase 3 v1.1 promotion is tracked as OVERSEER-LLM-AUTO-APPROVE-v1.1 in TASKS.md.

## 8. Grounding Verifier (Field-Pinned)

This is the centerpiece of Phase 3 and the strongest defense against OR9 (semantic-equivalence false positives).

`overseer/grounding_verifier.py::verify_grounding(conn, invocation_id, *, threshold=0.9) -> GroundingReport` runs:

1. Load the LLM output artefact's content.
2. Load every member of the source packet (artefact_id + member_hash).
3. For each generated unit (sentence or claim, depending on component_type):
   - Find at least one source-packet member whose content contains a quoted span or a structurally-pinned value supporting the unit.
   - "Structurally-pinned" means: a specific JSON path within a source artefact (e.g., `claims[0].canonical_claim_text`) that contains text overlapping the unit by at least 50% of the unit's tokens.
4. Compute the fraction of units that are field-pinned.
5. If fraction >= `threshold` (default 0.9), verdict is `pass`. Else verdict is `field_pinned_failure`.

If the verdict is `pass`, no further action; the LLM artefact remains at `review_decision='pending'` awaiting human review.

If the verdict is `field_pinned_failure`, the LLM artefact is tombstoned and a `completion_queue` row with severity `high` is raised: `llm_grounding_failed:<invocation_id>`.

**Conservative defaults that mitigate OR9**:

- Semantic similarity alone (cosine over embeddings, etc.) is NOT permitted. Grounding requires structural field-pinning.
- Default threshold = 0.9 (90% of units field-pinned). Tunable per component_type via `component_types.json` extension.

**Bounded re-prompt on grounding failure** (added per Phase 3 review):

A failed grounding does NOT immediately tombstone the artefact. Instead:

1. The overseer raises a `regrounding_requested` event referencing the original `invocation_id`.
2. Article Eater picks up the regrounding request and dispatches a single retry with:
   - the same prompt_template_id and source_packet_id,
   - a fresh `invocation_id`,
   - a marker indicating "retry of <prior_invocation_id>".
3. The retry's output MUST produce a different `output_hash` than the prior failed run (verified by the overseer at submission). An identical `output_hash` is treated as evidence the LLM cannot ground this packet and proceeds to the no-retry path below.
4. If the retry also fails grounding (`grounding_verdict` != `pass`), THEN tombstone the artefact and raise a `completion_queue` row with severity `high`.

Retry cap: **1**. No second retry. This caps risk (one flaky run does not force a human into the loop; a persistent failure still routes to review) and stays consistent with the conservative-default theme of Phase 3.

The retry path is implemented in `overseer/grounding_verifier.py::request_regrounding(conn, invocation_id) -> bool`. The companion submission path checks `prior_invocation_id` and rejects a third attempt for the same artefact in a short window.

### 8.1 Dry-run protocol for the first 20 submissions (added per Phase 3 review)

The grounding thresholds (0.9 pass, 0.5 token overlap, sentence-level granularity) are guesses tuned to the conservative side; the real values depend on the prose style of the active prompt template (`backing_prose_v1`). To avoid shipping with mis-tuned thresholds, Phase 3 ships with a **dry-run mode for the first 20 Article-Eater-submitted artefacts** of each new component_type.

In dry-run mode:

1. AE submits the artefact normally.
2. The grounding verifier runs as configured AND produces an extended report including:
   - per-unit field-pinning decisions (which sentence linked to which source path, with token-overlap percentage),
   - the overall pass/fail verdict at the configured threshold,
   - what the verdict would be at thresholds 0.85, 0.90, 0.95 (sensitivity sweep).
3. The verdict is recorded as `dry_run_pass` or `dry_run_fail` in `llm_invocations.grounding_verdict`. The artefact is NOT promoted to fresh; freshness stays at `unknown` and a completion_queue row routes the artefact to a human for review of both the LLM output and the grounding decision.
4. After 20 dry-run submissions, the spec author writes a tuning report (`docs/SPRINT_OVERSEER_PHASE_3_GROUNDING_TUNING_<DATE>.md`) recommending threshold adjustments. The grounding verifier flips to live mode via a config-file change.

Dry-run mode is per-component-type and per-template (e.g., flipping `backing_prose_v1` to live mode does not auto-flip a future `defeater_explanation_v1`). The toggle lives in `contracts/schemas/dependency_overseer/grounding_mode.json`:

```json
{
  "version": "v1",
  "modes": {
    "backing_prose_v1": "dry_run"
  },
  "dry_run_sample_size": 20
}
```

When the sample-size threshold is hit and the mode is still `dry_run`, the verifier raises a `completion_queue` row reminding the operator to write the tuning report and flip the mode.

## 9. Content Equivalence Checks (Semantic-vs-Cosmetic)

`content_equivalence_checks` is activated. When the cascade-bound rule (synthesis P8 / P27) would fire because `raw_hash` changed but `semantic_hash` cannot determine the change is purely cosmetic via Phase 1's deterministic normalization, an LLM equivalence check is queued.

Flow:
1. The invalidator (Phase 1) sees `raw_hash` changed but cannot rule it cosmetic.
2. Instead of cascading immediately, the invalidator enqueues a `content_equivalence_checks` row with `equivalence_verdict='unresolved'`.
3. An LLM worker picks up the row, fetches both versions, produces an `equivalence_verdict` of `semantic_equivalent` or `semantic_distinct`.
4. The check pairs with an `llm_invocations` row.
5. Conservative thresholds: if LLM confidence < 0.8, the verdict stays `unresolved` and the row routes to human review.
6. If verdict is `semantic_equivalent`, the artefact's `semantic_hash` is updated to the new value via a metadata-only write (no cascade).
7. If verdict is `semantic_distinct`, normal cascade proceeds.

**OR9 mitigation specifics**:

- `verify_strict()` adds a check: `_check_content_equivalence_review_status` flags any active `content_equivalence_checks` row with `equivalence_verdict='semantic_equivalent'` whose paired `llm_invocations.review_decision != 'human_approved'` AND is not covered by a batched-approval row (see below).
- A second check: `_check_semantic_equivalent_rate` flags artefact kinds whose `semantic_equivalent` rate per build window exceeds a threshold (default 30%). Indicates either tokenizer-change-induced false positives or LLM over-permissiveness.

**Batched approval** (added per Phase 3 review):

A reviewer can approve a *class* of equivalence checks with one decision rather than per-row. This is the right mode when an upstream change (tokenizer upgrade, normalizer-rule bump, sweeping reformat) produces a large batch of raw-only changes that the LLM uniformly classifies `semantic_equivalent`.

New table:

```sql
CREATE TABLE content_equivalence_batch_approvals (
    batch_id              TEXT PRIMARY KEY,
    description           TEXT NOT NULL,             -- human-readable rationale
    match_criteria_json   TEXT NOT NULL,             -- e.g., {"artefact_kind":"pnu_row","prior_raw_hash_prefix":"sha256:abc"}
    reviewer_id           TEXT NOT NULL,
    decision              TEXT NOT NULL CHECK(decision IN ('approved','revoked')),
    created_at            TEXT NOT NULL,
    revoked_at            TEXT
);
```

A `content_equivalence_checks` row is covered by a batch approval iff it matches the batch's `match_criteria_json` (evaluated by `overseer/content_equivalence.py::batch_covers(row, criteria)`). The verifier check accepts batched-approved rows as if they had `review_decision='human_approved'`.

Constraints:

- Match criteria must reference at least one of `{artefact_kind, normalization_rule_version_change, prior_semantic_hash, new_semantic_hash, build_run_id_range}`. Free-form "approve everything" criteria are rejected at write time.
- A batch can be revoked; revocation flips `decision='revoked'` and reverts every row previously covered by the batch back to per-row review (verifier rechecks at next run).
- The batched-approval CLI requires reviewer_id and refuses to land an approval without a description string.

This addresses the operational concern raised in review: a tokenizer change touching 500 papers becomes one batch-approval decision, not 500 per-row decisions, while preserving auditability (every covered row's coverage is computable from the batch criteria at any time).

## 10. LLM-Aided Vocabulary Canonicalization

`vocabulary_registry` rows with `review_status='candidate'` (Phase 2 may have created many) can be linked to canonical entries via an LLM-aided step.

Flow:
1. A periodic job (Phase 3 ships the function; daemon-wrapping is Phase 4) scans `vocabulary_registry` for candidate rows older than N hours.
2. For each candidate, the LLM is given the candidate value plus the full list of canonical entries for that kind and asked: "Is this candidate a synonym of any canonical entry?"
3. The LLM produces a paired `llm_invocations` row and, if it asserts a synonym, a proposed mapping.
4. The candidate row is updated: `canonical_value` is set to the proposed canonical; `review_status` flips to `synonym` only after human approval. Until then, `review_status` stays `candidate` and a `completion_queue` row routes to human review.

This is conservative by design: no candidate is auto-promoted to synonym in Phase 3.

## 11. New Verifier Checks

Phase 3 adds five new checks to `verifier_data.py`:

1. **`_check_llm_provenance`** — Every LLM artefact (identified by source_mode='llm_generated' or by FK back to llm_invocations) has a paired `llm_invocations` row with `worker_surface` in the allowed enum, `model_name` set, and all hash fields populated.
2. **`_check_llm_field_policy`** — No LLM artefact write targets a component_type/field_path whose `field_policy` is not `llm_enrichable`. (Belt-and-suspenders to the write-time enforcement; catches direct INSERTs that bypass the API.)
3. **`_check_grounding_verdict_strict`** — Every LLM artefact in production (i.e., reachable via active artefact_registry rows with freshness_status='fresh') has a paired `llm_invocations.grounding_verdict='pass'`.
4. **`_check_content_equivalence_review_status`** — Every `content_equivalence_checks` row with `equivalence_verdict='semantic_equivalent'` has a paired `llm_invocations.review_decision='human_approved'`.
5. **`_check_llm_artefact_in_production_review_status`** — Every LLM artefact in production has `llm_invocations.review_decision IN ('human_approved', 'machine_approved')`; machine_approved requires the component_type to be on the auto-approve list.

Phase 2's `_check_scaffold_tables_empty` loses the four LLM-governance tables from its scaffold list — they are no longer scaffold at Phase 3 ship.

## 12. Repository Layout

New files:

```
overseer/
    source_packets.py            # capture, get, hash-pin enforcement
    prompt_templates.py          # register, lookup, hash check
    llm_invocations.py           # record, set_grounding_verdict, set_review_decision
    llm_submission.py            # accept_submission(conn, result_json) — AE→overseer entry point (§2.1)
    field_policy.py              # enforce_at_write, lookup
    grounding_verifier.py        # verify_grounding (field-pinned) + request_regrounding
    grounding_mode.py            # dry_run vs live mode resolver (§8.1)
    content_equivalence.py       # enqueue, set_verdict
    content_equivalence_batch.py # batched approval (§9 batched approval)
    vocab_canonicalizer.py       # LLM-aided mapping (function only; daemon Phase 4)
contracts/schemas/dependency_overseer/
    llm_auto_approve.json        # initially empty; auto-approve list
    model_allowlist.json         # allowed model_name values
    grounding_mode.json          # per-template dry_run vs live toggle (§8.1)
contracts/prompts/dependency_overseer/
    backing_prose_v1.md          # Phase 3 pilot prompt template content
scripts/
    dependency_overseer_grounding_tick.py
        # one-shot wrapper that runs grounding verification on pending invocations
    dependency_overseer_llm_review_cli.py
        # CLI: list pending reviews, approve/reject (records reviewer_id)
    dependency_overseer_batch_approve_cli.py
        # CLI: batched approval for content_equivalence_checks
migrations/  (extends scripts/migrations/)
    2026_XX_XX_content_equivalence_batch_approvals.sql
        # new table per §9 batched approval
tests/
    test_overseer_source_packets.py
    test_overseer_prompt_templates.py
    test_overseer_llm_invocations.py
    test_overseer_field_policy.py
    test_overseer_grounding_verifier.py
    test_overseer_content_equivalence.py
    test_overseer_vocab_canonicalizer.py
    test_overseer_phase3_verifier_checks.py
    test_overseer_phase3_round_trip.py
docs/
    DEPENDENCY_OVERSEER_PHASE_3_SPEC_2026-05-23.md     (this file)
    SPRINT_OVERSEER_PHASE_3_COMPLETION_2026-05-23.md   (at ship)
```

Modified files:

```
overseer/artefact_registry.py
    + source_mode optional param on update_with_hashes
    + raise FieldPolicyViolation when LLM source writes to non-enrichable field
overseer/verifier_data.py
    + 5 new checks (llm_provenance, llm_field_policy, grounding_verdict_strict,
                    content_equivalence_review_status,
                    llm_artefact_in_production_review_status)
    - _check_scaffold_tables_empty: 4 LLM tables removed from scaffold list
    + _check_semantic_equivalent_rate (OR9 monitor)
overseer/invalidator.py
    + route raw-only changes to content_equivalence_checks instead of
      auto-cascading or auto-cosmetic
```

## 13. Test Plan

| Test file | Coverage |
|-----------|----------|
| `test_overseer_source_packets.py` | capture validates member existence; hash recomputes; idempotent on identical members; rejects tombstoned members; stale-member detection on get |
| `test_overseer_prompt_templates.py` | register with hash; activate/deactivate; hash mismatch detected by verifier; allowed_field_policies enforced |
| `test_overseer_llm_invocations.py` | record / set_grounding_verdict / set_review_decision; CHECK constraints; FK on artefact_id; idempotency |
| `test_overseer_field_policy.py` | enforce_at_write rejects llm_generated → extracted_only/deterministic_only/human_only; allows llm_generated → llm_enrichable |
| `test_overseer_grounding_verifier.py` | pass when ≥90% of units field-pinned; field_pinned_failure when below threshold; tombstones on failure; raises completion_queue row; semantic-only similarity NOT accepted |
| `test_overseer_content_equivalence.py` | enqueue from invalidator; LLM verdict flow; semantic_equivalent requires human approval before cascade is suppressed |
| `test_overseer_vocab_canonicalizer.py` | function proposes mappings; mappings land as candidate-with-canonical_value-set; only human approval flips to synonym |
| `test_overseer_phase3_verifier_checks.py` | each of the 5 new checks: passes on clean state; fails on documented failure condition |
| `test_overseer_phase3_round_trip.py` | end-to-end: enqueue a Stage 2 backing_prose invocation → record → grounding pass → pending review → human approval → freshness flips to fresh → verifier all-pass |
| `test_overseer_llm_submission.py` | AE→overseer accept_submission entry; rejects mismatched hashes; idempotent on (invocation_id) |
| `test_overseer_regrounding_retry.py` | first grounding failure raises regrounding_requested; retry with identical output_hash treated as no-retry; second grounding failure tombstones + completion_queue row |
| `test_overseer_content_equivalence_batch.py` | batch approval covers matching rows; cannot match free-form criteria; revocation reverts coverage; verifier honors active batch as approval |
| `test_overseer_grounding_dry_run.py` | dry_run mode records sensitivity sweep, does not promote to fresh, raises tuning-report reminder at sample size |

Target: 55–70 new tests; all 220 Phase 1+2 tests must continue to pass.

## 14. Acceptance Criteria

1. Four scaffold tables activate (no longer empty per the Phase 3 verifier).
2. `prompt_templates` carries the Phase 3 pilot template `backing_prose_v1` with active=1; hash recomputes from `contracts/prompts/dependency_overseer/backing_prose_v1.md`.
3. `source_packets.capture()` validates every member exists and is active; raises on tombstoned members.
4. `update_with_hashes(source_mode='llm_generated')` to a non-llm-enrichable field raises `FieldPolicyViolation`.
5. Grounding verifier: passes when ≥90% of units field-pinned; semantic-only similarity is NOT accepted. **First-failure path**: raise `regrounding_requested`; AE retries with a fresh `invocation_id` and (verified) different `output_hash`. **Second-failure path**: tombstone + completion_queue row.
6. Human review queue: Stage 2 LLM artefact remains at `review_decision='pending'` until a reviewer sets approved/rejected.
7. Production freshness: an LLM artefact does not flip to `freshness_status='fresh'` until `review_decision='human_approved'` (or `machine_approved` for an auto-approved component_type).
8. Content equivalence check: a raw-only change cannot be marked semantic_equivalent without `llm_invocations.review_decision='human_approved'` OR coverage by an active `content_equivalence_batch_approvals` row with matching criteria.
9. Vocab canonicalization: candidates are not auto-promoted to synonym; LLM-proposed mapping lands as candidate-with-canonical_value-set requiring human approval.
10. All 5 new verifier checks pass on a clean DB; each fails on its documented failure condition; live lifecycle DB strict verifier exits 0.
11. Phase 3 round-trip end-to-end test passes.
12. All Phase 1 + Phase 2 tests continue to pass (no regressions).
13. Phase 3 ship report covers each criterion above.
14. **Caller architecture (§2.1)**: `overseer.llm_submission.accept_submission` is the sole entry point for AE→overseer Stage 2 content; no overseer module spawns LLM workers or imports provider SDKs.
15. **Dry-run mode (§8.1)**: `backing_prose_v1` ships at `dry_run`; the first 20 submissions produce sensitivity sweeps; a tuning-report reminder fires at the sample-size threshold.
16. **Bounded retry (§8)**: a first grounding failure raises `regrounding_requested` rather than tombstoning; a second failure (or an identical-output_hash retry) tombstones.
17. **Batched equivalence approval (§9)**: an active batch row covers matching `content_equivalence_checks` rows; revocation reverts coverage; verifier honors active batches as approval.

## 15. Open Implementation Questions for Phase 3

Resolved by the Phase 3 review (folded into the spec above):

- ~~LLM caller architecture~~ — **§2.1**: AE is the LLM orchestrator; the overseer never calls an LLM directly.
- ~~Re-prompt-on-failure policy~~ — **§8**: bounded 1-retry with fresh invocation_id and required-different output_hash; second failure tombstones + queues review.
- ~~Grounding-threshold tuning~~ — **§8.1**: dry-run mode on the first 20 submissions per component_type; sensitivity sweep recorded; tuning report required before flipping to live.
- ~~Content-equivalence operational cost~~ — **§9 batched approval**: a reviewer can approve a typed class of equivalence checks with one decision; batch covers via match criteria; revocable; audit-preserving.
- ~~Auto-approve list initial size~~ — **§7**: Phase 3 v1 ships empty; Phase 3 v1.1 adds `provenance_summary` after ≥50 human-approved invocations + reviewer attestation.

Still open in Phase 3:

1. **Grounding granularity (unit definition)**: sentence-level vs claim-level vs paragraph-level. Recommend sentence-level for `backing_prose_v1`; configurable per component_type. To be confirmed by the dry-run tuning report (§8.1).
2. **Token-overlap threshold for field-pinning**: default 0.5 (50% of unit's tokens). Tunable per component_type. To be confirmed by the dry-run tuning report (§8.1).
3. **Model allowlist contents**: who maintains `model_allowlist.json` and how. Recommend cross-AI coordination doc and a quarterly refresh schedule.
4. **LLM cost monitoring**: not in Phase 3 scope; tracked in OVERSEER-LLM-COST follow-up.
5. **Reviewer authentication**: Phase 3 CLI records reviewer_id from a CLI arg. Real authentication via an upstream system is Phase 4.
6. **Backfill of historical LLM-generated content**: not in Phase 3. Going-forward only.
7. **Batched approval match-criteria vocabulary**: the §9 list (artefact_kind, normalization_rule_version_change, prior_semantic_hash, new_semantic_hash, build_run_id_range) is conservative; extending it requires a separate PR with verifier-pass evidence.

## 16. Sequence of Work

Recommended order, mirroring Phase 1 and Phase 2 ballistic patterns and incorporating the Phase 3 review additions:

1. Land this spec (this commit).
2. Land Phase 3 contract files (`llm_auto_approve.json` (empty), `model_allowlist.json`, `grounding_mode.json` (all templates `dry_run`), `backing_prose_v1.md`).
3. Land migration `2026_XX_XX_content_equivalence_batch_approvals.sql` (new table per §9).
4. Implement `source_packets`, `prompt_templates`, `llm_invocations` modules + tests.
5. Implement `field_policy` + add `source_mode` parameter to `update_with_hashes` + wire field-policy enforcement.
6. Implement `llm_submission.accept_submission()` (the AE→overseer entry point per §2.1) + tests.
7. Implement grounding verifier + `request_regrounding` (bounded 1-retry per §8) + tests.
8. Implement `grounding_mode` resolver + dry-run sensitivity sweep + tuning-report reminder + tests.
9. Implement content_equivalence module + batched approval + tests; update invalidator to route raw-only changes via content_equivalence_checks.
10. Implement vocab_canonicalizer + tests.
11. Add 5 new verifier checks; remove 4 LLM-governance tables from scaffold list.
12. Implement Phase 3 round-trip test (dry-run mode for backing_prose_v1).
13. Run full test suite; run live verifier; smoke test against the real lifecycle DB.
14. Phase 3 ship report; update TASKS.md and TOPIC_PROGRESS.md. Add `OVERSEER-LLM-AUTO-APPROVE-v1.1` task referencing §7's v1.1 promotion path.

Estimated commits: 8–11 (larger than Phase 2 because of the grounding verifier, retry plumbing, dry-run mode, and content_equivalence layers).

**Phase 3 is the most-dangerous failure-mode phase per synthesis OR9.** Every default favors safety over throughput: conservative grounding thresholds, human-review-by-default, no auto-promotion of vocab synonyms, tombstone-and-queue on grounding failure. The Phase 4 retrospective should review whether any of these defaults can be relaxed once a corpus of approved invocations is built up.
