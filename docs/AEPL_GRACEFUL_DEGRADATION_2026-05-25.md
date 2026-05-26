# Article-Epistemic Layer — Graceful Degradation & Availability Tiers

**Date:** 2026-05-25 (decided), implemented 2026-05-26
**Status:** governing design decision (Stage 1)
**Origin:** DK directive — "holding up presentation of an epistemic layer because the
PNUs are not done is the wrong approach. Show what we can and say the others are
not yet completed… robustness = 'we give you the best we can with what we have
now, and we'll do better soon.'"

## Principle

Do not gate the whole epistemic layer on any single not-yet-ready input. Render
every component we can fill today; mark the rest with a typed, honest "pending"
or "planned" state; and never let one missing input suppress the page or the
record.

## The mechanism: per-component availability tiers

Each component is tiered:

| Tier | Meaning | Render behaviour |
|------|---------|------------------|
| `available` | Derivable now from extracted/deterministic fields | Show it |
| `pending_upstream` | Depends on upstream work not yet done (today: PNU repair) | Show a typed "pending" note, not a blank |
| `planned_enrichment` | Stage-2 LLM sections, not built yet | Advertise as "coming" so the page shows its full intended shape |

**Record freshness and renderability are computed from CORE components only.**

- **CORE** (PNU-independent, available today): `primary_claim`, `claim_rows`,
  `evidence_strength` (argument support), `defeaters`, `answer_shape_status`,
  `provenance_summary`.
- **ENRICHMENT** (may be pending without blocking): `belief_network_context`
  (depends on PNU). When the PNU is `requires_repair`/missing, this one section
  is `pending_upstream`; the record stays `fresh`/`renderable` and its
  completion-queue item is a **warning**, not a blocker.

The public payload carries this contract explicitly per article:

```json
"availability_summary": {
  "available_now": ["answer_shape_status","claim_rows","defeaters",
                    "evidence_strength","primary_claim","provenance_summary"],
  "pending_upstream": [{"component_type":"belief_network_context",
                        "reason":"pnu_requires_repair"}],
  "planned_enrichment": ["warrant_explanation","rebuttal_synthesis",
                         "competing_account_summary","plain_language_interpretation"]
}
```

## Corpus impact (verified 2026-05-26 on 160sp/pipeline_lifecycle_full.db)

| Metric | Before (PNU-gated) | After (graceful degradation) |
|--------|-------------------|------------------------------|
| `renderable` records | 2 / 760 | **760 / 760** |
| `fresh` records | 0 / 760 | **760 / 760** |
| Blocking queue items | 758 | **0** (758 now `warning`) |
| Verifier | 760/760 clean | 760/760 clean |

The two formerly-"renderable" records were renderable only because their PNU was
*missing*; now all 760 render on the strength of their core epistemic content.

## What we display now vs. later

**Available today (≈100% coverage unless noted):** primary claim; all claim rows
with **claim facets** (`claim_type` + `epistemic_status` derived from the upstream
`signal` — e.g. *Indicator To Construct Inference* → `construct_inference` /
`inferred`); argument-support profile (honestly labelled — not a severity
measure) with **limitations**, study design, and key statistics surfaced from the
extracted summary; defeater *state* (honest "no defeater extracted", never "none
exist"); answer shape with its rule trace; provenance summary.

**Pending upstream:** belief-network context (needs PNU repair) — shown as a
"pending" section.

**Planned (Stage 2):** warrant explanation, rebuttal synthesis, competing-account
summary, plain-language interpretation — advertised, behind the Stage-2 gate
(span attribution + human review per the panel review).

**Not buildable from current data (verified absent):** corroboration from
`supporting_papers`/`contradicting_papers` (0% populated) and argument edges
(all zero). Do not promise these until the upstream extraction fills them.

## Spec implications

- **§10 amended:** PNU is reclassified from a *required* dependency class to an
  *enrichment* dependency. Its staleness marks `belief_network_context`
  `pending_upstream`; it does not make the record stale.
- **§13 amended:** the release gate evaluates freshness over CORE components
  only. A pending enrichment section does not block release of the core reading.
