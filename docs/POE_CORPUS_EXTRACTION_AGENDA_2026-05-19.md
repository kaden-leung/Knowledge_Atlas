# POE Corpus Extraction Agenda

*Project to-do — David Kirsh, 2026-05-19. Internal memo. Companion to `docs/POE_REVIEW_2026-05-19.md` (the literature review) and `docs/POE_TALK_OUTLINE_2026-05-19.md` (the talk).*

---

## Premise

The POE review identifies thirty-eight cases of shallow-versus-deep measurement in post-occupancy evaluation; the talk reduces those to fifteen first-person experiences. Eight of the items have a thin or absent presence in our current corpus extraction, and that thinness is not a coincidence: it tracks the disciplinary boundaries that the architecture-and-environmental-psychology literatures have been slow to cross. The corpus, as it stands, is strong on neuroaesthetic, biophilic, circadian-light, and acoustic-cognitive work and weak on the welfare-economic, adaptive-thermal, and indoor-air-chemistry literatures. This memo is the agenda for closing those gaps.

The agenda is intended for two readers: AG, who runs the substitution-graph extraction pass over the corpus, and CW (with Codex's assistance) for the topic-seeding and front-end work. The deliverables are paper seedings, search-term lists, and the candidate citations that should be added to the construct-to-measure graph and to the substitution skill's refusal logic. The eight items below are listed in roughly decreasing order of how badly they hurt the talk's credibility if they remain unaddressed.

---

## POE-EXT-1 — Adaptive thermal comfort and the affordances for adaptation

**Current corpus state.** One evidence row touches the adaptive thermal model (Humphreys' comfort-temperature-versus-outdoor-temperature figure, paraphrased). The de Dear-Brager 1998 ASHRAE *Transactions* paper and the 2002 *Energy and Buildings* paper are not in the corpus. The downstream literature — Parkinson, de Dear, and Brager (2020); Schweiker et al. (2020); Toftum (2010) on thermal comfort and personal control — is also absent. The talk leans on this material at experience five.

**Why it matters.** Adaptive thermal comfort is now in ASHRAE 55. It is the single most consequential reframing of thermal POE in the last forty years, and it changes what the practitioner should be measuring (adaptive opportunity, not air temperature within the comfort band).

**What to extract.** Twelve to fifteen papers, seeded by the de Dear-Brager 1998 paper. The substitution-graph relevant constructs are *adaptive thermal comfort*, *thermal pleasure / alliesthesia* (Cabanac 1971), *radiant asymmetry*, *mean radiant temperature*, *personal control over thermal environment*. Map each to its standard measurement (operative temperature plus globe thermometer for MRT; survey items for adaptive opportunity; the de Dear-Brager comfort-temperature regression for adaptive comfort itself).

**Owner.** AG substitution-graph extraction pass (per `prompts/AG_SUBSTITUTION_GRAPH_EXTRACTION_2026-05-18.md`). Seed papers added to the AG paper-acquisition queue.

**Acceptance.** All five constructs in the substitution graph with at least three measurement nodes each; the ae.db V2 schema reflects them with appropriate severity and entrenchment.

---

## POE-EXT-2 — Volatile organic compounds and particulate matter in indoor air

**Current corpus state.** Zero evidence rows mention VOCs or PM 2.5 directly. The Allen et al. (2016) COGfx paper is not in the corpus. Wargocki and Wyon's productivity-versus-ventilation studies appear only in a derivative way; Power et al. (2018) on air pollution and cognitive decline is absent.

**Why it matters.** This is one of the most policy-actionable POE findings in existence — the 1.7%-per-doubling-of-ventilation cognitive-performance result has been replicated across classroom and office settings — and one of the clearest cases where the standard CO₂ proxy is doing less work than the architects believe. The talk leans on this at experience seven.

**What to extract.** Fifteen to twenty papers. Seed with Allen et al. (2016); Wargocki et al. (2000); Wargocki and Wyon (2007a, 2007b); Bakó-Biró et al. (2012); Power et al. (2018); Tham et al. (2003). Constructs: *ventilation rate*, *perceived air quality*, *bio-effluent concentration* (olf/decipol), *VOC concentration*, *PM 2.5 concentration*, *cognitive performance under IAQ stress*. Measurements: CO₂ sensors (the current proxy), photo-ionisation detector VOC sensors, optical PM sensors, the COGfx test battery.

**Owner.** AG extraction pass; CW writes the substitution-graph node for *cognitive performance under IAQ stress* with explicit downstream links to PVT, COGfx-test battery, n-back, and Stroop.

**Acceptance.** Substitution graph contains at least the six constructs with their measurement nodes and substitutability relations; ae.db V2 mechanism warrant strengthens for the *CO₂ ↛ IAQ* link as the substitution graph populates.

---

## POE-EXT-3 — Implicit Association Tests applied to the built environment

**Current corpus state.** Zero evidence rows mention IAT or implicit association. The Greenwald 1998 paper and its successors are not in the corpus despite their forty-thousand-citation status in cognitive and social psychology. Schultz et al.'s (2004) Nature-IAT is absent. The methodological appendix of `160sp/ka_vr_measurability_content_2026-05-18.md` mentions IAT but the corpus underpinning is empty.

**Why it matters.** The talk's three-channel prescription rests on the implicit channel as the third leg of POE evaluation. If we tell our students or our audience that the IAT is the candidate instrument for the implicit channel and we have no corpus material to support that claim, we are operating on plausibility rather than warrant.

**What to extract.** Ten to fifteen papers. Seed with Greenwald, McGhee, and Schwartz (1998); Schultz, Shriver, Tabanico, and Khazian (2004); Fazio, Jackson, Dunton, and Williams (1995) on evaluative priming as an alternative implicit-measure paradigm; methodological critiques (Blanton et al. 2009 on the IAT's predictive validity); and any architecture-specific applications that exist (there are some isolated examples in environmental-policy research). The Nature-IAT and a Built-Environment-IAT are constructs to add.

**Owner.** CW (because the methodological framing matters and AG's extraction is paper-by-paper), with AG running the substitution-graph extraction once seed papers are added to the corpus.

**Acceptance.** A *Built-Environment-IAT* construct in the substitution graph, with links to evaluative priming and to the explicit attitude/satisfaction-survey nodes the IAT is meant to complement.

---

## POE-EXT-4 — Q-sort and preference-structure methods

**Current corpus state.** One evidence row mentions Q-sort, in a daylighting-bias study. Stephenson (1953) is absent; the modern Q-methodology textbooks (Watts and Stenner 2012; McKeown and Thomas 2013) are not in the corpus. The 20-sort and choice-based conjoint variants are also missing.

**Why it matters.** Same reason as POE-EXT-3: the talk's three-channel prescription names Q-sort and the 20-sort as the preference-structure methods. Without corpus support, the prescription is rhetorical. There is also a substantive payoff: Vischer's functional-comfort framework explicitly used Q-sort in some studies, and a substitution-graph node for *preference structure under functional comfort* is the natural way to encode this.

**What to extract.** Eight to twelve papers. Seed with Stephenson (1953); Watts and Stenner (2012); the Vischer (2007, 2008) functional-comfort papers; Louviere, Hensher, and Swait (2000) on stated-choice methods; Green and Srinivasan (1990) on conjoint analysis. The 20-sort task in our `ka_vr_measurability_content_2026-05-18.md` is a candidate for cross-reference.

**Owner.** CW. The Q-sort literature is small enough that direct seeding by CW is more efficient than waiting for the AG extraction pass to find it.

**Acceptance.** A *preference structure* construct in the substitution graph, with measurement nodes for Q-sort, 20-sort, conjoint analysis, and the *adaptive-preference elicitation* method (cross-referenced to POE-EXT-8 below).

---

## POE-EXT-5 — Experience-sampling and ecological-momentary-assessment methods

**Current corpus state.** Zero evidence rows mention experience sampling, ESM, day reconstruction, or EMA. Csikszentmihalyi and Larson (1987), one of the most-cited methodology papers in psychology, is absent. The clinical-research adaptation (Stone and Shiffman 2002; Trull and Ebner-Priemer 2009) is also missing.

**Why it matters.** The talk's slide nineteen rests on the *snapshot versus trajectory* failure mode of standard POE. The diagnosis depends on ESM being a real alternative; if our corpus does not have the methodology papers, the substitution skill cannot recommend the method when a student or researcher asks for the temporal-trajectory complement to single-shot satisfaction.

**What to extract.** Eight to ten papers. Seed with Csikszentmihalyi and Larson (1987); Hektner, Schmidt, and Csikszentmihalyi (2007); Kahneman, Krueger, Schkade, Schwarz, and Stone (2004) on the day-reconstruction method; recent architectural applications (the Lichtblau and others on experience sampling in office environments, if extractable). The ESM/EMA distinction in `160sp/ka_vr_measurability_content_2026-05-18.md` is the seed for the construct definitions.

**Owner.** CW.

**Acceptance.** *Experience sampling* and *day reconstruction* as constructs in the substitution graph, with measurement-protocol nodes specifying sampling cadence, prompt-design, and the smartphone-deployment standard practice.

---

## POE-EXT-6 — Daylight Glare Probability and the contemporary glare-metric literature

**Current corpus state.** Three evidence rows mention glare; one is the original Wienold-Christoffersen formulation in a derivative paraphrase. Wienold et al. (2019) on cross-validation is absent. The CIE-standard glare-index history (DGI, UGR) is also absent.

**Why it matters.** The talk's experience three is DGP. The visual demonstration — a fish-eye luminance image with the DGP heat-map overlay — is one of the slide's strongest. If the corpus does not have the DGP papers, the substitution skill cannot recommend the metric when a student is evaluating a daylit space.

**What to extract.** Six to eight papers. Seed with Wienold and Christoffersen (2006); Wienold et al. (2019); the Hopkinson-IES glare-index history; recent comparative-validation work. The substitution-graph construct is *discomfort glare* with measurement nodes for DGP, DGI, UGR, and the vertical-illuminance threshold method.

**Owner.** AG extraction pass once seed papers added; CW writes the substitution-graph node.

**Acceptance.** *Discomfort glare* construct with four measurement nodes and the substitutability links between them. *Daylight autonomy* is added as a complementary but distinct construct (daylight autonomy says nothing about glare; the substitution graph should make that orthogonality visible).

---

## POE-EXT-7 — Multisensory integration in the built environment

**Current corpus state.** Four evidence rows in the multisensory bundle. Schweiker et al.'s 2020 *Building and Environment* review is absent. The Spence neuroscience-of-multisensory-perception literature is absent. The thermal-acoustic and thermal-lighting interaction literatures are absent.

**Why it matters.** This is a methodological gap as much as a content gap. The standard POE protocol measures each IEQ axis in isolation. The multisensory literature has shown real interactions: a noisy office is judged warmer than a quiet office at the same temperature; a colder office is judged more glaring at the same DGP. Single-axis evaluation systematically underestimates these crossover effects.

**What to extract.** Eight to twelve papers. Seed with Schweiker et al. (2020); Yang and Mak (2017); Hong and Lin (2015); and the older Hellbrück literature on thermal-acoustic interaction. The substitution-graph construct is *multisensory IEQ interaction* with measurement nodes for the standard single-axis instruments and the multi-axis protocols (Spence-style crossover designs, conjoint-evaluation under multi-axis manipulation).

**Owner.** AG extraction pass once seed papers added.

**Acceptance.** Multisensory interaction terms encoded in the substitution graph as joint constructs (acoustic×thermal, lighting×thermal, lighting×acoustic), with explicit warning notes that single-axis evaluation will mis-estimate these.

---

## POE-EXT-8 — Adaptive preferences in the Sen-Nussbaum sense, applied to the built environment

**Current corpus state.** Zero evidence rows mention adaptive preference. Sen (1985, 1999) and Nussbaum (2000) are not in the corpus, which is unsurprising — they are welfare-economics texts, not architecture papers. There are no architectural studies that have explicitly elicited adaptive preferences in occupants of long-occupied buildings.

**Why it matters.** This is the deepest item on the agenda. The talk's slide eighteen — "Saying you are satisfied with what you no longer remember could be different" — is the rhetorical hinge of the whole prescription. If the corpus has no support for adaptive-preference elicitation as a POE method, the slide is making a philosophical claim without empirical anchorage. The fix is partly to add the welfare-economics literature, but more usefully to seed a research-front for the architectural application — POE-as-counterfactual-elicitation — and put it on the COGS 160 student-project roster.

**What to extract.** Six to eight papers from welfare economics and the capabilities approach; another six to eight from health-economics literature on adaptive preference in chronically ill populations; and a search for any architectural applications that exist (there will be very few). Seed with Sen (1985, 1999); Nussbaum (2000); Elster (1983) on sour grapes; Khader (2011) on adaptive preference and women's wellbeing; Teschl and Comim (2005) on adaptive preference and capabilities.

**Owner.** CW writes the framing and seeds the construct definition; AG extracts as papers become available. The architectural-application gap is itself a finding — we may want to recommend that some COGS 160 students propose theses on it.

**Acceptance.** *Adaptive preference* as a construct in the substitution graph, with measurement nodes for *counterfactual elicitation*, *temporal-comparison elicitation* (occupant rates the building twice — before exposure and after sustained occupancy), and the standard capabilities-approach assessment. Cross-references to the *stated preference* and *preference structure* nodes (POE-EXT-4).

---

## How this folds into the existing UJ-* sprint plan

The POE corpus-extraction items connect to the existing user-journey sprints as follows. UJ-A4 (substitution-skill build-spec) already references a construct-to-measure substitution graph; POE-EXT-1 through POE-EXT-8 are precisely the construct-and-measure nodes that need to populate it. UJ-A5 (V7-Lite build-spec) extracts new papers into the corpus; the seed lists in this memo go into the V7-Lite paper-acquisition queue.

The AG operator prompt (`prompts/AG_SUBSTITUTION_GRAPH_EXTRACTION_2026-05-18.md`) handles the extraction pass once the seed papers are added; CW should treat this memo as the deliverable that defines the eight construct-clusters AG is to extract first, in the priority order listed above.

The POE talk should not be presented to an external audience until at least POE-EXT-1, POE-EXT-2, POE-EXT-6, and POE-EXT-7 are extracted, because those are the gaps that the talk content depends on for its empirical claims. POE-EXT-3, POE-EXT-4, POE-EXT-5, and POE-EXT-8 are about the methods the talk recommends; they should be extracted before the prescription becomes a research programme, but the talk itself can survive their absence so long as the three-channel argument is framed as a recommendation rather than a track record.

---

## Estimated work

| Item | Papers to seed | Owner | Wall-clock | Dependencies |
|------|---|-------|-----|---|
| POE-EXT-1 (adaptive thermal) | 12–15 | AG + CW | 2 weeks | none |
| POE-EXT-2 (VOC/PM/IAQ) | 15–20 | AG + CW | 2 weeks | none |
| POE-EXT-3 (IAT) | 10–15 | CW + AG | 2 weeks | none |
| POE-EXT-4 (Q-sort) | 8–12 | CW | 1 week | none |
| POE-EXT-5 (ESM/EMA) | 8–10 | CW | 1 week | none |
| POE-EXT-6 (DGP) | 6–8 | AG | 1 week | seed papers in place |
| POE-EXT-7 (multisensory) | 8–12 | AG | 2 weeks | none |
| POE-EXT-8 (adaptive prefs) | 12–16 | CW | 2 weeks | none |

Total: roughly 80 to 110 papers added to the corpus; eight to ten weeks of wall-clock if run sequentially, three to four weeks if AG and CW work in parallel on disjoint items (AG: 1, 2, 6, 7; CW: 3, 4, 5, 8).

---

## Open questions

A few questions for DK before the work starts.

1. Should the POE-EXT-* items go into TASKS.md as a top-level priority alongside the UJ-* sprint, or are they a sub-track of UJ-A4 (the substitution-skill build)? My preference is the former — they are pedagogically and methodologically central enough to deserve their own track — but it adds another swim-lane to the project plan.

2. Is there an existing Article_Eater paper-acquisition pipeline that can ingest the seed lists, or does CW need to assemble them as PDF batches for direct upload? The answer affects how the seed lists are formatted.

3. Should the talk be deferred until at least POE-EXT-1, 2, 6, 7 are extracted, or is there an external venue where presenting the framing without the full corpus underpinning is acceptable?

4. The Sen-Nussbaum literature (POE-EXT-8) is genuinely outside the canonical architecture-and-environmental-psychology canon. Are we comfortable having the corpus reach that far? If yes, the substitution-graph design needs a framework-stratum tag (welfare economics) that the existing schema may not support.

---

*End of memo. Next action: DK to decide on the open questions above, then CW updates TASKS.md and writes the AG extraction-batch handoff.*
