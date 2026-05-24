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

## 2. Pre-existing LLM Contract Alignment

The Article Eater repo already carries a substantial LLM anti-cheat contract: `SUBSCRIPTION_LLM_ORCHESTRATION_AND_ANTI_CHEAT_CONTRACT_2026-05-21.md`. Phase 3 of the overseer aligns with that contract rather than reinventing. Specifically:

- Allowed worker surfaces (from synthesis P22 and the existing contract): `antigravity_subscription`, `codex_cli_subscription`, `claude_cli_subscription`, `google_ai_api`. The overseer's `llm_invocations.worker_surface` CHECK constraint already enforces this enum.
- The existing contract has 12 last-mile success conditions (SC-SLO-1 through SC-SLO-12). Phase 3 maps every overseer verifier check that involves LLM artefacts to one or more SC-SLO conditions, so the two contracts compose cleanly.
- Job-packet / result-artefact orchestration is owned by the Article Eater side; the overseer side records provenance and enforces field-policy. The reconciler between the two systems (analogous to the AF reconciler in Phase 2) is a Phase 4 task.

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

Auto-approve list lives in `contracts/schemas/dependency_overseer/llm_auto_approve.json`. Phase 3 ships this file empty (every Stage 2 LLM artefact requires human approval). The auto-approve list can be extended in Phase 4 once a reviewer cohort has validated the grounding verifier.

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
- Re-prompt-on-failure is not in Phase 3. A failed grounding tombstones the artefact and queues human review.
- Default threshold = 0.9 (90% of units field-pinned). Tunable per component_type via `component_types.json` extension.

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

- `verify_strict()` adds a check: `_check_content_equivalence_review_status` flags any active `content_equivalence_checks` row with `equivalence_verdict='semantic_equivalent'` whose paired `llm_invocations.review_decision != 'human_approved'`. Phase 3 default: every `semantic_equivalent` verdict requires human approval before the cascade is suppressed.
- A second check: `_check_semantic_equivalent_rate` flags artefact kinds whose `semantic_equivalent` rate per build window exceeds a threshold (default 30%). Indicates either tokenizer-change-induced false positives or LLM over-permissiveness.

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
    field_policy.py              # enforce_at_write, lookup
    grounding_verifier.py        # verify_grounding (field-pinned)
    content_equivalence.py       # enqueue, set_verdict
    vocab_canonicalizer.py       # LLM-aided mapping (function only; daemon Phase 4)
contracts/schemas/dependency_overseer/
    llm_auto_approve.json        # initially empty; auto-approve list
    model_allowlist.json         # allowed model_name values
contracts/prompts/dependency_overseer/
    backing_prose_v1.md          # Phase 3 pilot prompt template content
scripts/
    dependency_overseer_grounding_tick.py
        # one-shot wrapper that runs grounding verification on pending invocations
    dependency_overseer_llm_review_cli.py
        # CLI: list pending reviews, approve/reject (records reviewer_id)
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

Target: 45–60 new tests; all 220 Phase 1+2 tests must continue to pass.

## 14. Acceptance Criteria

1. Four scaffold tables activate (no longer empty per the Phase 3 verifier).
2. `prompt_templates` carries the Phase 3 pilot template `backing_prose_v1` with active=1; hash recomputes from `contracts/prompts/dependency_overseer/backing_prose_v1.md`.
3. `source_packets.capture()` validates every member exists and is active; raises on tombstoned members.
4. `update_with_hashes(source_mode='llm_generated')` to a non-llm-enrichable field raises `FieldPolicyViolation`.
5. Grounding verifier: passes when ≥90% of units field-pinned; fails (tombstone + completion_queue row) below threshold; semantic-only similarity is NOT accepted.
6. Human review queue: Stage 2 LLM artefact remains at `review_decision='pending'` until a reviewer sets approved/rejected.
7. Production freshness: an LLM artefact does not flip to `freshness_status='fresh'` until `review_decision='human_approved'` (or `machine_approved` for an auto-approved component_type).
8. Content equivalence check: a raw-only change cannot be marked semantic_equivalent without `llm_invocations.review_decision='human_approved'`.
9. Vocab canonicalization: candidates are not auto-promoted to synonym; LLM-proposed mapping lands as candidate-with-canonical_value-set requiring human approval.
10. All 5 new verifier checks pass on a clean DB; each fails on its documented failure condition; live lifecycle DB strict verifier exits 0.
11. Phase 3 round-trip end-to-end test passes.
12. All Phase 1 + Phase 2 tests continue to pass (no regressions).
13. Phase 3 ship report covers each criterion above.

## 15. Open Implementation Questions for Phase 3

1. **Grounding granularity (unit definition)**: sentence-level vs claim-level vs paragraph-level. Recommend sentence-level for `backing_prose_v1`; configurable per component_type.
2. **Token-overlap threshold for field-pinning**: default 0.5 (50% of unit's tokens). Tunable per component_type.
3. **Model allowlist contents**: who maintains `model_allowlist.json` and how. Recommend cross-AI coordination doc.
4. **Auto-approve list initial size**: Phase 3 ships empty. Adding a component_type to auto-approve requires a separate PR with verifier-pass evidence.
5. **Re-prompt-on-failure policy**: Phase 3 ships none. Phase 4 may add bounded re-prompt with fresh invocation_id and capped retry count.
6. **LLM cost monitoring**: not in Phase 3 scope; tracked in OVERSEER-LLM-COST follow-up.
7. **Reviewer authentication**: Phase 3 CLI records reviewer_id from a CLI arg. Real authentication via an upstream system is Phase 4.
8. **Backfill of historical LLM-generated content**: not in Phase 3. Going-forward only.

## 16. Sequence of Work

Recommended order, mirroring Phase 1 and Phase 2 ballistic patterns:

1. Land this spec.
2. Land Phase 3 contract files (`llm_auto_approve.json`, `model_allowlist.json`, `backing_prose_v1.md`).
3. Implement `source_packets`, `prompt_templates`, `llm_invocations`, `field_policy` modules + tests.
4. Add `source_mode` parameter to `update_with_hashes` and wire field-policy enforcement.
5. Implement grounding verifier + tests.
6. Implement content_equivalence module + tests; update invalidator to enqueue checks.
7. Implement vocab_canonicalizer + tests.
8. Add 5 new verifier checks; remove 4 tables from scaffold list.
9. Implement Phase 3 round-trip test.
10. Run full test suite; run live verifier.
11. Phase 3 ship report; update TASKS.md and TOPIC_PROGRESS.md.

Estimated commits: 7–10 (larger than Phase 2 because of the grounding verifier and content_equivalence layers).

**Phase 3 is the most-dangerous failure-mode phase per synthesis OR9.** Every default favors safety over throughput: conservative grounding thresholds, human-review-by-default, no auto-promotion of vocab synonyms, tombstone-and-queue on grounding failure. The Phase 4 retrospective should review whether any of these defaults can be relaxed once a corpus of approved invocations is built up.
