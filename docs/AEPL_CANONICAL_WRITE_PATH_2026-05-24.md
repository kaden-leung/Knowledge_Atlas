# Article-Epistemic Layer — Canonical Write Path & Builder Ownership

**Date:** 2026-05-24
**Status:** governing decision (Stage 1)
**Origin:** `docs/AEPL_PANEL_RUTHLESS_REVIEW_OUTPUT_2026-05-24.md` §4.2 item 3 (Helland, Wright)

## The problem this resolves

Two builders in this repo produce overlapping epistemic content for the same
papers:

- `scripts/build_article_epistemic_layer.py` — the **article-detail epistemic
  layer**. Writes `article_epistemic_records` / `_components` / `_support_sets`
  / `_build_runs` / `_completion_queue` / `_verification_events`. Populated on
  the full 760-paper corpus; feeds the article page (Phase 3) and the public
  payload `data/ka_payloads/article_epistemic_layer.json`.
- `overseer/article_epistemic_builder.py` — part of the **dependency overseer**
  subsystem. Writes a *different, disjoint* set of tables (`claims`,
  `defeaters`, `belief_network_links`, `answer_shape_decisions`,
  `artefact_registry`, `content_hashes`) through a fenced, fencing-token-
  validated path. Has its own test suite (5 files). Currently `claims` is empty
  on the production DB — it has not been run over the corpus.

They share one physical SQLite file (`160sp/pipeline_lifecycle_full.db`) but
write **disjoint tables**, so there is no row-level write collision. The risk is
**divergent content for the same facts**: the two builders use *different rules*
for the same decisions (e.g. `select_primary_claim` reads `finding` in one and
`canonical_claim_text`/`text` in the other; the two `answer_shape` assigners use
entirely different rule cascades). Run both and the same paper could carry a
different primary claim and a different answer shape depending on which tables
you read.

## Decision

1. **The article-detail epistemic layer
   (`scripts/build_article_epistemic_layer.py`) is the canonical source of truth
   for the article page's epistemic content in Stage 1.** It is the populated,
   verified, rendered-against representation. The public payload and the
   `ka_article_view.html` renderer read it and only it.

2. **The overseer's `article_epistemic_builder.py` is NOT deprecated or
   removed.** It is a tested component of a separate subsystem under active
   development. It must not, however, be run as a second writer of
   article-page epistemic content against the production DB until item 3 below
   is satisfied.

3. **Before Stage 2 (LLM enrichment) begins, the two builders' rule logic must
   be reconciled to a single shared implementation.** Concretely: the
   deterministic rule functions (`select_primary_claim`, the `answer_shape`
   cascade, the defeater target/defeat-kind vocabulary) move into one module
   that *both* entry points import, so they cannot diverge. The choice of which
   storage/write path survives for Stage 2 (the layer's denormalized component
   model, or the overseer's fenced normalized model) is open question #1 for
   David in the panel output and is **deferred, not decided here.** What is
   decided here is that they may not diverge silently in the meantime.

## What was hardened now (Stage 1, without merging the subsystems)

- The canonical builder's active-record swap (`UPDATE active=0; INSERT
  active=1`) now runs inside a single `BEGIN IMMEDIATE` transaction, so a
  concurrent run blocks rather than racing the swap (Helland's TOCTOU).
- The defeater **row contract** (`target_kind` ∈ 8 kinds, `defeat_kind` ∈
  {rebutting, undercutting}) is now fixed identically in both the canonical
  builder and its verifier, matching the vocabulary the overseer builder
  already enforces — so when defeater extraction lands, the two builders cannot
  disagree about what a defeater is.

## Open hazard (not introduced here, flagged for David)

The production DB's `artefact_registry` row count changed (3 → 13) between the
panel review and this session with no AEPL build responsible (the AEPL builder
does not touch that table; verified 13→13 across a clean rebuild). The most
likely cause is another worker (Codex/AG) running overseer activity against the
shared `160sp/pipeline_lifecycle_full.db`. This is a live instance of the
shared-database concern: **writers from different subsystems are mutating one
production DB file with no coordination.** Worth a coordination-protocol rule
before Stage 2.
