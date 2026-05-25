# Ruthless Panel Review — Article-Detail Epistemic Layer

**Date prompt written:** 2026-05-24
**Module under review:** `article_epistemic_layer.v1` (Stage 1 implementation + Stage 2–5 plan)
**Audience for the prompt:** a fresh AI agent (or human reviewer) running the panel; the agent should NOT have implemented the module and should treat it adversarially.
**Audience for the output:** David Kirsh, who needs a go / hold / no-go signal before promoting Stage 1 to a release gate and committing to Stage 2.

---

## 0. Purpose and Disposition

You are running a **ruthless** expert review of a module that someone — call them "the implementer" — already shipped. Your job is **not** to give a balanced retrospective. Your job is to find what is broken, what is fragile, what was waved past, and what will cost the project later. Treat hedges with suspicion. Treat self-congratulatory language with suspicion. Treat passing tests with suspicion (they only prove the implementer's own model is internally consistent).

You will simulate ten experts. **The rule is impersonation, not paraphrase.** Each expert has:

- Their own technical vocabulary and idioms. Use them.
- Their own published positions. Cite them by paper or book title, with year.
- Their own characteristic targets — what they have spent careers refusing to let pass.
- Their own characteristic blind spots — acknowledge them.

If you have not read enough of an expert's actual writing to impersonate them, **say so explicitly** in their voice ("I cannot fully reconstruct X's position here without consulting Y; what follows is my best reconstruction"), and use web fetches to pull primary sources before continuing. Do not fake citations. Do not invent quotes.

---

## 1. Required Pre-Work Before The Panel Speaks

Read these first, in order. Do not begin the panel until you have read all of them.

### 1.1. The controlling documents

- `docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md` — the spec the module claims to implement.
- `docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_SYNTHESIS_2026-05-23.md` — the prior panel's review that produced the spec.
- `docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_PANEL_BRIEF_2026-05-23.md` — the original brief.
- `docs/HANDOFF_EPISTEMIC_LAYER_IMPLEMENTATION_2026-05-23.md` — the implementation handoff.

### 1.2. The implementation

- `contracts/schemas/article_epistemic_layer.sql` (and mirror at `scripts/migrations/2026_05_23_article_epistemic_layer.sql`).
- `scripts/article_epistemic_layer_init.py`
- `scripts/build_article_epistemic_layer.py`
- `scripts/verify_article_epistemic_layer_contract.py`
- `tests/_article_epistemic_fixtures.py`
- `tests/test_article_epistemic_*.py` (six files)
- `tests/conftest.py` (fixture additions)
- `data/ka_payloads/article_epistemic_layer.json` (the end-to-end output payload)
- `TASKS.md` (look at the `Newly Added — 2026-05-23 (Article-Detail Epistemic Layer Stage 1)` section and the `AEPL-PHASE-3` through `AEPL-PNU-REPAIR-BACKLOG` rows).

### 1.3. The parallel track — read this even if it looks unrelated

A separate system, the **dependency overseer**, has its OWN Stage 1 builder at `overseer/article_epistemic_builder.py` plus governance tables (`llm_invocations`, `prompt_templates`, `source_packets`, `content_equivalence_checks`). Find them. The implementer's builder writes directly to `article_epistemic_*` tables; the overseer's builder writes through `artefact_registry` with fencing tokens and content hashes. **Two builders, one schema, no integration.** This is one of the largest unsurfaced risks; the panel must address it head-on.

### 1.4. Write the situation summary before the panel speaks

Before the first panelist opens their mouth, produce a self-contained summary in plain prose covering:

1. **What the module does today.** Describe the behaviour as if explaining to someone who will inherit it next quarter. What does running the builder produce? What does running the verifier prove and not prove? What does the sibling payload give a downstream renderer?
2. **Where it is going.** The four deferred phases (page render, release gate, Stage 2 LLM enrichment, PNU repair backlog) — what each one needs and what blocks it.
3. **Strengths, in three sentences.** No more.
4. **Promises that have been made implicitly by shipping this — the things that downstream code, downstream readers, and downstream agents will assume hold because Stage 1 exists.** This list matters more than the explicit promises in the spec. Look at the JSON schema in the sibling payload and ask: "what would a renderer plausibly assume from this shape?"
5. **Weaknesses you can name before any panelist speaks.**

Get this summary on the page **before** any panelist speaks. The panelists will then have something concrete to attack.

---

## 2. The Panel

Ten experts, chosen because their actual published work intersects the module's design decisions. For each panelist, before they speak, write a one-paragraph reminder to yourself of: (a) one or two of their canonical works, (b) the technical claim they are most famous for defending, (c) one position they hold that the module probably violates. **Look up at least one primary source per panelist if you are uncertain.**

The panel:

1. **John L. Pollock** — defeasible reasoning, OSCAR, *Cognitive Carpentry* (1995), the rebutting / undercutting / no-reason distinction. He will read the module's `defeaters` component and ask whether you have implemented defeat in the technical sense or merely a count.
2. **Deborah G. Mayo** — error-statistical philosophy of science, *Statistical Inference as Severe Testing* (2018), the severity principle. She will ask whether `evidence_strength` represents anything that has been *severely tested* or merely arithmetic on counts.
3. **Susan Haack** — foundherentism, *Defending Science—Within Reason* (2003), the crossword-puzzle metaphor. She will examine the status vocabularies and ask whether the system can distinguish coherent-but-unwarranted from warranted-but-incoherent and whether the categories degenerate under pressure.
4. **Yolanda Gil** — W3C PROV co-chair, provenance for AI-assisted science. She will read `provenance_summary` and `provenance_json` and ask whether the module satisfies the W3C PROV-DM minimum (Entity, Activity, Agent, with `wasGeneratedBy`, `used`, `wasAttributedTo`) and whether anything can actually be replayed.
5. **Emily M. Bender** — *On the Dangers of Stochastic Parrots* (2021), the form-vs-meaning distinction, the Octopus Test. She will go after the Stage 2 plan: any LLM-generated "warrant explanation" or "rebuttal synthesis" is by construction not a representation of anything in the article and the layer's whole epistemic posture is at risk of laundering form as meaning.
6. **Pat Helland** — Amazon, *Life Beyond Distributed Transactions* (2007), *Data on the Outside Versus Data on the Inside* (2005), immutability and identity. He will read the SQLite schema and ask about concurrent writers, fencing tokens, the partial unique index race, and what happens when two builders disagree about which row should be active.
7. **Barry Smith** — Basic Formal Ontology, *Beyond Concepts* (2018), realist ontology, the critique of "concept" as a category. He will read the seven component types and the status vocabularies and ask whether the categories are carving the world at the joints or whether they will need to be renamed every six months as new evidence types are encountered.
8. **Carole Goble** — FAIR principles, *myExperiment* and Common Workflow Language, scientific data curation at scale. She will read the build pipeline and ask whether anyone other than the implementer can reproduce it, whether the inputs are FAIR, and whether the payload schema is FAIR.
9. **Hyrum Wright** — Google, *Software Engineering at Google* (2020), Hyrum's Law ("with a sufficient number of users, all observable behaviours of your contract will be depended on"). He will treat the sibling payload JSON as a public API and ask which fields are now load-bearing forever, and what happens to downstream consumers when the spec evolves.
10. **Marc Brooker** — AWS, builder of DynamoDB and S3 metadata layers, blogger on formal methods at scale, *Surprising Scalability of Multitenancy* (2023). He will look at the operational story: what does this look like when the corpus grows to 10× or 100×, what does failure look like at 3am, what is the runbook when the verifier reports `payload_hash_recomputes` fail in production, and what does it mean that 758 of 760 records are currently blocking on `pnu_requires_repair`.

That's ten. If you find you cannot impersonate a panelist with enough fidelity to be useful, replace them with someone whose work you do know — but tell David in the synthesis that you swapped them and why. Do not pad the panel.

---

## 3. Rounds

### Round 1 — Read the Room (one paragraph per panelist)

Each panelist, in voice, gives a brief read of the module: what it does, where it is going, one strength they will acknowledge, one promise they will not yet accept, one weakness they can already see from the spec + summary alone. **No more than 150 words per panelist.** Brevity here forces precision.

### Round 2 — Shred the Implementation (the meat of the review)

Each panelist takes the floor in turn and tears into the implementation. **They must cite by file and line where possible.** No high-level platitudes. If Pollock says the defeater model is broken, he must name the table column or the builder function that is broken and explain in defeasible-reasoning terms what is missing. If Helland says the schema has a concurrent-writer hazard, he must name the index, the SQL, and the race.

Pre-loaded shred targets to ensure no panelist glides past them. Each must be addressed by at least one panelist; the simulating agent should distribute them.

- **The two builders.** `scripts/build_article_epistemic_layer.py` and `overseer/article_epistemic_builder.py` produce overlapping content via different write paths. The implementer's builder bypasses `artefact_registry`, fencing tokens, and content-hash tables. The two will drift. Which panelist owns this? (Helland and Wright are the obvious candidates.)
- **`make_build_run_id` race.** The fallback path uses `datetime.now().microsecond` when no DB connection is available. Two dry-run builds in the same microsecond collide. Tests use this path. (Brooker.)
- **Partial unique index on `active=1`.** The "exactly one active record per (paper, schema)" guarantee depends on a partial unique index plus an `UPDATE…SET active=0; INSERT…active=1` pattern in `persist_record`. Under concurrent writers without a transaction-scoped lock, this is a TOCTOU race. (Helland.)
- **Defeater component does not implement target-specificity.** Spec §8 requires defeaters to be target-specific (claim / warrant / method / measurement / interpretation / generalizability / mechanism / application). The builder writes `rows: []` with at most a `no_defeater_basis` string. There is no target-kind field. (Pollock — this is the canonical critique.)
- **Primary-claim sort key.** The `select_primary_claim` rule order is documented in spec §8 but the tie-breaker chain in `build_article_epistemic_layer.py:select_primary_claim` collapses on identical `support_count + attack_count + credence + index`. Identical canonical text *is* the final tiebreaker but identical text means the rows ARE the same claim, so the choice is undetermined when two distinct claims hash to neighbouring values. (Haack on the crossword-puzzle: do two equally-coherent fragments resolve to one choice deterministically?)
- **`unreviewed` vs `not_required` confusion.** The status vocab distinguishes them but the builder writes `unreviewed` for some `deterministic_derived` components and `not_required` for others, inconsistently. Which is it? (Haack, Smith — category hygiene.)
- **The `no_llm_source_mode` check is grep-based.** `verify_article_epistemic_layer_contract.py:check_forbidden_provider_imports` looks for `import openai` etc. in the builder source. Rename the import, base64-encode it, or call out to a subprocess and the check is silent. (Wright on Hyrum's Law applied in reverse: the check is a contract you cannot actually enforce.)
- **`input_fingerprint` does not cover `schema_version` or `builder_version`.** Spec §6 says `input_fingerprint` covers all support-set hashes "for a record." Bumping the builder version without changing inputs produces identical fingerprints — silent regression. (Gil on provenance completeness.)
- **`payload_hash` includes `release_eligible` but the value is always 0 in Stage 1.** This means any future Stage that flips `release_eligible` to 1 changes the hash and invalidates everything downstream that compared hashes. Is that intended? (Wright.)
- **Canonical JSON uses `ensure_ascii=False`.** Python's `json.dumps(ensure_ascii=False)` emits raw Unicode; cross-system reproducibility depends on the file being read with the same encoding. SQLite stores TEXT as the connection's encoding. Hash drift is possible across locales. (Brooker on cross-host reproducibility.)
- **`pnu_requires_repair` blocks 758/760 papers.** The implementer surfaces this as "we are surfacing it, not laundering it." The panel should ask: surfaced *to whom*, and *what is the runbook*? Is this a successful implementation or a successful demonstration that the upstream pipeline is broken and downstream rendering cannot ship? (Mayo, Brooker, Goble — three different angles.)
- **The completion queue dedupes by `(paper_id, component_type, reason)`.** Re-running with a higher severity does not overwrite the existing lower-severity row. A `warning`-severity item that becomes `blocking` on the next build will silently remain `warning`. (Mayo on missing severity escalation.)
- **`source_artifact_id = "article_details_json:{paper_id}:{field}"`.** This couples identity to the file path. Renaming `article_details.json`, moving it, or sharding it across files invalidates all support-set hashes. (Gil on provenance identity persistence; Helland on data on the outside.)
- **Tests pass against `complete_record` fixtures whose `requires_repair` is `False`, but the production corpus has 758/760 with `requires_repair=True`.** Coverage gap: the happy path is the rare path. (Brooker, Mayo.)
- **Public payload field `release_eligible: bool` vs DB `release_eligible: 0`.** JSON emits `false`, DB stores `0`. The payload_hash recomputation function in the verifier rebuilds from the DB's `0`, but the public payload renderer sees `false`. This works today because Python's `False == 0` but it is a footgun. (Brooker.)
- **No `verification_status` field on records.** A record can be created, persisted, never verified, and still appear in the active set. The verifier writes events but does not update the record. So the `review_status: machine_verified` value in the vocab is unreachable in Stage 1. Why is it in the vocab? (Smith, Haack on dead categories.)
- **`science_summary_core_finding` rule 4 produces a `primary_claim` with no `credence` and `source_credence=null`, but `claim_id` is computed from the canonical text only.** Two different papers with the same `core_finding` text get the same `claim_id` prefix beyond the paper_id. This is structurally fine because `claim_id` includes the `paper_id` — but the test that asserts identity-stability across normalisation does not test the cross-paper case. (Smith.)
- **The fixture `record_with_attack_count_no_defeaters` sets the *primary claim*'s per-claim `attack_count` to 4 in order to trigger the count-reconciliation path.** That is the test exercising the verifier. But the *builder* computes `attack_count_argumentation` from `argumentation.attack_edge_count`, which in the production corpus is 0 for nearly every paper. So the production builder *almost never* exercises the path the test exercises. (Mayo on severity of testing: passing this test tells you almost nothing about production behaviour.)

### Round 3 — Shred the Plan (Stages 2–5 and AEPL-PNU-REPAIR-BACKLOG)

Each panelist now shifts to the forward-looking plan. Pre-loaded targets:

- **Stage 2 LLM enrichment governance via subscription-CLI only** — what enforces it at runtime, not at lint time? (Bender, Wright.)
- **Grounding verifier** — what is the actual verification algorithm? Citation matching? Entailment? Retrieval consistency? Hajishirzi-style attribution? The plan says "grounding verifier" the way an architect says "scalable." (Bender, Brooker.)
- **Source-packet manifest hashing** — how do you prove the manifest matches what the LLM actually saw? The LLM provider does not return the input it processed; it returns text generated from an opaque context window. The hash is of *your* manifest, not of *its* view. (Bender, Gil.)
- **Field-policy enforcement at write path** — but the Stage 1 builder does not go through `artefact_registry`. So whose write path is enforcing it? The overseer's? Then the implementer's builder needs to be rewritten on top of the overseer or be deprecated. (Helland, Wright.)
- **AEPL-PHASE-3 page rendering** — the spec §11 rendered verifier list (mobile overflow, console errors, network errors) is a Selenium-style runtime check. Who runs it? In CI? On every deploy? (Goble, Brooker.)
- **AEPL-PHASE-4 release gate** — twelve conditions. What is the gate's failure-mode behaviour: fail-closed, fail-open, page someone? (Brooker.)
- **AEPL-PNU-REPAIR-BACKLOG.** This is the real question. The system is doing what it was told to do, and 758 of 760 records are blocked by an upstream pipeline state. The panel must ask whether shipping Stage 1 as "complete" is honest or whether it is reporting completeness while the artefact is unusable. (Mayo — severe testing. Bender — what does the system actually *do for the reader*?)

Each panelist gives their forward-looking critique in their own idiom, at least 250 words. They must propose at least one *concrete* fix per critique. Vague gestures are not allowed.

### Round 4 — Cross-Talk (this is where the real signal is)

After the per-panelist rounds, run **at least three** cross-panelist exchanges. Pick the most generative disagreements and let them play out:

- **Pollock vs Bender** on whether Stage 2's "warrant explanation" can ever count as a defeater-aware representation of a warrant or whether it is by construction a fluent confabulation.
- **Helland vs Wright** on whether the two-builder problem is a versioning problem (Wright: pick one and deprecate the other now) or a topology problem (Helland: route both through a single write path).
- **Mayo vs Haack** on whether the `evidence_strength` component represents anything epistemically meaningful or whether it is bookkeeping dressed up as evidence.
- **Smith vs Goble** on whether the component-type taxonomy is realist enough to survive corpus expansion or whether it is FAIR-but-fragile.
- **Brooker vs Gil** on whether the provenance machinery scales — Gil wants more, Brooker wants the minimum that survives at 3am.

These are suggestions; let the dialogue go where the disagreement actually is. The cross-talk must produce **at least one specific change of mind** somewhere — a panelist conceding a point, refining a position, or escalating a concern. If everyone stays at their original position, you are not running the cross-talk hard enough.

### Round 5 — Go / Hold / No-Go

Each panelist votes:

- **GO** — the module is ready to promote to Phase 3 (page rendering). They state what they consider acceptable risk.
- **HOLD** — fix N specific items first, then promote. They list the items with file:line citations.
- **NO-GO** — the module's architecture or the plan's path forward has a defect that requires reconsideration, not a fix. They name the defect.

The default for ruthless reviewers is HOLD or NO-GO. GO requires explicit justification under that reviewer's framework.

---

## 4. Synthesis

After the votes, write a synthesis section in your own voice (as the agent running the panel, not as a panelist). The synthesis has the following shape and only the following shape:

### 4.1. Vote tally

Plain table: panelist | vote | dominant concern.

### 4.2. Blocking items

Numbered list. Each item:
- File, function, or design element implicated.
- Which panelist or panelists raised it.
- Why it blocks shipping.
- The minimum fix.
- The minimum test that would prove the fix.

### 4.3. Recommended spec amendments

Where the panel surfaced a problem that is not in the implementation but in the spec, list those amendments as proposed redlines to `docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md`.

### 4.4. Recommended plan amendments

Where the panel surfaced a problem in the path forward (Stages 2–5), list amendments to `TASKS.md` rows `AEPL-PHASE-3` through `AEPL-PNU-REPAIR-BACKLOG`.

### 4.5. Open questions to send back to David

The questions the panel could not resolve, framed for a human decision. No more than five. Each one must be specific enough that David can answer it in a sentence.

### 4.6. The single sentence

End with one sentence: the most important thing this panel said. Earn the sentence.

---

## 5. Disposition Rules (binding on the agent running this prompt)

- **No diplomatic preambles.** No "the team has done excellent work." Panelists open with the critique, not with a thank-you.
- **No false consensus.** If panelists disagree, surface the disagreement; do not paper over it in the synthesis.
- **No invented citations.** If you cite a panelist's paper or claim, you must have grounds for the citation. Use web search and fetch when uncertain.
- **No "AI panels" defaulting to mush.** If you find yourself writing "the panel agreed that thoughtful consideration is warranted," delete it and try again.
- **No exoneration by passing tests.** The tests prove the implementer's own model is internally consistent. The panel's job is to break that model.
- **The implementer is not in the room.** Do not soften critiques to spare feelings. The implementer wrote this prompt explicitly asking to be shredded; honour that.
- **One final discipline: ruthlessness is not snark.** Ruthlessness means "specific, file-cited, actionable, hard to deflect." Snark is the failure mode. If a panelist says "this is bad," ask "bad how, in your own framework's terms." Make them earn it.

---

## 6. What David Will Do With This Output

The output goes into the project's epistemic decisions log as `docs/AEPL_PANEL_RUTHLESS_REVIEW_OUTPUT_2026-05-24.md`. David will read the synthesis section first. If `4.2 Blocking items` is empty and `4.6 The single sentence` is bland, the panel did not earn its keep and David will rerun it with a different agent. If the synthesis is sharp and the blocking items are specific, David will treat them as binding constraints on the next sprint.

Earn your keep.
