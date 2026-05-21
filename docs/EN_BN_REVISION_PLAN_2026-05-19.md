# Revision Plan — The Epistemic Network, the Bayesian Layer, the Warrant Model, and the Projection Between Them

*David Kirsh, 2026-05-19. An architecture plan. It follows from `docs/EN_OVER_BN_PANEL_READING_2026-05-19.md` §8, which produced ten design obligations from the Thagard / Haack / Cartwright reading plus three concessions from the Pearl critique. This document turns those obligations into a concrete revision of the Epistemic Network schema, the warrant model, and the Bayesian layer — and answers the question the obligations force: how is the projection from the EN to a BN now altered?*

---

## 1. Why this plan exists, and the one idea that organises it

The panel reading left ten design obligations and three concessions. Taken individually they look like ten schema tickets. Taken together they are one idea, and the plan is easier to hold if the idea is stated first.

**The Bayesian layer is not a peer of the Epistemic Network. It is a projection of it.** A BN is what you get when you take the EN — a web of warranted, scoped, concept-indexed, defeasibly-supported belief — and collapse it onto the subspace a probabilistic causal model can hold: variables, directed edges, and parameters. The collapse is lossy. Before the panel reading, the loss was unprincipled — credences were read off the EN as priors and the rest was dropped without a rule. After the panel reading, the loss must be *specified*: every EN node type and edge type needs a defined projection rule, and several of the new EN structures change not merely what is dropped but what the BN *is*. That reframe — BN as a typed, setting-indexed, concept-version-locked, cycle-cut projection of the EN — is the spine of this plan, and §6 and §7, on the projection itself, are its centre. The user asked specifically how the projection is altered; the honest answer is that it is altered enough to be worth rebuilding deliberately rather than patching.

A scope note. "The EN" is, concretely, the `epistemic_v2` layer in `ae.db` — the credence column, the `constraints` table, the theory nodes with entrenchment, the coherence score and tension count — together with the `substitution_graph.db` constructs and measures. The Atlas also already has an **ontology layer** — `data/ka_payloads/topic_ontology.json`, schema v1.0: the controlled vocabulary of 9 IV roots, 8 DV roots, 137 topic nodes and 1,503 cross-relations, with authority split between the Tagging_Contractor (IV side) and Outcome_Contractor (DV side), and surfaced by the Layer-G Ontology inspector (`ka_journey_ontology.html`). This plan upgrades that existing ontology; it does **not** add a parallel concept layer (see §2). "The BN" is the causal-and-probabilistic layer; in the present system it is partly implicit (credence plus the `constraints` relations carry probabilistic content) rather than a separate materialised artifact. This plan applies whether the BN is materialised on disk or computed on demand; the projection it specifies is the same either way.

---

## 2. Revising the Epistemic Network — node types

The EN today has two node kinds that matter: *belief* nodes (findings, claims) and *theory* nodes. The panel reading at first looked as though it required new node types for *capacities* and *concepts*. It does not — and the correction matters, because the Atlas already carries that material. The concept scheme is the existing ontology (`topic_ontology.json`, §1); the disposition-and-measure material is in the mechanism inventory and the `substitution_graph.db`. So this section revises *two* node kinds (belief, theory), adds *one* genuinely new bookkeeping kind (inference), and otherwise specifies an **upgrade to the existing ontology** and a **promotion of existing records** — not two new layers. An earlier draft of this plan called capacity and concept "new node types"; that overstated them and risked duplicating structure the Atlas already has. The corrected framing follows.

**Belief nodes (revised).** Findings and claims, as now, but with two additions. First, an `epistemic_anchoring` field — Haack's clue/entry distinction: a belief is `clue` (an empirical finding anchored, defeasibly, in observation) or `entry` (a claim believed largely through its connections to other beliefs). The `warrant_class` field already half-carries this (`empirical_association` versus `mechanism` versus `review`); `epistemic_anchoring` makes it explicit and projection-relevant. Second, every belief node references the ontology nodes it predicates over (see the ontology upgrade below), so that a conceptual revolution can be detected as a change in which ontology concepts a stable belief points at.

**Theory nodes (revised).** As now, but the single `entrenchment` score splits into two: `entrenchment_evidential` (how much independently-secured warrant stands under the theory, and how much else depends on it) and `entrenchment_affective` (how much the field is attached to it, inferred from citation sentiment, defence behaviour, commercial and institutional stake). Thagard's point: a theory entrenched evidentially and a theory entrenched only affectively are different epistemic states with different prognoses, and only the first may project to the BN (§6).

**Capacity role — a promotion of existing records, not a new node type.** Cartwright's correction. A *capacity* is the stable dispositional fact — "nature views have the capacity to support attentional restoration" — that travels from setting to setting even when the *regularity* it produces does not. The Atlas does not need a new `capacity` table: it already has the mechanism inventory (the 70-to-71-item neuroscience-mechanism set), the IV roots of the ontology, and the `substitution_graph.db` constructs. A capacity is a **role** that selected records of those existing structures take on when an explicit, warranted invariance claim is attached — concretely, an `invariance_warrant` field plus an IV→effect pairing on a mechanism-inventory or construct record. A finding node remains the manifestation of one or more capacities *inside a particular nomological machine* (a setting-and-population). The capacity-role records are the part of the EN that projects to the *structural* part of the BN; finding nodes project to the *parametric* part (§6). Naming the role earns its keep at projection time — the projection must read, off existing records, which carry an invariance claim — not as a new layer.

**Concept layer — the existing ontology, upgraded, not a new table.** Thagard's correction. The Atlas already holds its concept scheme as a kind-hierarchy maintained separately from the belief graph: `topic_ontology.json` is exactly that — IV roots, DV roots, topic nodes, and the framework-and-measure hierarchy, separate from `ae.db`'s belief graph. The panel reading does not require a second concept table; it requires the existing ontology to gain three things its own Ontology-inspector page already names as missing — node-level *provenance* (who added a node, when), *deprecation status*, and *disputed-concept* status — plus a *version history*, so that a conceptual revolution (a category boundary moving) is a logged `concept_revision` event rather than a silent edit. The BN's variable set is a projection of the ontology *at a version*; when the ontology reorganises, the BN must be re-projected, not re-parametrised (§6). The work here is an ontology upgrade, not a new layer.

**Inference nodes (new, bookkeeping).** Cartwright's two-node correction requires that the step from an as-tested claim to a scope-adjusted claim be itself an object that can carry warrant. So a scope-transport, a mechanism-to-finding manifestation, and any other warrant-bearing inference becomes a first-class `inference` node with its own warrant packet, rather than a bare edge. This is what lets the EN say "the finding is well warranted, and the *generalisation of it* is not."

---

## 3. Revising the Epistemic Network — edge types

The `constraints` table today carries roughly two relations — `instantiates` and `supports`, with strengths. The panel reading requires a typed edge vocabulary, because coherence must be *computed over typed explanatory relations*, not counted, and because the projection rule depends on the edge type. The proposed edge types, grouped by how they will project:

| Edge type | Meaning | Projects to BN as (preview of §7) |
|---|---|---|
| `explains` / `is_explained_by` | A explanatorily accounts for B | candidate causal/dependency edge |
| `manifests` | finding is a manifestation of a capacity | the structural edge — capacity → finding parameter |
| `supports` / `is_supported_by` | A raises the warrant of B (evidential) | prior strength, not an edge |
| `scope_transports_to` | as-tested claim → scope-adjusted claim, via an inference node | a transportability adjustment (selection diagram) |
| `is_analogous_to` | A is analogous to B | does **not** project; informs prior-setting only |
| `contradicts` | A and B cannot both hold | a mutual-exclusion constraint, not an edge |
| `competes_with` | A and B explain the same thing | a prior-coupling constraint, not an edge |
| `undercuts` | A defeats the warrant-link of B without bearing on B's truth (Pollock undercutting defeater) | a likelihood discount on B, not an edge |
| `rebuts` | A is evidence B is false | ordinary counter-evidence — conditioning |
| `depends_for_security_on` | B's warrant depends on A being believed independently of B | the cycle-detection edge — governs where projection must cut |

The last edge type is the operational form of Haack's *independent security*. It is the edge the projection inspects to find circular support (§6).

---

## 4. Revising the warrant model

The warrant packet today carries `mechanism_warrant`, `entrenchment_warrant`, `meta_analytic_warrant`, `confounding_warrant`, a defeat status, and supporting/contradicting counts, and it yields a `credence_value`. Four revisions.

**Warrant is not a probability — separate the credence from the warrant object.** Haack's sharp point, conceded in the panel reading: the warrant of a claim and the warrant of its negation do not sum to one, because inconclusive evidence leaves both unwarranted. The schema must therefore stop treating the warrant packet as if it obeyed the probability axioms. Concretely: keep `credence_value` as a derived, probability-like scalar for the places that need one (display, the BN projection), but make the *warrant packet itself* a structured object that tracks **support and defeat separately and does not net them to a complemented number** — Pollock's defeasible-reasoning algebra rather than the probability algebra. The credence is a projection of the warrant packet, exactly as the BN is a projection of the EN; the warrant packet is the primary object.

**Add the third dimension — independent security.** The warrant packet today has supportiveness (the warrant signal — Keynes's balance) and comprehensiveness (the supporting/contradicting counts and meta-analytic warrant — Keynes's weight). Add `independent_security`: a measure of how far the supporting evidence is believed *independently of the claim it supports*. It is computed from the `depends_for_security_on` edges — a belief whose supports trace back, through a cycle, to itself scores low. This is the dimension that guards against co-validated literatures, and it is also the dimension the projection needs in order to produce a legal acyclic BN (§6).

**Add the genuineness-of-inquiry channel.** A new sub-object, `inquiry_genuineness`, with coarse, auditable fields: pre-registered (yes/no/partial), declared competing interests, whether the design could in principle have disconfirmed the authors' hypothesis, and a single `pseudo_inquiry_flag` for the egregious cases Haack's Peircean argument is aimed at. This does not enter `credence_value` directly; it enters the *projection* as a likelihood discount (§6), so the BN never inherits the field's motivated reasoning at full weight.

**Make the warrant components typed by what defeats them.** Each warrant component should record whether the relevant defeaters are *rebutting* (counter-evidence) or *undercutting* (a broken inference — confounds, population bias, demand characteristics). The current `confounding_warrant` is an undercutting channel and should be named as one; the EN should be able to report, per belief, how much of its discount is rebutting and how much undercutting, because the two project to the BN completely differently (§7).

---

## 5. Revising the Bayesian layer — the BN as a projection

The BN is not revised by editing it. It is revised by **redefining how it comes to exist.** Four properties, each forced by a panel obligation.

**The BN is setting-indexed.** Because capacities travel and regularities do not (Cartwright), there is no such thing as "the BN" — there is `BN(setting)`, a projection evaluated at a named nomological machine: a population, a setting type, an exposure regime. The capacity layer of the EN is invariant across the whole family `{BN(s)}`; the finding layer parametrises each member. Projecting therefore *requires* a target setting as an argument. Asking for "the BN" without a setting is, after this revision, a type error.

**The BN is concept-version-locked.** Because the concept hierarchy can reorganise (Thagard), a BN's variable set is a projection of the concept hierarchy *at a version*. Every materialised or computed BN carries the `concept_hierarchy_version` it was projected against. A conceptual revolution invalidates the BN — not its numbers, its *variables* — and forces a re-projection. The system must refuse to incrementally update a BN across a concept-revision event.

**The BN is acyclic by a cut, and the cut is warranted.** EN support can be circular; a DAG cannot. The projection must break every support cycle, and the `independent_security` scores decide *which edge in the cycle is cut* — you cut the weakest-independent-security link. The BN therefore inherits, as metadata, the list of cuts the projection made, so that a BN result can be reported with the caveat "this conclusion depends on a circularity broken here."

**The BN is laundered.** Affective entrenchment, coherence, analogy, and raw genuineness-of-inquiry are EN-only. The projection drops affective entrenchment and coherence entirely, converts genuineness into a likelihood discount, and uses analogy only to inform prior-setting. The BN that results is a *cleaned* object — the field's sociology has been left behind on the EN side of the boundary. This is a feature: the projection is the membrane that keeps motivated reasoning out of the causal model.

One consequence worth stating plainly: the projection can **refuse**. If a support cycle cannot be cut without dropping below an independent-security floor, or if the ontology is mid-revolution, or if no capacity-role records underwrite the requested setting, the projection returns *no valid BN* rather than a misleading one. The EN can therefore tell you when a Bayesian model is not yet warrantable — which is itself a finding, and one the old unprincipled projection could never deliver.

---

## 6. How the projection to the BN is altered — the core analysis

This is the question the plan exists to answer. Take the projection obligation by obligation; in each case state what the new EN structure changes about the map down to the BN.

*A note on terms, per the 2026-05-19 correction (see §2).* Where this section says "capacity node" it means a record of the existing mechanism inventory or `substitution_graph.db` that carries the capacity **role** — an `invariance_warrant` plus an IV→effect pairing — not a row in a new `capacity` table. Where it says "concept hierarchy" or "concept-version" it means the existing **ontology** (`topic_ontology.json`) and its version. The projection logic described below is unchanged by the correction: what changes is only that the projection reads from the *upgraded ontology* and the *promoted records*, not from new tables. The phrase "concept-version-locked" therefore means "locked to a version of `topic_ontology.json`."

**Typed explanatory edges → a typed projection, not a flat read-off.** Previously every EN relation was treated, loosely, as something that became a BN edge or a prior. Now each edge type has a fixed treatment (the table in §7). The decisive change: `contradicts` and `competes_with` do **not** become BN edges — they become *constraints over the projected priors* (a mutual-exclusion region; a coupling that keeps competing hypotheses' priors normalised against each other). `is_analogous_to` does not project at all. So the projection is no longer "EN graph minus warrant equals BN graph." The EN graph and the BN graph are different graphs, related by a typed rule.

**Capacities versus findings → the projection now produces a family, and splits structure from parameter.** This is the largest single change. A capacity node projects to the *structural* part of `BN(setting)` — the edges, the form of the structural equations — and it does so identically for every setting, because capacities are invariant. A finding node projects to the *parametric* part — the CPT values — and it does so differently for each setting, because a finding is a capacity's output through a particular nomological machine. Therefore one EN projects to a *family* of BNs sharing structure and differing in parameters. "Projecting to the BN" is now "projecting the shared structure once, then projecting the parameters for the requested setting." The old projection conflated the two and so silently treated lab parameters as world parameters.

**Two-node travelling claims → the projection's scope step is a transportability computation.** Because the as-tested claim and the scope-adjusted claim are now two nodes joined by a warranted `scope_transports_to` inference, projecting a finding to `BN(target_setting)` is a two-step operation: project the as-tested finding, then apply the scope-transport inference to obtain the parameter for the target. And the content of that inference — *which* differences between source setting and target setting are causally relevant — is exactly Pearl's *selection diagram*. So the EN supplies, as the `scope_transports_to` inference node, the selection diagram that Pearl's transportability calculus consumes; the projection's scope step *runs* that calculus. This is the precise point at which the EN and Pearl's framework engage rather than compete: the EN does not replace transportability, it *furnishes its premise*. The warrant on the inference node becomes the warrant of the transport — and if that warrant is low, the projection still produces `BN(target)` but flags the target parameters as weakly transported.

**Independent security → the projection's cycle-cut, and the precondition for a legal BN.** A BN must be acyclic. EN support can cycle (F supported by E, E believed because of F). The projection cannot proceed until every such cycle is cut, and the `independent_security` / `depends_for_security_on` structure is what tells it where: cut the edge of least independent security. So independent security is not a refinement of the projection — it is the property that makes a legal projection *possible at all*. Without it, the projection either fails to be a DAG or cuts cycles arbitrarily and hides the fact. With it, the BN comes with an explicit, warranted record of every circularity that had to be broken to bring it into existence.

**Genuineness of inquiry → a likelihood discount applied at the membrane.** A finding from pseudo-inquiry has, by Haack's argument, a possibly-flawless *d* and *p*. The BN, fed *d* and *p*, would inherit that finding at full evidential weight. The projection now interposes a genuineness discount: the `inquiry_genuineness` object is converted, at the EN→BN boundary, into a multiplicative attenuation of the finding's likelihood contribution. The BN never sees the undiscounted finding. The sociology is laundered at the membrane.

**Rebutting versus undercutting defeat → two different projection operations.** This is the precise, corrected answer to the original essay's confound question. A *rebutting* defeater projects into the BN natively — it is counter-evidence; you condition on it. An *undercutting* defeater — a suspected confound, a population-bias worry — projects differently: it does **not** become a node or a piece of evidence; it becomes a *discount on the warrant of the projection itself*. Concretely, an undercutting defeater on finding F lowers the confidence with which F's parameter is asserted in `BN(setting)` — it widens the parameter's credible interval, or, in the limit, it triggers the projection to mark that parameter `weakly_warranted`. The BN thereby carries, per parameter, a second-order tag inherited from the EN's undercutting defeaters. This is how the confound finally reaches the BN: not through *d* and *p*, which never carried it, but as a projection-time attenuation of the parameter's warrant. Pearl is right that a *named, modelled* confound is a BN node and the do-calculus handles it; the EN's contribution is the *unnamed, suspected* confound, which the projection converts into warrant-attenuation on the parameter rather than into a node.

**Affective entrenchment and coherence → dropped at the membrane.** Neither projects. Affective entrenchment is a fact about the field's psychology, not the world; coherence is an EN-only diagnostic and, per Cartwright, must never become an objective function. The projection drops both. Only *evidential* entrenchment projects, and it projects as prior strength — how peaked, how resistant to a single contrary datum, a prior should be.

**The round trip — what the BN sends back, and its warrant ceiling.** Projection is not one-way. A BN, once projected, produces results — a posterior, an intervention prediction, a counterfactual. Each result is itself a new belief and must be lifted back into the EN. The governing principle: **a BN-derived belief cannot be better warranted than the projection that produced the BN.** Its warrant is bounded above by the conjoined warrant of the capacity structure, the setting's parameters, the scope-transport inferences, and the cycle-cuts the projection had to make. A confident posterior produced from a weakly-warranted projection re-enters the EN as a weakly-warranted belief, however sharp the number. This ceiling is the EN's protection against laundering a guess into a fact by routing it through a probability calculation.

The summary of the alteration: the projection was a read-off and is now a *typed, setting-indexed, concept-version-locked, cycle-cutting, sociology-laundering, refusable transformation with a transportability step and a warrant ceiling on its return path.* Every clause of that sentence is one of the panel's obligations made operational.

---

## 7. The projection rule table

The reference artifact Codex will implement. Each EN element, its projection treatment, and the obligation it discharges.

| EN element | Projects to BN as | Discharges |
|---|---|---|
| capacity-role record (mechanism-inventory / substitution-graph record carrying `invariance_warrant` + IV→effect pairing) | structural edge + structural-equation form (setting-invariant) | Cartwright — capacities travel |
| finding node | CPT parameter for the requested setting | Cartwright — regularities are local |
| `explains` / `manifests` edge | causal/dependency edge | Thagard — explanatory relations |
| `supports` edge | prior strength on the supported node | (existing) |
| `scope_transports_to` inference | transportability adjustment; the inference node *is* the selection diagram | Cartwright + Pearl concession |
| `contradicts` edge | mutual-exclusion constraint over priors (not an edge) | Thagard — typed coherence |
| `competes_with` edge | prior-coupling/normalisation constraint (not an edge) | Thagard |
| `is_analogous_to` edge | does not project; informs prior-setting only | Thagard |
| `undercuts` (undercutting defeater) | warrant-attenuation on a parameter (widened interval / `weakly_warranted` tag) | the corrected confound answer |
| `rebuts` (rebutting defeater) | counter-evidence; conditioned on natively | Pollock; Pearl concession |
| `epistemic_anchoring = clue` | evidence node / near-fixed observed node | Haack — clues |
| `epistemic_anchoring = entry` | derived node / prior | Haack — entries |
| `entrenchment_evidential` | prior strength / peakedness | Thagard — split |
| `entrenchment_affective` | dropped at the membrane | Thagard; Pearl — no sociology in the model |
| `independent_security` low + a support cycle | cycle-cut; weakest link removed; cut logged on the BN | Haack — independent security; DAG legality |
| `inquiry_genuineness` | multiplicative likelihood discount at the membrane | Haack — genuine vs sham inquiry |
| coherence score, tension count | dropped; EN-only diagnostic | Cartwright — coherence is not a maximand |
| ontology (`topic_ontology.json`) at version V | the BN variable set; BN locked to V | Thagard — concepts move |

---

## 8. Sequencing

Five phases, ordered by dependency. Each phase is independently testable.

**Phase 1 — warrant model.** Split the warrant packet from `credence_value`; add `independent_security`; add `inquiry_genuineness`; type defeaters as rebutting versus undercutting; split `entrenchment` into evidential and affective. Schema migration on `ae.db` `epistemic_v2`. No projection change yet — this phase just makes the EN carry the new fields. Lowest risk; do first.

**Phase 2 — edge typing.** Migrate the `constraints` table to the typed edge vocabulary of §3. Back-fill existing `instantiates`/`supports` rows into the new types. Add `depends_for_security_on` edges (these may need extraction — see Phase 5).

**Phase 3 — ontology upgrade and the capacity role.** No new `capacity` or `concept` tables (see §2). Upgrade `topic_ontology.json` with node-level provenance, deprecation status, disputed-concept status, and a version history; add the `invariance_warrant` field plus the IV→effect pairing that promotes selected mechanism-inventory and `substitution_graph.db` records to the capacity role; link finding nodes to the ontology concepts they predicate over and to their capacity-role records; add `inference` nodes for scope-transport. This is the largest change and the one most worth a dry-run on a corpus subset first — and it touches the contractor-owned ontology, so the Tagging_Contractor and Outcome_Contractor authority model must be respected (the upgrade adds fields; it does not seize authority over node content).

**Phase 4 — the projection.** Implement the §7 rule table as an actual `project(EN, target_setting, concept_version) → BN | refusal` procedure. This is where the BN stops being implicit and becomes an explicit, derived, setting-indexed artifact. Includes the cycle-cut, the membrane (laundering + genuineness discount), the transportability step, and the warrant-ceiling on the return path.

**Phase 5 — extraction back-fill.** The new fields are only as good as what populates them. AG's substitution-graph extraction pass and the V7-complete pass must be extended to extract: independent-security signals (does a finding's support trace back to itself), genuineness-of-inquiry signals (pre-registration, interests), capacity-versus-regularity distinctions, and concept-boundary events. This runs last because it depends on the schema (Phases 1–3) existing, and it is continuous thereafter.

Phases 1 and 2 can proceed in parallel. Phase 4 depends on 1–3. Phase 5 depends on 1–3 and continues indefinitely.

---

## 9. Open decisions for DK

1. **Materialise the BN, or compute it on demand?** The projection is now well-defined enough to be run lazily — `BN(setting)` computed when asked. Materialising a family of BNs is storage-heavy and stale-prone. Recommendation: compute on demand, cache by `(setting, concept_version)`. DK to confirm.
2. **The independent-security cut policy.** When a support cycle must be broken, "cut the weakest-independent-security link" is the default. But sometimes every link in a cycle is weak. Fallback options: refuse to project that sub-graph; or project it with a loud `circular_support` warning. Recommendation: refuse for any BN that will inform a student deliverable; warn for exploratory views. DK to confirm.
3. **Capacity extraction is hard.** Distinguishing a capacity from a regularity is a genuine act of scientific judgement, not a parse. It may need its own AG operator prompt and possibly panel input. DK to decide whether capacity extraction is in scope for the first build or deferred, with `mechanism` records standing in until it lands.
4. **Concept-revolution detection.** Logging `concept_revision` events automatically is ambitious. A cheaper first version: flag candidate revolutions (a stable belief whose predicated concepts' jingle-jangle warnings spike) for human review rather than auto-committing them. DK to confirm the cheaper version is acceptable for v1.
5. **Affective entrenchment is inferred, and the inference is delicate.** Citation-sentiment and defence-behaviour signals are noisy and could be unfair to a theory. DK to decide whether affective entrenchment ships as a displayed quantity or stays an internal projection-filter input only.

---

## 10. Risks

The schema migration touches `ae.db`, which AG's V7-complete run is currently writing to; Phase 1 must be sequenced around that run, not concurrent with it. The projection's refusal behaviour, if tuned too strict, could leave the student-facing surfaces with no BN to show; the refusal thresholds need calibration on real corpus subsets before they gate anything a student sees. Capacity extraction and concept-revolution detection are research problems wearing engineering clothes; the plan deliberately lets `mechanism` records and human-flagged revolutions stand in, so that the rest of the architecture does not block on them. And the deepest risk is conceptual rather than technical: the warrant model must not quietly drift back into being a probability — every place the code is tempted to net support and defeat into one complemented number is a place Haack's argument is being violated, and the review of Phase 1 should hunt specifically for that temptation.

---

## 11. Summary

The panel reading's ten obligations are, structurally, one instruction: stop treating the Bayesian layer as a peer of the Epistemic Network and start treating it as a *projection* of the EN — and then specify the projection. The EN gains capacity nodes and a separate concept hierarchy, typed explanatory edges, a warrant model with an independent-security dimension and a genuineness channel and an entrenchment split, and inference nodes that carry the warrant of a generalisation. The warrant packet stops pretending to be a probability. And the BN is redefined as `project(EN, setting, concept_version)` — a typed, setting-indexed, concept-version-locked, cycle-cutting, sociology-laundering, refusable transformation whose scope step is a transportability computation and whose results return to the EN under a warrant ceiling. The projection is altered in exactly the ways the panel's corrections require, and naming the projection as a first-class object is what makes those corrections implementable rather than merely admirable. It is also, not incidentally, the place where Pearl's calculus and the web of belief finally do their work together: the do-calculus runs inside `BN(setting)`; the EN decides which `BN(setting)` is warranted enough to be worth running it on.

---

*Companion to `docs/EN_OVER_BN_WEB_OF_BELIEF_THINKING_2026-05-19.md` and `docs/EN_OVER_BN_PANEL_READING_2026-05-19.md`. The §7 projection rule table and the §8 phases are intended to be actionable by Codex; the §9 open decisions are for DK before Phase 1 begins.*
