# Panel Context — Determining the Canonical Topic-Family Taxonomy

*David Kirsh, 2026-05-19. Panel-context document, modelled on `docs/VOI_OPERATIONALISATION_PANEL_CONTEXT_2026-05-17.md`. Composes a panel and frames the questions for deciding the canonical topic-family taxonomy that the COGS 160 Fall journey depends on. As with the VOI panel: the composition below is for DK's approval; the CW-simulated synthesis is the next step once DK signs off, and a real-panel transmission is optional after that.*

---

## Why this panel exists

The COGS 160 Fall Week-1 journey has a surface — the Did-You-Know browser, Surface 2 of the wireframe (`160sp/ka_fall_dyk_browser.html`) — whose central affordance is a set of **topic-family filter pills**. A student arriving without a topic in mind scans surprising findings and narrows by family. The wireframe shows five example families: *Daylight × attention*, *Soundscape × stress*, *Biophilia × restoration*, *Spatial form × navigation*, *Ceiling × processing style*. The wireframe's own annotation flags this as unresolved: "whether the five families shown here are the right grouping is itself a design decision."

It is more than a UI decision. The topic-family taxonomy is the lens through which every student first sees the corpus. It determines which findings sit near which, which intersections look like live research areas and which look empty, and — because Week 1 is where students choose the topic they will spend ten weeks on — it shapes the distribution of what the cohort studies. A taxonomy that is wrong in a structural way will be wrong for every student, every term. It deserves the same deliberate treatment the VOI operationalisation received.

This document does not decide the taxonomy. It composes a panel and frames the questions, so that the decision is made against the best available thinking on categorisation, knowledge organisation, and science mapping rather than by the path of least resistance.

---

## The corpus as it actually is

The panel should reason against the real structure, not an idealisation. The Knowledge Atlas corpus, as indexed in `data/ka_payloads/topic_ontology.json` and the research-fronts payload:

- **Nine IV roots** — the environmental dimensions: Spatial Form, Luminous Environment, Thermal & Air Quality, Acoustic Environment, Nature & Biophilia, Material & Surface, Social-Spatial, Environmental Control, Multisensory / Compound.
- **Eight DV roots** — the outcome categories: Cognition & Performance, Affect & Wellbeing, Physiology, Neural Activity, Behaviour, Health Outcomes, Social Outcomes, Mechanism / Pathway.
- **121 IV × DV topic nodes** — the cross-product, pruned to the pairs that actually have papers (e.g. `acoustic__cog_attention`, `luminous__affect_negative_stress`).
- **18 research fronts** — data-derived clusters with names like "Nature & Biophilia × Stress Response (Biophilia)" and "Luminous Environment × Cognitive Performance (Circadian)". Several fronts are near-duplicates of one another (three separate "Nature & Biophilia × Stress Response" fronts with different parenthetical tags), which is itself a finding about the front-detection method.
- **760 articles**, **1,900 evidence rows**, and a topic-crosswalk that maps articles to nodes.

The taxonomy question is, in effect: given this structure, what is the right *intermediate* grouping — coarser than 121 nodes, finer than 9 roots — for a student-facing filter, and on what principle is it built?

---

## The design tensions the panel must resolve

Six tensions run through the problem. The panel does not have to resolve all of them, but the synthesis should take a position on each.

**Axis.** Should families be IV-rooted (group by environmental dimension — all daylight studies together), DV-rooted (group by outcome — all stress studies together), faceted (the student picks an IV facet *and* a DV facet), theory-rooted (group by the theory that explains them — Attention Restoration Theory, prospect-refuge, circadian entrainment), or data-driven (group by citation-graph community)? The wireframe's five examples are IV × DV pairs, which is a faceted scheme collapsed to named cells — but it is not obvious that is right.

**Granularity.** 121 nodes is far too many for filter pills. Nine IV roots may be too coarse — "Luminous Environment" spans circadian health, glare, daylight-and-performance, and aesthetic preference, which a student would not want lumped. What is the right cardinality for a Week-1 filter — five, nine, a dozen?

**Discovered versus designed.** Should the families be *discovered* bottom-up from the corpus (research-front detection, citation-community detection under the map equation) or *designed* top-down for student intuition? The discovered taxonomy reflects the science's actual structure but shifts as the corpus grows and produces artefacts like the three duplicate biophilia fronts. The designed taxonomy is stable and legible but may impose a structure the literature does not have.

**Stability.** A data-driven taxonomy is a moving target — re-running community detection after each corpus expansion reshuffles the families, and a student who bookmarked "Soundscape × stress" may find it renamed next term. A designed taxonomy is stable but can drift out of alignment with a growing corpus. How should the taxonomy version across corpus growth?

**Cross-cutting topics.** Some topics resist a single home. "Biophilia" is an IV that spans nearly every DV; "stress" is a DV that spans nearly every IV; "restoration" is half-construct, half-outcome. A single-axis taxonomy forces every such topic into one bin and hides its reach. A faceted scheme handles it but costs UI complexity.

**Audience.** The filter is for undergraduates in the first week of a course, not for expert users of a knowledge base. The families must be immediately legible to someone who has not yet learned the field's vocabulary. This constraint may pull against every data-driven or ontologically-principled option.

---

## Panel composition (for DK approval)

Eight panelists, chosen so that categorisation psychology, knowledge organisation, data-driven science mapping, information theory, the environmental-psychology domain, and information-architecture practice are each represented. As with the VOI panel, the panel is CW-simulated in the first instance; each panelist's position will be reconstructed from their published work and clearly labelled as simulation pending a real panel.

**1. Eleanor Rosch** — prototype theory and the basic-level category. Rosch's work established that categories have graded structure (some members are more central than others) and that there is a *basic level* of abstraction at which people most naturally categorise — neither the most general nor the most specific. Her central question for this panel: is there a basic level of environmental-psychology topic that students naturally reach for, and should the families sit at it rather than at the IV-root level or the 121-node level?

**2. Gregory Murphy** — concepts and theory-based categorisation; author of *The Big Book of Concepts*. Murphy's work argues that categories cohere because of the theories people hold about why their members belong together, not merely because of feature similarity. His question: do topic families need a unifying explanatory theory to be cognitively real, or is topic-similarity grouping enough for a filter?

**3. Geoffrey C. Bowker** — classification infrastructures; co-author with Susan Leigh Star of *Sorting Things Out: Classification and Its Consequences*. Bowker's contribution is the insistence that every classification scheme makes some things visible and others invisible, and that the silences are consequential. His question: what does an IV-rooted taxonomy make invisible — and who or what loses when a cross-cutting topic is forced into one family?

**4. Birger Hjørland** — knowledge organisation and domain analysis. Hjørland argues that classification should be derived from an analysis of the domain's own discourse and literature structure, not from universal logical principles or from naive user intuition alone. His question: should the topic-family taxonomy be derived by domain analysis of the architecture-and-cognition literature itself, and if so, what does that analysis show?

**5. Chaomei Chen** — research-front detection and science mapping; creator of CiteSpace. Chen's work operationalises the "research front" as a detectable, time-evolving cluster of co-cited work. The corpus already has 18 such fronts. His question: should the families simply *be* the research fronts (or a curated subset of them), and what does the duplication among the current fronts say about whether they are ready to serve as a taxonomy?

**6. Carl Bergstrom** — information theory and community detection; co-developer of the map equation and the Infomap algorithm, and a panelist on the VOI panel (continuity is deliberate). Bergstrom's question: should families be the communities of the corpus citation graph under the map equation — the partition that most compresses a random walk over the literature — and how does that partition compare with both the research fronts and the IV × DV grid?

**7. Robert Gifford** — environmental psychology; author of *Environmental Psychology: Principles and Practice*, the field's standard textbook. Writing that textbook was itself an act of topic-family taxonomy: Gifford had to decide the chapter structure of the whole field. His question: how does the textbook-chapter organisation of environmental psychology map onto the corpus, and where does the corpus's IV × DV grid diverge from how the field organises itself for teaching?

**8. Peter Morville** — information architecture and findability; co-author of *Information Architecture for the World Wide Web* and author of *Ambient Findability*. Morville's expertise is the practical design of faceted navigation and filter interfaces. His question: for a filter-pill UI serving first-week students, is a flat list of named families or a two-axis faceted filter (pick an environment, pick an outcome) the better findability design — and what is the cardinality beyond which filter pills stop helping?

---

## The questions put to the panel

Thirteen questions, grouped. The synthesis should produce a position on each, and should flag where the panel converges and where it genuinely divides.

*On the principle of the taxonomy:*

1. Should the taxonomy be IV-rooted, DV-rooted, faceted (IV × DV), theory-rooted, or data-driven? If faceted, should the named families be collapsed cells of the grid or should the student filter on two axes independently?
2. Should the families be discovered bottom-up from the corpus or designed top-down for student intuition — and if a hybrid, what is discovered and what is designed?
3. Should the families simply be the 18 research fronts, a curated subset of them, or something the front-detection does not produce?
4. Should the families be the citation-graph communities under the map equation? How should that partition be reconciled with the research fronts and the IV × DV grid when they disagree?

*On structure and granularity:*

5. What is the right number of families for a Week-1 student-facing filter? Is there a defensible upper bound beyond which filter pills stop aiding findability?
6. Is there a basic level of environmental-psychology topic — in Rosch's sense — and should the families sit at it?
7. Do families need a unifying explanatory theory to cohere, or is topic-similarity enough?
8. How should cross-cutting topics (biophilia, stress, restoration) be handled — forced into one family, allowed multiple memberships, or made into a facet rather than a family?

*On consequences and stability:*

9. What does the chosen taxonomy make invisible? Which topics or intersections become hard to find, and is that acceptable?
10. How should the taxonomy version as the corpus grows — re-derived periodically, frozen, or designed so growth slots into existing families?
11. How should the taxonomy relate to the deeper-measurement work — the POE-EXT constructs now in the substitution graph — so that a student filtering by family also sees the measurement opportunities within it?

*On the interface:*

12. Flat family list versus two-axis faceted filter: which serves first-week students better, and how should the "Contested" and "VR-tractable" flags interact with the family filter?
13. Should the family taxonomy on the student-facing DYK browser be the same taxonomy used on the researcher-facing surfaces, or is a simplified student taxonomy a defensible divergence from a richer researcher one?

---

## What convergence would look like

The VOI panel converged on four positions and left five contested for DK. A good outcome here would be similar: a recommended taxonomy principle (the answer to question 1), a recommended cardinality (question 5), a recommended treatment of cross-cutting topics (question 8), and a recommended versioning policy (question 10) — with the genuinely contested choices surfaced explicitly rather than papered over. The most likely fault line, on CW's reading of these panelists, is between the data-driven voices (Chen, Bergstrom) who will favour letting the corpus's own structure define the families, and the categorisation-and-audience voices (Rosch, Morville, Gifford) who will favour a designed, stable, student-legible scheme — with Bowker and Hjørland likely arguing that the choice between them is itself the consequential decision and Murphy asking whether either produces families that cohere for a reason a student could state.

---

## Status and next step

Panel composition is proposed, not approved. Per the VOI-panel precedent, the next step is DK's approval (or revision) of the eight-panelist composition, after which CW produces the simulated synthesis — eight position sections of roughly 700–900 words each, reconstructed from each panelist's published work and clearly labelled as CW-simulation, followed by the convergent and contested positions. A real-panel transmission, with briefing letters, is optional after that and would follow the same pattern as the VOI real-panel plan.

---

*End of panel-context document. Companion to the VOI panel materials. Next action: DK approves or revises the panel composition; CW then drafts the simulated synthesis.*
