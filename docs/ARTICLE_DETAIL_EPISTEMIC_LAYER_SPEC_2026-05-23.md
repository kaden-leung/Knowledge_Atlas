# Article Detail Epistemic Layer: Implementation Contract

Date: 2026-05-23  
Status: implementation contract, stage 1  
Related review: `ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_SYNTHESIS_2026-05-23.md`

## 1. Decision

The article detail page should get an epistemic layer, but the first production
version must be modest, deterministic, and fully verifiable.

Stage 1 builds a database-backed, machine-verifiable layer from existing article
detail payloads, Article Finder metadata, PNU state where available, and existing
argumentation fields. It does not call an LLM.

Stage 2 may add LLM-generated interpretive content later, but only after field
policies, provenance, source packet manifests, grounding verification, and review
rules are enforced by code.

## 2. Conceptual Scope

The epistemic layer is not merely the Toulmin layer.

The Toulmin layer is one possible representation of claim, data, warrant,
backing, qualifier, and rebuttal. The epistemic layer is broader. It includes:

- the paper's central claims and their scope;
- the warrant or reason the claim is treated as supported;
- the evidence strength and limits of that support;
- defeaters, attacks, caveats, and missing-defeater states;
- PNU and belief-network dependencies when available;
- the answer shape: Toulmin, field map, comparison, mechanism, review synthesis,
  or unknown;
- provenance for each displayed value;
- freshness against its support set;
- repair status when required information is absent, stale, or inconsistent.

## 3. Stable Identity

Every article epistemic layer record and every component must have stable
identity. Wording changes must not silently create a new concept unless the
claim itself has changed.

Required identifiers:

- `record_id`: `article_epistemic_layer.v1:{paper_id}`
- `schema_version`: currently `article_epistemic_layer.v1`
- `build_run_id`: unique build execution identifier
- `component_id`: `{record_id}:{component_type}:{local_id}`
- `claim_id`: `claim:{paper_id}:{sha256(canonical_claim_text)[:16]}`
- `support_set_id`: `support_set:{sha256(canonical_support_members)[:16]}`
- `source_artifact_id`: stable identifier for each source payload, database row,
  PDF, OCR artifact, abstract, PNU row, or Article Finder metadata record

Historical versions are retained in the lifecycle database. There is one active
record per `paper_id` and `schema_version`.

## 4. Status Vocabularies

Top-level records must use split statuses rather than a single ambiguous state:

- `extraction_status`: `absent`, `minimal`, `partial`, `complete`, `failed`
- `enrichment_status`: `none`, `deferred`, `draft`, `machine_checked`,
  `human_approved`, `rejected`
- `freshness_status`: `fresh`, `stale`, `unknown`
- `review_status`: `not_required`, `unreviewed`, `machine_verified`,
  `human_review_required`, `human_approved`, `human_rejected`
- `render_status`: `renderable`, `show_with_warning`, `hidden`, `block_article`
- `release_eligible`: boolean

Component status values:

- `present`
- `not_extracted`
- `not_applicable`
- `source_missing`
- `extraction_failed`
- `stale`
- `blocked`
- `queued`
- `withheld_low_confidence`

Source modes:

- `extracted`
- `deterministic_derived`
- `llm_generated`
- `human_entered`
- `missing`

Field policies:

- `extracted_only`
- `deterministic_only`
- `llm_enrichable`
- `human_only`

Empty arrays are illegal unless paired with `absence_reason`.

## 5. Lifecycle Database Tables

The layer is a derived artifact governed by the lifecycle database, not only a
field appended to page JSON.

Required tables:

### `article_epistemic_records`

- `record_id`
- `paper_id`
- `schema_version`
- `active`
- `extraction_status`
- `enrichment_status`
- `freshness_status`
- `review_status`
- `render_status`
- `release_eligible`
- `primary_claim_id`
- `build_run_id`
- `input_fingerprint`
- `payload_hash`
- `blocking_failures_json`
- `created_at`
- `updated_at`

### `article_epistemic_components`

- `component_id`
- `record_id`
- `paper_id`
- `component_type`
- `component_status`
- `source_mode`
- `field_policy`
- `review_status`
- `freshness_status`
- `render_policy`
- `content_json`
- `content_hash`
- `support_set_id`
- `provenance_json`
- `verification_json`
- `created_at`
- `updated_at`

### `article_epistemic_support_sets`

- `support_set_id`
- `support_set_hash`
- `members_json`
- `created_at`

Each member entry must include:

- `source_artifact_id`
- `source_kind`
- `source_path_or_table`
- `source_record_id`
- `source_field_path`
- `source_hash`
- `source_updated_at` when known

### `article_epistemic_build_runs`

- `build_run_id`
- `builder_version`
- `started_at`
- `finished_at`
- `input_snapshot_hash`
- `record_count`
- `success_count`
- `failure_count`
- `repair_count`
- `status`
- `report_json`

### `article_epistemic_completion_queue`

- `queue_id`
- `paper_id`
- `component_type`
- `reason`
- `severity`
- `first_seen_at`
- `last_seen_at`
- `attempt_count`
- `next_action`
- `status`
- `assigned_to`
- `resolved_at`

### `article_epistemic_verification_events`

- `event_id`
- `record_id`
- `build_run_id`
- `verifier_name`
- `verifier_version`
- `status`
- `failures_json`
- `repair_actions_json`
- `created_at`

## 6. Canonical Hashing

Hashes must be produced by code, never by an LLM.

Canonical JSON rules:

- UTF-8 encoding
- sorted keys
- compact separators `,` and `:`
- no volatile fields such as timestamps in content hashes
- SHA-256 over the canonical byte string

`payload_hash` covers the public epistemic layer payload. `support_set_hash`
covers source-member identity plus source hashes. `input_fingerprint` covers all
support set hashes for a record.

> **Amendment 2026-05-24 (panel review `docs/AEPL_PANEL_RUTHLESS_REVIEW_OUTPUT_2026-05-24.md` §4.2, §4.3).**
> Two corrections supersede the paragraph above:
>
> 1. **`payload_hash` covers immutable CONTENT only** — `schema_version`,
>    `record_id`, `paper_id`, `primary_claim_id`, and each component's
>    `content_json`. It deliberately EXCLUDES all mutable lifecycle/status
>    fields (`extraction_status`, `enrichment_status`, `freshness_status`,
>    `review_status`, `render_status`, `release_eligible`). Those travel in the
>    public payload's envelope but are not part of the content identity. This
>    makes the published payload recomputable from its own bytes (no
>    `false`-vs-`0` divergence) and lets promotion, machine-verification, and
>    PNU repair change lifecycle state without rewriting content hashes or
>    invalidating downstream caches.
> 2. **`input_fingerprint` additionally covers `builder_version` and
>    `schema_version`**, not support-set hashes alone. Bumping the builder with
>    identical inputs must change the fingerprint, otherwise a rule change is a
>    silent regression.

## 7. Public Payload Shape

Each article detail payload may include:

```json
{
  "epistemic_layer": {
    "schema_version": "article_epistemic_layer.v1",
    "record_id": "article_epistemic_layer.v1:PDF-0007",
    "paper_id": "PDF-0007",
    "extraction_status": "partial",
    "enrichment_status": "deferred",
    "freshness_status": "fresh",
    "review_status": "machine_verified",
    "render_status": "renderable",
    "release_eligible": true,
    "primary_claim_id": "claim:PDF-0007:examplehash0000",
    "build": {
      "build_run_id": "aepl-20260523-000001",
      "builder_version": "article_epistemic_builder.v1",
      "input_fingerprint": "sha256:...",
      "payload_hash": "sha256:..."
    },
    "counts": {
      "claim_count": 3,
      "support_count": 4,
      "attack_count": 0,
      "defeater_count": 0
    },
    "components": {
      "primary_claim": {},
      "claim_rows": [],
      "evidence_strength": {},
      "defeaters": {},
      "belief_network_context": {},
      "answer_shape_status": {},
      "provenance_summary": {}
    },
    "blocking_failures": []
  }
}
```

> **Amendment 2026-05-24.** The status fields in the envelope above
> (`extraction_status` … `release_eligible`) are NOT covered by `payload_hash`
> (see §6 amendment). They are mutable lifecycle state; `payload_hash` is the
> identity of the immutable content only. A downstream consumer can verify the
> payload it holds by recomputing the content hash from the bytes it received.

Each component object must include:

- `component_id`
- `component_type`
- `status`
- `source_mode`
- `field_policy`
- `review_status`
- `freshness_status`
- `render_policy`
- `display_label`
- `content_json`
- `absence_reason` when content is empty
- `support_set_id`
- `support_set_hash`
- `provenance`
- `verification`

## 8. Stage 1 Builder

Stage 1 must use deterministic rules only.

Inputs, when available:

- existing article detail JSON;
- Article Finder paper metadata;
- abstract text and abstract hash;
- candidate PDF state and PDF hash;
- OCR artifact hash;
- existing `top_claims`, `argumentation`, `evidence_profile`,
  `technical_results_table`, `constructs`, `instruments`, and
  `operationalization`;
- PNU registry rows and hashes;
- lifecycle database state.

Primary claim selection:

1. Prefer an explicit structured core finding if present.
2. Else use `top_claims`, sorted by:
   - higher `support_count`;
   - lower `attack_count`;
   - higher `credence`;
   - stable source order;
   - canonical claim text.
3. Else use a declared article-level main conclusion if present.
4. Else use a science-summary core finding if present.
5. Else emit a missing primary-claim component with
   `status=not_extracted` and a completion-queue item.

Claim rows:

- must preserve source text;
- must include canonical claim text;
- must declare `claim_scope`, `claim_type`, `claim_polarity`,
  `assertion_status`, and `epistemic_status` where determinable;
- must mark unknown values explicitly, not infer them loosely.

Evidence strength:

- is tied to a claim, never only to an article;
- may copy existing numeric `credence` only as `source_credence`;
- must record `confidence_basis`;
- must not upgrade confidence because generated prose sounds persuasive.

Defeaters:

- are target-specific: claim, warrant, method, measurement, interpretation,
  generalizability, mechanism, or application;
- if `attack_count > 0` but no defeater rows exist, emit
  `absence_reason=attack_count_without_mapped_rows`;
- distinguish `no_defeater_extracted` from `no_defeater_exists`.

Belief-network context:

- may be partial;
- must list PNU IDs and PNU hashes if used;
- must become stale when a referenced PNU row, edge, or registry hash changes.

Answer shape:

- Stage 1 may assign `toulmin`, `field_map`, `comparison`, `mechanism`,
  `review_synthesis`, `mixed`, or `unknown`;
- the assignment must include the deterministic rule that produced it;
- if no rule fires, use `unknown`, not a guess.

## 9. Stage 2 LLM Enrichment

Stage 2 is deferred for production.

When enabled later, LLMs may only populate fields whose policy is
`llm_enrichable`. LLMs must not generate or modify:

- claim identity;
- extracted claim text;
- DOI, URL, citation, authors, year, venue;
- sample size;
- study design type;
- numeric effect values;
- evidence strength;
- confidence or credence;
- support and attack counts;
- source links;
- hashes;
- freshness state;
- review status.

Each LLM call must use the approved subscription-CLI path, not direct API keys or
provider SDK calls. Each call must store:

- model name;
- prompt template hash;
- source packet manifest;
- source packet hash;
- output hash;
- grounding result;
- reviewer decision if a human review is required.

Unreviewed generated content may be displayed only with an explicit visible
`llm_generated` label and only when the release policy permits it.

## 10. Dependency And Freshness Rules

Every computed value depends on a support set.

When any support-set member changes, the affected component becomes stale. The
record becomes stale if a required component is stale.

> **Amendment 2026-05-25 (graceful degradation — `docs/AEPL_GRACEFUL_DEGRADATION_2026-05-25.md`).**
> Components are split into CORE (PNU-independent, available today) and
> ENRICHMENT (depends on upstream work not yet done). **PNU is reclassified from
> a required dependency to an ENRICHMENT dependency.** Record freshness and
> renderability are computed from CORE components only. A stale/missing PNU marks
> `belief_network_context` as `pending_upstream` (a non-blocking warning) and the
> record stays `fresh`/`renderable`. Principle: show the best we have now, label
> the rest, never gate the whole layer on one not-yet-ready input.

Required dependency classes:

- article detail JSON;
- article index row;
- Article Finder metadata row;
- abstract;
- candidate PDF state;
- PDF hash;
- OCR artifact;
- extracted claim rows;
- argumentation fields;
- evidence profile;
- PNU row;
- PNU edge;
- PNU registry snapshot;
- lifecycle review event.

Article Finder must have a local database formally related to the lifecycle
database. Candidate and contributed PDFs must pass through distinct states:

- `metadata_only`
- `abstract_only`
- `candidate_pdf_unverified`
- `pdf_verified`
- `ocr_ready`
- `extracted`

Abstract-derived content must be marked separately from PDF-derived content.

## 11. Verification Layer

The strict verifier is required before any promotion.

Command target:

```bash
python3 scripts/verify_article_epistemic_layer_contract.py --strict
```

Required checks:

- all records validate against schema;
- status values are in the approved vocabularies;
- IDs are stable and unique;
- every component has a support set;
- every support set hash recomputes;
- every payload hash recomputes;
- every component with empty content has an `absence_reason`;
- evidence strength is claim-bound;
- support and attack counts reconcile with rows or declare a count basis;
- no LLM-generated field appears in Stage 1 output;
- no forbidden direct LLM provider calls are introduced;
- stale required components block release eligibility;
- completion-queue entries exist for repairable gaps;
- one active record exists per `paper_id` and schema version;
- rendered payload contains required public fields.

Rendered-page verifier:

```bash
python3 scripts/verify_article_epistemic_render_contract.py --strict
```

Required checks:

- article page renders the epistemic section;
- primary claim is visible;
- evidence strength or missing-state explanation is visible;
- defeater section distinguishes missing from none;
- provenance badges are visible without hover;
- stale and missing states render as warnings;
- no horizontal overflow on mobile fixture widths;
- no console errors;
- no failed network requests for required assets.

## 12. Repair And Completion

Verification failure must trigger repair or completion, not merely block release.

Allowed repair outcomes:

- deterministic rebuild of affected records;
- stale support-set refresh;
- Article Finder metadata refresh;
- PDF verification request;
- OCR or extraction queue item;
- PNU dependency refresh;
- human review queue item;
- explicit waiver with reviewer identity, expiry, and visible warning.

Repair actions must be written to `article_epistemic_completion_queue` and
`article_epistemic_verification_events`.

Promotion is blocked while any blocking repair item remains unresolved.

## 13. Last-Mile Release Conditions

A release may promote the epistemic layer only if all conditions hold:

> **Amendment 2026-05-25.** "Required component" below means CORE components only
> (see §10 amendment). A pending ENRICHMENT section (e.g. belief-network context
> awaiting PNU repair) does not block release of the core epistemic reading.

- strict data verifier passes;
- strict rendered verifier passes;
- no required (CORE) component is stale;
- no blocking completion-queue item is open;
- every public payload hash matches the lifecycle database record;
- production serves the same artifact hash as the release artifact;
- article detail pages return HTTP 200;
- required CSS and JS assets return HTTP 200;
- page has no console errors;
- mobile and desktop visual checks pass;
- provenance labels remain visible in production.

## 14. Tests

Required test groups:

- `tests/test_article_epistemic_schema.py`
- `tests/test_article_epistemic_builder.py`
- `tests/test_article_epistemic_support_sets.py`
- `tests/test_article_epistemic_freshness.py`
- `tests/test_article_epistemic_completion_queue.py`
- `tests/test_article_epistemic_llm_governance.py`
- `tests/test_article_epistemic_render_contract.py`
- `tests/test_article_epistemic_release_gate.py`

Minimum fixtures:

- complete record;
- partial record with missing primary claim;
- record with `attack_count > 0` and no mapped defeater rows;
- stale PNU dependency;
- abstract-only Article Finder record;
- candidate PDF unverified;
- long claim text;
- unreviewed LLM content fixture, which must be rejected in Stage 1.

## 15. Implementation Phases

Phase 0: panel review and contract writing. Complete.

Phase 1: add lifecycle database schema and migrations.

Phase 2: implement Stage 1 builder, support-set hashing, exported payloads, and
strict data verifier.

Phase 3: update `ka_article_view.html` to render the layer with visible
provenance, empty states, stale states, and mobile-safe layout.

Phase 4: add rendered verifier and release gate integration. Promotion must fail
closed and create repair records.

Phase 5: design Stage 2 LLM enrichment separately, with source-packet manifests,
subscription-CLI enforcement, grounding checks, and review gates.

## 16. Success Conditions

The implementation succeeds when:

- all 760 current article detail records receive an active Stage 1 epistemic
  record or a precise repair item;
- no displayed epistemic value lacks provenance;
- no required component can silently become stale;
- the article page displays useful epistemic information even when the source
  record is partial;
- every verifier failure records a concrete next repair action;
- the release process cannot promote stale, unverifiable, or unlabelled generated
  epistemic content.
