# Article Detail Epistemic Layer Panel Brief

Date: 2026-05-23
Scope: `ka_article_view.html?id=PDF-XXXX`, `data/ka_payloads/article_details.json`, lifecycle DB records, deterministic builders, optional LLM enrichment, verifiers, repair loops, and production release gates.

## Purpose

The article-detail page should become the place where a reader inspects not only what a paper says, but why the Atlas treats the paper's claims as warranted, uncertain, contested, or actionable.

The epistemic layer is broader than a Toulmin layer. Toulmin is one representation inside the epistemic layer. The full layer includes claim identity, warrant structure, evidence strength, defeaters, belief-network context, answer shape, reader response, provenance, and freshness/dependency status.

This panel reviews the contract and implementation plan before code is written.

## Current State

The current payload already supports a partial first pass:

- `data/ka_payloads/article_details.json` has 760 article detail records.
- Each detail record may include `science_summary`, `pnu`, `operationalization`, `evidence_profile`, `argumentation`, `top_claims`, `related_papers`, `supporting_papers`, `contradicting_papers`, `visual_support_gallery`, `technical_results_table`, and `article_meta`.
- `ka_article_view.html` already renders science summary, instruments/sensors, journey links, PNU, visual gallery, and study record.
- `top_claims` rows currently expose shallow claim data: finding, signal, warrant, credence, support/attack counts, and qualifier.

Missing pieces:

- a formal `epistemic_layer` contract;
- lifecycle DB records for epistemic components;
- full provenance on every component;
- explicit support sets and dependency hashes;
- complete Toulmin objects where available;
- defeater/competing-account records;
- answer-shape selection and rationale;
- reader-response affordance;
- repair/completion process for verification failures;
- release gate that verifies local, staging, and production rendered behaviour.

## Proposed Two-Stage Pipeline

### Stage 1: Deterministic Baseline

No LLM use.

Inputs:
- existing article details payload;
- articles payload;
- argumentation payload;
- lifecycle DB structured claims if available;
- PNU rows where available;
- Article Finder metadata and abstracts where available.

Outputs:
- `article_epistemic_records`;
- `article_epistemic_components`;
- updated `article_details.json` with `epistemic_layer`;
- coverage report;
- completion queue for missing extraction.

Permitted derivations:
- primary claim from structured claim or strongest `top_claims` row;
- data rows from `top_claims`;
- warrant type from existing warrant label;
- qualifier from existing qualifier or explicit `not_extracted`;
- evidence strength from credence, sample size, article type, support/attack counts;
- belief-network context from topic/theory/PNU/support/attack links;
- honest empty states for missing backing, rebuttals, or competing accounts.

### Stage 2: LLM Enrichment

Optional and provenance-marked.

LLM-eligible fields:
- backing prose;
- rebuttal synthesis;
- competing-account summaries;
- answer-shape rationale;
- Chinn-Brewer anomaly framing;
- plain-language warrant explanation.

LLM-prohibited actions:
- inventing evidence;
- upgrading confidence;
- overwriting extracted claims;
- hiding missing source content;
- presenting generated synthesis as extracted fact.

Every LLM output must record model, prompt ID, prompt hash, input hash, output hash, source fields, source artefact hashes, generated time, and review status.

## Proposed Page Sections

The article page should render these sections, with graceful empty states:

1. What this paper says.
2. Epistemic reading.
3. Evidence strength.
4. Instruments and sensors.
5. Continue the Atlas journey.
6. Plausible neural explanation.
7. Visual support gallery.
8. Study record.

The `Epistemic reading` section should show:

- primary claim;
- claim rows;
- data;
- warrant;
- backing;
- qualifier;
- rebuttals/defeaters;
- competing accounts;
- answer shape;
- provenance markers.

The Chinn-Brewer reader-response panel should appear only when the article has a genuine anomaly, rebuttal, defeater, or contested claim.

## Required Success Conditions

### Claim Layer

- Every article has `epistemic_layer.status`.
- `partial` and `complete` records have a primary claim.
- Claim text, claim type, source, paper ID, and provenance are present.
- Missing confidence is explicit, not silent.

### Toulmin / Warrant Layer

- `complete` records have claim, data, warrant, backing, qualifier, and rebuttal or explicit `rebuttal_status`.
- Warrant types use controlled vocabulary.
- Generated fallback is not labelled as extracted.

### Evidence-Strength Layer

- Numeric values are numeric or explicitly missing.
- Strength indicators distinguish evidence strength from argument structure.
- Sample size, design type, support count, attack count, credence, and article type are shown where available.

### Defeater Layer

- Every article has a defeater array, even if empty.
- Attack counts and defeater rows cannot contradict each other.
- Empty state is explicit: "No explicit defeater has been extracted for this paper yet."

### Belief-Network Layer

- Topic, theory, mechanism/PNU, support, and contradiction links are shown where available.
- Links resolve or are withheld with explicit reason.
- Counts match rows or state truncation.

### Answer-Shape Layer

- Every article has `answer_shape` or `answer_shape_status`.
- Allowed shapes: `toulmin`, `field_map`, `procedure`, `contrast_pair`, `ranked_brief`, `mixed`.
- The UI explains why the shape was selected.

### Reader-Response Layer

- Chinn-Brewer appears only for contested/anomalous articles.
- If shown, all seven responses are present.
- Reader responses are local/session-only unless backend persistence is explicitly added.

### Provenance Layer

- Every component has provenance.
- LLM-generated content is visible as LLM-generated and unreviewed unless reviewed.
- Provenance includes support artefacts and support hashes.

### Dependency/Freshness Layer

- Every component records its support set.
- If a PNU, abstract, structured claim, or argumentation artefact changes, affected epistemic components become stale and queue rebuilds.

### Verification And Repair

- Verification failure triggers classification, repair/completion/queueing, and re-verification.
- Unresolved failures block promotion with a specific report.

### Last Mile

- Local tests pass.
- Staging smoke passes.
- Production smoke passes.
- Production article page renders required headings.
- Production article page has no JS console errors.
- Mobile render has no horizontal overflow.
- Production payload checksum matches DB-derived artefact checksum.

## Review Questions

Each panel reviewer should answer:

1. What is missing from the epistemic model?
2. What should be in Stage 1 versus Stage 2?
3. What must never be LLM-generated?
4. What fields require human review?
5. What verifier failure would the proposed design miss?
6. What repair loop could launder bad content?
7. What must block production?
8. What is too ambitious for the first implementation?
9. What is the smallest useful implementation?
10. What exact contract change do you recommend?

## Panel Roles

Use these six perspectives:

1. Backend/data-contract engineer.
2. Epistemology/knowledge-representation reviewer.
3. Article-page UX reviewer.
4. LLM provenance/governance reviewer.
5. QA/release-gate engineer.
6. Pipeline/dependency engineer.

## Expected Output

The panel execution should produce:

```text
docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_SYNTHESIS_2026-05-23.md
docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md
```

The synthesis records the review. The spec incorporates accepted changes and becomes the implementation contract.
