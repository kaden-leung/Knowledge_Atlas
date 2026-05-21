# AG — POE-EXT Corpus Extraction Seed Package

*David Kirsh, 2026-05-19. The executable content of the POE corpus-extraction sprint. Companion to `docs/POE_CORPUS_EXTRACTION_AGENDA_2026-05-19.md` (the agenda, which states why each item matters) and `docs/POE_REVIEW_2026-05-19.md` (the review the items derive from). This document is the operator package: for each of POE-EXT-1 through POE-EXT-8 it gives the concrete seed-paper list with full citations, the construct definitions, the shallow-versus-deep measurement contrast, and the substitution-graph nodes to populate.*

---

## How to use this package

Each of the eight sections below is one extraction job. AG works them in the priority order of the agenda memo: POE-EXT-1, 2, 6, 7 first (the talk's empirical claims depend on them), then POE-EXT-3, 4, 5, 8 (the methods the talk recommends). For each item:

1. **Acquire the seed papers.** The citations below are complete enough for a paper-acquisition pipeline to resolve via CrossRef; DOIs are given where confirmed. Books are given with publisher and ISBN where relevant. Add each paper to the corpus through the standard V7-Lite ingest path so it gains a fingerprint, IV/DV extraction, and a topic assignment.

2. **Populate the substitution graph.** Each section lists the constructs and the measure nodes. Insert them into `data/substitution_graph.db` (`constructs`, `measures`, `construct_measure_links` — schema confirmed 2026-05-19). The machine-readable seed is in the companion file `data/poe_ext_substitution_seed.json`; this document is the human-readable rationale for it.

3. **Run the substitution-graph extraction pass** per `prompts/AG_SUBSTITUTION_GRAPH_EXTRACTION_2026-05-18.md` over the newly seeded papers, so the per-paper psychometric profiles, construct-validity coefficients, and severity averages are filled from the papers themselves rather than from this document's estimates.

The recurring pattern across all eight items is the same one the POE review identified: the standard POE instrument measures a **surface proxy** (the shallow measure column) when the literature has long since articulated a **deeper construct** (the deep measure column) that better predicts what occupants experience. The substitution graph should encode both, and encode the link between them, so the substitution skill can tell a student "you asked for the shallow measure; here is the deeper one and what it costs."

A note on the subscription/API question: this seed package is content, not an LLM run; it carries no invocation-mode implications. The AG substitution-graph extraction pass that consumes it follows whatever mode `prompts/AG_SUBSTITUTION_GRAPH_EXTRACTION_2026-05-18.md` specifies.

---

## POE-EXT-1 — Adaptive thermal comfort

**Scope.** The adaptive thermal-comfort model and the affordances for adaptation. Currently one evidence row in the corpus. The talk depends on this at experience 5 ("wanting to open a window and not being able to").

### Constructs

| Construct | Shallow standard measure | Deeper warranted measure | IV/DV |
|---|---|---|---|
| Adaptive thermal comfort | PMV/PPD static comfort band | Adaptive comfort regression (comfort temperature on outdoor running-mean temperature) | DV |
| Thermal pleasure / alliesthesia | Thermal sensation vote (cold–hot, ASHRAE 7-point) | Thermal-pleasure rating; spatial and temporal alliesthesia | DV |
| Mean radiant temperature | Air temperature (thermostat) | MRT via globe thermometer | IV |
| Radiant asymmetry | (not measured) | Directional radiant-asymmetry measurement against ASHRAE 55 limits | IV |
| Personal thermal control / adaptive opportunity | Presence of a thermostat | Adaptive-opportunity inventory: operable windows, fans, dress code, schedule flexibility | IV |

### Seed papers

1. de Dear, R. J., & Brager, G. S. (1998). Developing an adaptive model of thermal comfort and preference. *ASHRAE Transactions, 104*(1), 145–167.
2. de Dear, R. J., & Brager, G. S. (2002). Thermal comfort in naturally ventilated buildings: Revisions to ASHRAE Standard 55. *Energy and Buildings, 34*(6), 549–561. https://doi.org/10.1016/S0378-7788(02)00005-1
3. Humphreys, M. A., & Nicol, J. F. (1998). Understanding the adaptive approach to thermal comfort. *ASHRAE Transactions, 104*(1), 991–1004.
4. Nicol, J. F., & Humphreys, M. A. (2002). Adaptive thermal comfort and sustainable thermal standards for buildings. *Energy and Buildings, 34*(6), 563–572. https://doi.org/10.1016/S0378-7788(02)00006-3
5. Cabanac, M. (1971). Physiological role of pleasure. *Science, 173*(4002), 1103–1107. https://doi.org/10.1126/science.173.4002.1103
6. Parkinson, T., & de Dear, R. (2015). Thermal pleasure in built environments: Physiology of alliesthesia. *Building Research & Information, 43*(3), 288–301. https://doi.org/10.1080/09613218.2015.989662
7. Parkinson, T., de Dear, R., & Brager, G. (2020). Nudging the adaptive thermal comfort model. *Energy and Buildings, 206*, 109559. https://doi.org/10.1016/j.enbuild.2019.109559
8. Halawa, E., van Hoof, J., & Soebarto, V. (2014). The impacts of the thermal radiation field on thermal comfort, energy consumption and control. *Renewable and Sustainable Energy Reviews, 37*, 907–918. https://doi.org/10.1016/j.rser.2014.05.040
9. Brager, G. S., Paliaga, G., & de Dear, R. (2004). Operable windows, personal control, and occupant comfort. *ASHRAE Transactions, 110*(2), 17–35.
10. Toftum, J. (2010). Central automatic control or distributed occupant control for better indoor environment quality in the future. *Building and Environment, 45*(1), 23–28. https://doi.org/10.1016/j.buildenv.2009.03.011
11. Schweiker, M., & Wagner, A. (2015). A framework for an adaptive thermal heat balance model (ATHB). *Building and Environment, 94*, 252–262. https://doi.org/10.1016/j.buildenv.2015.08.018
12. Luo, M., et al. (2016). Can personal control influence human thermal comfort? A field study in residential buildings in China in winter. *Energy and Buildings, 72*, 411–418.
13. Fanger, P. O. (1970). *Thermal Comfort: Analysis and Applications in Environmental Engineering*. Danish Technical Press. *(the PMV origin — the shallow baseline the adaptive model corrects)*
14. ASHRAE. (2020). *ANSI/ASHRAE Standard 55-2020: Thermal Environmental Conditions for Human Occupancy* — adaptive comfort section. ASHRAE.

### Acceptance

All five constructs present in the substitution graph with at least two measurement nodes each; the *adaptive thermal comfort* and *thermal pleasure* constructs carry a `proliferation_warning` JSON noting the jangle risk with the generic "thermal comfort" construct already in the corpus.

---

## POE-EXT-2 — Volatile organic compounds, particulate matter, and indoor air quality

**Scope.** The deeper IAQ constructs the CO₂ proxy does not capture. Currently zero evidence rows on VOC/PM, three on CO₂/ventilation. The talk depends on this at experience 7 ("reading your performance dip at two in the afternoon").

### Constructs

| Construct | Shallow standard measure | Deeper warranted measure | IV/DV |
|---|---|---|---|
| Ventilation rate | CO₂ ppm as proxy | Outdoor air supply rate (L/s per person), measured directly | IV |
| Perceived air quality | "Freshness" Likert item | olf/decipol panel evaluation | DV |
| Bio-effluent concentration | (not measured) | olf source strength; CO₂-as-bioeffluent-marker separated from CO₂-as-pollutant | IV |
| VOC concentration | (not measured) | Total VOC via photo-ionisation detector or GC-MS | IV |
| PM2.5 concentration | (not measured) | Optical PM2.5 monitor | IV |
| Cognitive performance under IAQ load | Self-reported productivity | COGfx Strategic Management Simulation battery; PVT; objective task throughput | DV |

### Seed papers

1. Allen, J. G., MacNaughton, P., Satish, U., Santanam, S., Vallarino, J., & Spengler, J. D. (2016). Associations of cognitive function scores with carbon dioxide, ventilation, and volatile organic compound exposures in office workers: A controlled exposure study of green and conventional office environments. *Environmental Health Perspectives, 124*(6), 805–812. https://doi.org/10.1289/ehp.1510037
2. Satish, U., Mendell, M. J., Shekhar, K., Hotchi, T., Sullivan, D., Streufert, S., & Fisk, W. J. (2012). Is CO₂ an indoor pollutant? Direct effects of low-to-moderate CO₂ concentrations on human decision-making performance. *Environmental Health Perspectives, 120*(12), 1671–1677. https://doi.org/10.1289/ehp.1104789
3. Wargocki, P., Wyon, D. P., Sundell, J., Clausen, G., & Fanger, P. O. (2000). The effects of outdoor air supply rate in an office on perceived air quality, sick building syndrome (SBS) symptoms and productivity. *Indoor Air, 10*(4), 222–236. https://doi.org/10.1034/j.1600-0668.2000.010004222.x
4. Wargocki, P., & Wyon, D. P. (2007). The effects of outdoor air supply rate and supply air filter condition in classrooms on the performance of schoolwork by children. *HVAC&R Research, 13*(2), 165–191.
5. Wargocki, P., & Wyon, D. P. (2007). The effects of moderately raised classroom temperatures and classroom ventilation rate on the performance of schoolwork by children. *HVAC&R Research, 13*(2), 193–220.
6. Bakó-Biró, Z., Clements-Croome, D. J., Kochhar, N., Awbi, H. B., & Williams, M. J. (2012). Ventilation rates in schools and pupils' performance. *Building and Environment, 48*, 215–223. https://doi.org/10.1016/j.buildenv.2011.08.018
7. Fanger, P. O. (1988). Introduction of the olf and the decipol units to quantify air pollution perceived by humans indoors and outdoors. *Energy and Buildings, 12*(1), 1–6. https://doi.org/10.1016/0378-7788(88)90019-5
8. Tham, K. W., Sekhar, S. C., Cheong, K. W. D., & Wargocki, P. (2003). The effects of outdoor air supply rate on health, performance, and perceived air quality of call-centre workers. *Building Services Engineering Research and Technology, 24*(3), 153–162.
9. Power, M. C., Adar, S. D., Yanosky, J. D., & Weuve, J. (2016). Exposure to air pollution as a potential contributor to cognitive function, cognitive decline, brain imaging, and dementia: A systematic review of epidemiologic research. *NeuroToxicology, 56*, 235–253. https://doi.org/10.1016/j.neuro.2016.06.004
10. MacNaughton, P., Satish, U., Laurent, J. G. C., Flanigan, S., Vallarino, J., Coull, B., Spengler, J. D., & Allen, J. G. (2017). The impact of working in a green certified building on cognitive function and health. *Building and Environment, 114*, 178–186. https://doi.org/10.1016/j.buildenv.2016.11.041
11. Wyon, D. P. (2004). The effects of indoor air quality on performance and productivity. *Indoor Air, 14*(s7), 92–101. https://doi.org/10.1111/j.1600-0668.2004.00278.x
12. Sundell, J., Levin, H., Nazaroff, W. W., et al. (2011). Ventilation rates and health: Multidisciplinary review of the scientific literature. *Indoor Air, 21*(3), 191–204. https://doi.org/10.1111/j.1600-0668.2010.00703.x
13. Zhang, X., Wargocki, P., & Lian, Z. (2017). Effects of exposure to carbon dioxide and bioeffluents on cognitive performance. *Scandinavian Journal of Work, Environment & Health, 43*(5), 456–464.
14. Allen, J. G., et al. (2018). Airplane pilot flight performance on 21 maneuvers in a flight simulator under varying carbon dioxide concentrations. *Journal of Exposure Science & Environmental Epidemiology, 29*, 457–468. *(optional — extends the CO₂-decrement finding to a high-skill task)*

### Acceptance

Six constructs present; the substitution graph carries an explicit *low-construct-validity* link between *ventilation rate* and the CO₂-ppm measure (the proxy is weak), and a high-validity link to the direct L/s/person measure. The *cognitive performance under IAQ load* construct cross-references the existing corpus cognitive-performance measures (PVT, n-back) so the substitution skill can route between IEQ axes.

---

## POE-EXT-3 — Implicit Association Tests applied to the built environment

**Scope.** The implicit channel of the three-channel evaluation prescription. Currently zero evidence rows. Without corpus support, the talk's implicit-channel recommendation rests on plausibility rather than warrant.

### Constructs

| Construct | Shallow standard measure | Deeper warranted measure | IV/DV |
|---|---|---|---|
| Implicit attitude | Explicit Likert attitude / satisfaction rating | IAT D-score (improved scoring algorithm) | DV |
| Built-Environment-IAT *(new — no extant paper; research opportunity)* | (none) | Implicit me/other × built/natural association, or me/other × specific spatial feature | DV |
| Evaluative implicit response | Explicit preference rating | Evaluative priming; Affect Misattribution Procedure | DV |

### Seed papers

1. Greenwald, A. G., McGhee, D. E., & Schwartz, J. L. K. (1998). Measuring individual differences in implicit cognition: The Implicit Association Test. *Journal of Personality and Social Psychology, 74*(6), 1464–1480. https://doi.org/10.1037/0022-3514.74.6.1464
2. Greenwald, A. G., Nosek, B. A., & Banaji, M. R. (2003). Understanding and using the Implicit Association Test: I. An improved scoring algorithm. *Journal of Personality and Social Psychology, 85*(2), 197–216. https://doi.org/10.1037/0022-3514.85.2.197
3. Nosek, B. A., Greenwald, A. G., & Banaji, M. R. (2007). The Implicit Association Test at age 7: A methodological and conceptual review. In J. A. Bargh (Ed.), *Social Psychology and the Unconscious: The Automaticity of Higher Mental Processes* (pp. 265–292). Psychology Press.
4. Schultz, P. W., Shriver, C., Tabanico, J. J., & Khazian, A. M. (2004). Implicit connections with nature. *Journal of Environmental Psychology, 24*(1), 31–42. https://doi.org/10.1016/S0272-4944(03)00022-7
5. Bruni, C. M., & Schultz, P. W. (2010). Implicit beliefs about self and nature: Evidence from an IAT game. *Journal of Environmental Psychology, 30*(1), 95–102. https://doi.org/10.1016/j.jenvp.2009.10.004
6. Fazio, R. H., Jackson, J. R., Dunton, B. C., & Williams, C. J. (1995). Variability in automatic activation as an unobtrusive measure of racial attitudes: A bona fide pipeline? *Journal of Personality and Social Psychology, 69*(6), 1013–1027.
7. Payne, B. K., Cheng, C. M., Govorun, O., & Stewart, B. D. (2005). An inkblot for attitudes: Affect misattribution as implicit measurement. *Journal of Personality and Social Psychology, 89*(3), 277–293.
8. Karpinski, A., & Steinman, R. B. (2006). The single category implicit association test as a measure of implicit social cognition. *Journal of Personality and Social Psychology, 91*(1), 16–32.
9. Greenwald, A. G., Poehlman, T. A., Uhlmann, E. L., & Banaji, M. R. (2009). Understanding and using the Implicit Association Test: III. Meta-analysis of predictive validity. *Journal of Personality and Social Psychology, 97*(1), 17–41. https://doi.org/10.1037/a0015575
10. Blanton, H., Jaccard, J., Klick, J., Mellers, B., Mitchell, G., & Tetlock, P. E. (2009). Strong claims and weak evidence: Reassessing the predictive validity of the IAT. *Journal of Applied Psychology, 94*(3), 567–582. https://doi.org/10.1037/a0014665
11. Cunningham, W. A., Preacher, K. J., & Banaji, M. R. (2001). Implicit attitude measures: Consistency, stability, and convergent validity. *Psychological Science, 12*(2), 163–170.

### Acceptance

The *implicit attitude* construct is in the graph with the IAT and evaluative-priming measure nodes. The *Built-Environment-IAT* construct is seeded **without** a canonical paper and flagged `proliferation_warning` as a research opportunity rather than an extant instrument — it is the single clearest place where the corpus could host a genuinely new contribution. Items 9 and 10 (the predictive-validity meta-analysis and the Blanton critique) must both be seeded so the substitution skill can surface the IAT's contested status rather than overselling it.

---

## POE-EXT-4 — Q-sort and preference-structure methods

**Scope.** The preference-structure leg of the three-channel prescription. Currently one evidence row. Vischer's functional-comfort work used Q-sort; the wider POE tradition has not adopted it.

### Constructs

| Construct | Shallow standard measure | Deeper warranted measure | IV/DV |
|---|---|---|---|
| Preference structure | Single Likert position on one dimension | Q-sort factor structure over a forced distribution | DV |
| Q-methodology subjectivity | (none) | Q-sort with by-person factor analysis | DV |
| 20-sort / forced-choice card sort | (none) | Constrained card sort, most-like-me to least-like-me | DV |
| Marginal attribute utility | Stated importance rating | Choice-based conjoint / discrete-choice estimation | DV |

### Seed papers

1. Stephenson, W. (1953). *The Study of Behavior: Q-Technique and Its Methodology*. University of Chicago Press.
2. Brown, S. R. (1980). *Political Subjectivity: Applications of Q Methodology in Political Science*. Yale University Press.
3. Watts, S., & Stenner, P. (2012). *Doing Q Methodological Research: Theory, Method and Interpretation*. Sage.
4. McKeown, B., & Thomas, D. B. (2013). *Q Methodology* (2nd ed.). Sage. (Quantitative Applications in the Social Sciences, No. 66.)
5. Vischer, J. C. (2007). The concept of workplace performance and its value to managers. *California Management Review, 49*(2), 62–79. https://doi.org/10.2307/41166383
6. Vischer, J. C. (2008). Towards an environmental psychology of workspace: How people are affected by environments for work. *Architectural Science Review, 51*(2), 97–108. https://doi.org/10.3763/asre.2008.5114
7. Green, P. E., & Srinivasan, V. (1990). Conjoint analysis in marketing: New developments with implications for research and practice. *Journal of Marketing, 54*(4), 3–19. https://doi.org/10.1177/002224299005400402
8. Louviere, J. J., Hensher, D. A., & Swait, J. D. (2000). *Stated Choice Methods: Analysis and Applications*. Cambridge University Press.
9. Coolen, H., & Hoekstra, J. (2001). Values as determinants of preferences for housing attributes. *Journal of Housing and the Built Environment, 16*(3–4), 285–306. https://doi.org/10.1023/A:1012543719364
10. Block, J. (2008). *The Q-Sort in Character Appraisal: Encoding Subjective Impressions of Persons Quantitatively*. American Psychological Association. *(reissue of the 1961 monograph)*

### Acceptance

The *preference structure* construct is in the graph with Q-sort, 20-sort, and conjoint measure nodes, each linked to the *adaptive preference* construct of POE-EXT-8 (the two are methodologically adjacent — both surface preferences a single Likert item flattens).

---

## POE-EXT-5 — Experience-sampling and ecological-momentary-assessment methods

**Scope.** The snapshot-versus-trajectory failure mode. Currently zero evidence rows. The talk's slide-19 diagnosis depends on ESM being a real, corpus-supported alternative.

### Constructs

| Construct | Shallow standard measure | Deeper warranted measure | IV/DV |
|---|---|---|---|
| Occupant experience over time | Single post-occupancy survey snapshot | Experience-sampling time series (multiple prompts per day) | DV |
| Ecological momentary state | Retrospective global rating | EMA momentary mood/comfort/environment record | DV |
| Reconstructed daily experience | (none) | Day Reconstruction Method episode reconstruction | DV |

### Seed papers

1. Csikszentmihalyi, M., & Larson, R. (1987). Validity and reliability of the experience-sampling method. *Journal of Nervous and Mental Disease, 175*(9), 526–536. https://doi.org/10.1097/00005053-198709000-00004
2. Larson, R., & Csikszentmihalyi, M. (1983). The experience sampling method. *New Directions for Methodology of Social and Behavioral Science, 15*, 41–56.
3. Hektner, J. M., Schmidt, J. A., & Csikszentmihalyi, M. (2007). *Experience Sampling Method: Measuring the Quality of Everyday Life*. Sage.
4. Kahneman, D., Krueger, A. B., Schkade, D. A., Schwarz, N., & Stone, A. A. (2004). A survey method for characterizing daily life experience: The Day Reconstruction Method. *Science, 306*(5702), 1776–1780. https://doi.org/10.1126/science.1103572
5. Shiffman, S., Stone, A. A., & Hufford, M. R. (2008). Ecological momentary assessment. *Annual Review of Clinical Psychology, 4*, 1–32. https://doi.org/10.1146/annurev.clinpsy.3.022806.091415
6. Stone, A. A., & Shiffman, S. (1994). Ecological momentary assessment (EMA) in behavioral medicine. *Annals of Behavioral Medicine, 16*(3), 199–202.
7. Trull, T. J., & Ebner-Priemer, U. (2013). Ambulatory assessment. *Annual Review of Clinical Psychology, 9*, 151–176. https://doi.org/10.1146/annurev-clinpsy-050212-185510
8. Bolger, N., Davis, A., & Rafaeli, E. (2003). Diary methods: Capturing life as it is lived. *Annual Review of Psychology, 54*, 579–616. https://doi.org/10.1146/annurev.psych.54.101601.145030
9. Conner, T. S., Tennen, H., Fleeson, W., & Barrett, L. F. (2009). Experience sampling methods: A modern idiographic approach to personality research. *Social and Personality Psychology Compass, 3*(3), 292–313.

### Acceptance

The three temporal-method constructs in the graph, each carrying a `vr_tractability_conditions` note: ESM and EMA are smartphone-deployable and so are tractable for a class-scale field study; the substitution skill should recommend them whenever a student proposes a single-shot satisfaction measure for a phenomenon known to vary by time of day.

---

## POE-EXT-6 — Daylight Glare Probability and the contemporary glare-metric literature

**Scope.** Discomfort glare. Currently three evidence rows on glare. The talk's experience 3 ("the micro-flinch when light hits the wrong part of your visual field") and one of its strongest visual demonstrations.

### Constructs

| Construct | Shallow standard measure | Deeper warranted measure | IV/DV |
|---|---|---|---|
| Discomfort glare | Horizontal desk illuminance; daylight autonomy | Daylight Glare Probability (DGP) from a fish-eye luminance image + vertical eye illuminance | DV |
| Glare from artificial lighting | Illuminance | Unified Glare Rating (UGR) | DV |
| Glare-source contrast | (not measured) | Luminance-contrast ratio; position-indexed source luminance | IV |

### Seed papers

1. Wienold, J., & Christoffersen, J. (2006). Evaluation methods and development of a new glare prediction model for daylight environments with the use of CCD cameras. *Energy and Buildings, 38*(7), 743–757. https://doi.org/10.1016/j.enbuild.2006.03.017
2. Wienold, J., Iwata, T., Sarey Khanie, M., Erell, E., Kaftan, E., Rodriguez, R. G., Yamin Garreton, J. A., Tzempelikos, T., Konstantzos, I., Christoffersen, J., Kuhn, T. E., Pierson, C., & Andersen, M. (2019). Cross-validation and robustness of daylight glare metrics. *Lighting Research & Technology, 51*(7), 983–1013. https://doi.org/10.1177/1477153519826003
3. Hopkinson, R. G. (1972). Glare from daylighting in buildings. *Applied Ergonomics, 3*(4), 206–215. https://doi.org/10.1016/0003-6870(72)90102-0
4. Commission Internationale de l'Éclairage. (1995). *Discomfort Glare in Interior Lighting* (CIE 117-1995). CIE. *(the Unified Glare Rating standard)*
5. Pierson, C., Wienold, J., & Bodart, M. (2018). Review of factors influencing discomfort glare perception from daylight. *LEUKOS, 14*(3), 111–148. https://doi.org/10.1080/15502724.2018.1428617
6. Jakubiec, J. A., & Reinhart, C. F. (2012). The 'adaptive zone' — A concept for assessing discomfort glare throughout daylit spaces. *Lighting Research & Technology, 44*(2), 149–170. https://doi.org/10.1177/1477153511420097
7. Osterhaus, W. K. E. (2005). Discomfort glare assessment and prevention for daylight applications in office environments. *Solar Energy, 79*(2), 140–158. https://doi.org/10.1016/j.solener.2004.11.011
8. Boyce, P. R. (2014). *Human Factors in Lighting* (3rd ed.). CRC Press. *(textbook anchor for the glare-metric history and the daylight-autonomy contrast)*

### Acceptance

The *discomfort glare* construct in the graph with four measure nodes (DGP, DGI, UGR, vertical-illuminance threshold) and the substitutability links between them. *Daylight autonomy* is added as a **distinct, complementary** construct — the substitution graph must make visible that daylight autonomy says nothing about glare, so the two are not interchangeable.

---

## POE-EXT-7 — Multisensory IEQ interaction

**Scope.** The cross-modal interactions single-axis POE evaluation systematically misses. Currently four evidence rows in the multisensory bundle.

### Constructs

| Construct | Shallow standard measure | Deeper warranted measure | IV/DV |
|---|---|---|---|
| Multisensory IEQ interaction | Each IEQ axis rated in isolation | Joint multi-axis manipulation with crossover-effect estimation | IV×IV |
| Acoustic × thermal interaction | Separate noise and temperature ratings | Combined-exposure design measuring how each shifts the other's acceptability | IV×IV |
| Lighting × thermal interaction | Separate illuminance and temperature ratings | Combined-exposure design (e.g., daylight shifting thermal perception) | IV×IV |
| Cross-modal overall comfort | Sum of single-axis comfort votes | Holistic overall-comfort vote with interaction terms modelled | DV |

### Seed papers

1. Schweiker, M., Ampatzi, E., Andargie, M. S., Andersen, R. K., Azar, E., Barthelmes, V. M., et al. (2020). Review of multi-domain approaches to indoor environmental perception and behaviour. *Building and Environment, 176*, 106804. https://doi.org/10.1016/j.buildenv.2020.106804
2. Torresin, S., Pernigotto, G., Cappelletti, F., & Gasparella, A. (2018). Combined effects of environmental factors on human perception and objective performance: A review of experimental laboratory works. *Indoor Air, 28*(4), 525–538. https://doi.org/10.1111/ina.12457
3. Pellerin, N., & Candas, V. (2003). Combined effects of temperature and noise on human discomfort. *Physiology & Behavior, 78*(1), 99–106. https://doi.org/10.1016/S0031-9384(02)00956-3
4. Pellerin, N., & Candas, V. (2004). Effects of steady-state noise and temperature conditions on environmental perception and acceptability. *Indoor Air, 14*(2), 129–136. https://doi.org/10.1046/j.1600-0668.2003.00221.x
5. Witterseh, T., Wyon, D. P., & Clausen, G. (2004). The effects of moderate heat stress and open-plan office noise distraction on SBS symptoms and on the performance of office work. *Indoor Air, 14*(s8), 30–40. https://doi.org/10.1111/j.1600-0668.2004.00305.x
6. Yang, W., & Moon, H. J. (2019). Combined effects of acoustic, thermal, and illumination conditions on the comfort of discrete senses and overall indoor environment. *Building and Environment, 148*, 623–633. https://doi.org/10.1016/j.buildenv.2018.11.040
7. Chinazzo, G., Wienold, J., & Andersen, M. (2018). Daylight affects human thermal perception. *Scientific Reports, 8*, 14892. https://doi.org/10.1038/s41598-018-33311-3
8. Tiller, D. K., Wang, L. M., Musser, A., & Radik, M. J. (2010). Combined effects of noise and temperature on human comfort and performance (ASHRAE 1128-RP). *ASHRAE Transactions, 116*(2).
9. Laurentin, C., Bermtto, V., & Fontoynont, M. (2000). Effect of thermal conditions and light source type on visual comfort appraisal. *Lighting Research & Technology, 32*(4), 223–233.
10. Fanger, P. O., Breum, N. O., & Jerking, E. (1977). Can colour and noise influence man's thermal comfort? *Ergonomics, 20*(1), 11–18. *(early cross-modal — colour and noise on thermal comfort)*

### Acceptance

The interaction constructs are encoded as **joint constructs** (acoustic×thermal, lighting×thermal, lighting×acoustic) rather than as single-axis constructs, with `notes` on each `construct_measure_link` warning that any single-axis instrument will mis-estimate the joint effect. This is the one item where the deeper measure is a *study design*, not an instrument.

---

## POE-EXT-8 — Adaptive preferences in the Sen–Nussbaum sense

**Scope.** The deepest item: the structural blind spot in the satisfaction survey. Currently zero evidence rows. The talk's slide 18 ("saying you are satisfied with what you no longer remember could be different") is the rhetorical hinge of the whole prescription.

### Constructs

| Construct | Shallow standard measure | Deeper warranted measure | IV/DV |
|---|---|---|---|
| Adaptive preference | Stated satisfaction with current conditions | Counterfactual-elicited preference (rating against a described better condition) | DV |
| Counterfactual elicitation | (none) | Structured counterfactual prompt: "imagine an office with X; how would you rate it?" | DV |
| Temporal-comparison elicitation | Single post-occupancy rating | Rate-twice design: before sustained exposure and after, to expose normalisation | DV |
| Hedonic adaptation | (none) | Longitudinal satisfaction tracking against a baseline-return hypothesis | DV |

### Seed papers

1. Sen, A. (1985). *Commodities and Capabilities*. North-Holland.
2. Sen, A. (1999). *Development as Freedom*. Knopf.
3. Elster, J. (1983). *Sour Grapes: Studies in the Subversion of Rationality*. Cambridge University Press. *(the origin of the term "adaptive preference")*
4. Nussbaum, M. C. (2000). *Women and Human Development: The Capabilities Approach*. Cambridge University Press.
5. Nussbaum, M. C. (2001). Adaptive preferences and women's options. *Economics and Philosophy, 17*(1), 67–88. https://doi.org/10.1017/S0266267101000153
6. Khader, S. J. (2011). *Adaptive Preferences and Women's Empowerment*. Oxford University Press. (ISBN 9780199777877.)
7. Teschl, M., & Comim, F. (2005). Adaptive preferences and capabilities: Some preliminary conceptual explorations. *Review of Social Economy, 63*(2), 229–247. https://doi.org/10.1080/00346760500130374
8. Bruckner, D. W. (2009). In defense of adaptive preferences. *Philosophical Studies, 142*(3), 307–324. https://doi.org/10.1007/s11098-007-9188-7
9. Colburn, B. (2011). Autonomy and adaptive preferences. *Utilitas, 23*(1), 52–71. https://doi.org/10.1017/S0953820810000440
10. Albrecht, G. L., & Devlieger, P. J. (1999). The disability paradox: High quality of life against all odds. *Social Science & Medicine, 48*(8), 977–988. https://doi.org/10.1016/S0277-9536(98)00411-0
11. Clark, A. E., Diener, E., Georgellis, Y., & Lucas, R. E. (2008). Lags and leads in life satisfaction: A test of the baseline hypothesis. *The Economic Journal, 118*(529), F222–F243. https://doi.org/10.1111/j.1468-0297.2008.02150.x
12. Frederick, S., & Loewenstein, G. (1999). Hedonic adaptation. In D. Kahneman, E. Diener, & N. Schwarz (Eds.), *Well-Being: The Foundations of Hedonic Psychology* (pp. 302–329). Russell Sage Foundation.

### Acceptance

The *adaptive preference* construct in the graph with `counterfactual elicitation` and `temporal-comparison elicitation` as measure nodes, cross-referenced to the *preference structure* construct of POE-EXT-4. **Schema note for DK and Codex:** this item needs a `family_theory_id` that does not currently exist in the corpus — welfare economics / the capabilities approach. The substitution-graph schema's `family_theory_id` column accepts a free-text id, so seeding `welfare_economics_capabilities` as a new theory family is a one-row addition; it is flagged here because it is the agenda memo's open question 4.

---

## Summary of the eight extractions

| Item | Papers | Constructs | Owner | Talk dependency |
|---|---|---|---|---|
| POE-EXT-1 Adaptive thermal | 14 | 5 | AG + CW | Experience 5 |
| POE-EXT-2 VOC/PM/IAQ | 14 | 6 | AG + CW | Experience 7 |
| POE-EXT-3 IAT | 11 | 3 | CW + AG | Three-channel prescription |
| POE-EXT-4 Q-sort | 10 | 4 | CW | Three-channel prescription |
| POE-EXT-5 ESM/EMA | 9 | 3 | CW | Slide-19 diagnosis |
| POE-EXT-6 DGP glare | 8 | 3 | AG + CW | Experience 3 |
| POE-EXT-7 Multisensory | 10 | 4 | AG | (corpus completeness) |
| POE-EXT-8 Adaptive preferences | 12 | 4 | CW | Slide 18 |

Total: 88 papers, 32 constructs. Roughly three to four weeks of wall-clock if AG and CW parallelise across disjoint items (AG: 1, 2, 6, 7; CW: 3, 4, 5, 8).

The four substantive items the talk's empirical claims depend on — POE-EXT-1, 2, 6, 7 — should be extracted before the talk is presented externally. POE-EXT-3, 4, 5, 8 cover the methods the talk recommends and can be extracted in parallel with talk delivery so long as the three-channel argument is framed as a recommendation rather than a track record.

---

## Citation verification note

The DOIs in this package were confirmed against publisher records and CrossRef-indexed sources during the 2026-05-19 session for the marquee papers of each item (de Dear & Brager 2002; Allen et al. 2016; Satish et al. 2012; Greenwald et al. 1998; Blanton et al. 2009; Csikszentmihalyi & Larson 1987; Shiffman, Stone & Hufford 2008; Wienold & Christoffersen 2006; Schweiker et al. 2020; Torresin et al. 2018; Albrecht & Devlieger 1999; Khader 2011). Where a DOI is given without an explicit verification it is the publisher-registered DOI and should resolve, but the paper-acquisition pipeline should treat the full citation (authors, year, title, journal) as authoritative and re-resolve the DOI via CrossRef rather than trusting any single string. Two citations carry minor uncertainty the pipeline should double-check: the Tiller et al. (2010) ASHRAE 1128-RP transaction volume, and the Laurentin, Bermtto & Fontoynont (2000) middle author's name as it appears garbled in some indexes.

---

*End of seed package. Machine-readable companion: `data/poe_ext_substitution_seed.json`. Next action: AG works POE-EXT-1, 2, 6, 7 first per the agenda priority order; CW takes POE-EXT-3, 4, 5, 8 in parallel.*
