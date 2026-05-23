# Article Detail Epistemic Layer Panel Synthesis

Date: 2026-05-23
Input: `docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_BRIEF_2026-05-23.md`

## Executive Decision

The panel approves the direction but rejects the brief as an implementation contract.

The replacement implementation principle is:

> Build a modest, deterministic, machine-verified epistemic layer first. Do not ship LLM enrichment or full Toulmin reconstruction until identity, provenance, support sets, freshness, lifecycle DB writes, repair queues, and rendered production verification are enforceable.

The first implementation must be a strict payload-and-rendering gate, not a content-enrichment project.

## Reviewers

Six perspectives were simulated:

1. Backend/data-contract engineer.
2. Epistemology/knowledge-representation reviewer.
3. Article-page UX reviewer.
4. LLM provenance/governance reviewer.
5. QA/release-gate engineer.
6. Pipeline/dependency engineer.

## Consensus Findings

### 1. The Epistemic Layer Must Not Be Reduced To Toulmin

Toulmin is one rendering, not the ontology of the system.

The epistemic layer must distinguish:

- what the paper explicitly claims;
- what the Atlas deterministically derives;
- what other papers support or attack;
- what a model or reviewer synthesizes;
- what remains unknown or unavailable.

The layer must model relations among claims, evidence, warrants, sources, scope, and uncertainty.

### 2. Stable Identity Is Mandatory

Every object needs stable identity:

- `record_id`
- `component_id`
- `claim_id`
- `support_set_id`
- `build_run_id`
- source artefact IDs

Without stable IDs, primary claims can shift, rebuilds are not idempotent, and verifiers cannot prove freshness.

### 3. Status Must Be Split

The single word `complete` is dangerous. It can mean schema-complete, extraction-complete, enriched, fresh, reviewed, or renderable.

The spec must separate:

- `extraction_status`
- `enrichment_status`
- `freshness_status`
- `review_status`
- `render_status`
- `release_eligible`

### 4. Stage 1 Must Be Deterministic

Stage 1 should use only existing structured sources:

- article details;
- article metadata;
- top claims;
- evidence profile;
- argumentation summary;
- PNU fields where present;
- abstract/Article Finder metadata where present;
- related/supporting/contradicting-paper rows where present.

Stage 1 should not generate full backing prose, rebuttal synthesis, competing-account summaries, or Chinn-Brewer framing.

### 5. LLM Enrichment Must Be Deferred

Stage 2 may later enrich:

- plain-language warrant explanation;
- answer-shape rationale;
- backing prose;
- rebuttal synthesis;
- competing-account summary;
- Chinn-Brewer anomaly framing.

But Stage 2 must not enter production until field-level LLM policy, support-packet hashing, subscription-CLI-only enforcement, grounding checks, and review-state rules are implemented.

### 6. Provenance Must Be A Governing Invariant

Provenance cannot be decorative metadata.

Every component must have:

- source mode;
- source artefact IDs;
- source field paths;
- source hashes;
- support-set hash;
- builder version;
- review status;
- freshness status.

Hashes are computed by deterministic code, never supplied by LLM output.

### 7. Missing Content Needs Typed Absence

The panel rejected silent empty strings and bare empty arrays.

Every absence needs an explicit reason, such as:

- `not_extracted`
- `not_applicable`
- `source_missing`
- `extraction_failed`
- `stale`
- `blocked`
- `queued`
- `withheld_low_confidence`

Absence of extracted defeaters is not evidence that no defeaters exist.

### 8. Dependency/Freshness Is Not Optional

The epistemic layer is a derived artefact. It must record support sets and invalidate when upstream inputs change.

Required first upstream classes:

- PNU;
- abstract;
- structured claims;
- argumentation.

Article Finder and candidate PDF state must be represented before the full pipeline is declared complete.

### 9. Repair Loops Can Launder Bad Content

A repair process must not convert missing or failed content into acceptable prose merely to satisfy schema shape.

Allowed repair outcomes:

- deterministic rebuild;
- explicit missing-state marking;
- queue for extraction;
- queue for human review;
- blocking report.

Disallowed repair outcome:

- generated or placeholder content reclassified as extracted or verified.

### 10. Rendered UX Is Part Of The Contract

The page can pass JSON validation and still fail the reader.

The verifier must check rendered DOM behaviour, mobile overflow, visible provenance badges, empty states, Chinn-Brewer eligibility, stale-state display, and console/network errors.

## Accepted Schema Corrections

The revised spec must include:

- stable IDs;
- support sets;
- content hashes;
- status vocabularies;
- field policies;
- missing-state reasons;
- component-level provenance;
- component-level review status;
- deterministic primary-claim selection;
- count reconciliation;
- explicit Chinn-Brewer eligibility;
- UI-facing provenance badges;
- release-eligibility flags.

## Accepted Verifier Corrections

The revised verifier must check:

- JSON schema;
- controlled vocabularies;
- referential integrity;
- hash recomputation;
- support-set freshness;
- count reconciliation;
- LLM policy;
- idempotency;
- rendered DOM;
- production checksum;
- stale-dependency blocking;
- repair-queue integrity.

## Accepted UX Corrections

The article page should first implement a compact section:

1. primary claim;
2. claim rows;
3. evidence strength;
4. warrant label;
5. limitations / missing-state rows;
6. provenance badges.

Chinn-Brewer is conditional and below core epistemic material.

Visible provenance must work without hover.

## Accepted LLM Governance Corrections

Stage 2 is deferred from the first production release.

When enabled, it must enforce:

- subscription-CLI-only;
- field whitelist;
- generated-content labels;
- source packet manifest;
- prompt/input/output/support-packet hashes;
- no LLM-generated hashes/provenance/review status;
- no LLM generation of extracted-only fields;
- no production promotion of unreviewed generated public content unless explicitly permitted and visibly labelled.

## Minimum Viable Implementation

Stage 1 only:

- Add deterministic `epistemic_layer` for all 760 article records.
- Components:
  - `primary_claim`
  - `claim_rows`
  - `evidence_strength`
  - `defeaters` with honest empty state
  - `belief_network_context`
  - `answer_shape_status`
  - `provenance_summary`
- DB rows first, JSON export second.
- No LLM enrichment.
- No full Toulmin reconstruction unless directly extracted.
- Strict verifier.
- Rendered article-page verification.
- Production release blocked on unresolved required stale artefacts or blocking failures.

## Blocking Concerns Resolved In Spec

The companion spec must resolve:

- concrete payload schema;
- lifecycle table definitions;
- status vocabulary;
- deterministic hash rules;
- primary-claim selection;
- transaction boundaries;
- repair-loop allowed outcomes;
- release gate;
- UI rendering states;
- Stage 2 deferral and governance.

## Output

The corrected implementation contract is:

`docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md`
