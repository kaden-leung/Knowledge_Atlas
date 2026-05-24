# Handoff Prompt: Epistemic Layer Implementation

You are taking over the Knowledge_Atlas article-detail epistemic layer
implementation.

Repo:

```text
/Users/davidusa/REPOS/Knowledge_Atlas
```

Branch:

```text
master
```

Important pushed docs:

```text
docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_BRIEF_2026-05-23.md
docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_SYNTHESIS_2026-05-23.md
docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md
```

Controlling contract:

```text
docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md
```

## Context

The article detail page currently has partial epistemic inputs in article
payloads, including fields such as:

```text
top_claims
argumentation
evidence_profile
technical_results_table
constructs
instruments
operationalization
pnu
article_meta
science_summary
```

The panel concluded that the epistemic layer is broader than Toulmin. Toulmin is
only one possible representation. The full layer must include claim identity,
evidence strength, defeaters, PNU/belief-network dependencies, answer shape,
provenance, freshness, lifecycle DB records, repair/completion states, and
release verification.

## Task

Implement Stage 1 only. Do not add LLM enrichment yet.

Stage 1 requirements:

1. Read the controlling spec fully.
2. Add lifecycle DB schema/tables for:
   - `article_epistemic_records`
   - `article_epistemic_components`
   - `article_epistemic_support_sets`
   - `article_epistemic_build_runs`
   - `article_epistemic_completion_queue`
   - `article_epistemic_verification_events`
3. Implement deterministic Stage 1 builder:
   - one active epistemic record per `paper_id` and `schema_version`
   - stable `record_id`, `component_id`, `claim_id`, `support_set_id`
   - canonical JSON hashing
   - primary claim selection using the rule order in the spec
   - claim rows, evidence strength, defeater state, belief-network context,
     answer-shape status, provenance summary
   - repair/completion queue entries when required information is missing or
     stale
4. Implement strict verifier:

```bash
python3 scripts/verify_article_epistemic_layer_contract.py --strict
```

Verification failures must write repair/completion records, not merely fail.

5. Add focused tests:
   - schema validation
   - stable IDs
   - support-set hashing
   - stale dependency detection
   - missing primary claim repair
   - `attack_count` without mapped defeaters
   - no LLM-generated fields in Stage 1
6. Do not modify article page rendering yet unless the data contract and verifier
   are passing.

## Success Condition

A representative fixture set passes the strict verifier, and the builder can run
on the current article payload set so that every paper either receives a valid
Stage 1 epistemic record or a precise repair/completion item.

## Constraints

- Do not use LLMs inside the pipeline.
- Do not use direct provider APIs.
- Do not touch unrelated live data artifacts.
- Do not push or deploy unless explicitly asked.
- Preserve uncommitted user work.
