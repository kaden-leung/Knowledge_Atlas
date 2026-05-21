# VOI Source-Grounded Simulated Panel

**Date**: 2026-05-20
**Scope**: Topic-level VOI profile for KA navigation, article finding, and project triage.
**Status**: Simulated expert panel. No named human respondent reviewed this system.
**Governing contract**: `contracts/TOPIC_VOI_PROFILE_CONTRACT_2026-05-19.md`

## Provenance Rule

In this project, a "panel" may mean a source-grounded simulation of expert standpoints. It must never be reported as real correspondence, real review, or real endorsement by the named people. The correct public label is: source-grounded simulated expert panel.

The simulation is allowed to use named thinkers as interpretive anchors only when the output remains in third person and cites the work used to model the standpoint.

## Sources Read For Standpoint Anchoring

- Judea Pearl: structural causal models, causal diagrams, do-calculus, and the requirement that causal claims expose assumptions rather than merely report associations.
  Source: https://bayes.cs.ucla.edu/BOOK-2K/pref.html
- Ronald A. Howard: decision analysis and value of information as a function of alternatives, uncertainty, preferences, and information sources.
  Source: https://www.pearson.com/en-us/subject-catalog/p/foundations-of-decision-analysis/P200000003532/9780132336246
- Andrew Gelman: Bayesian workflow, model checking, multilevel modeling, and criticism of overconfident inference from noisy measures.
  Source: https://arxiv.org/abs/2011.01808
- Helen Longino: contextual empiricism, critical interaction, and the role of values and social assumptions in scientific objectivity.
  Source: https://plato.stanford.edu/archives/fall2016/entries/scientific-knowledge-social/
- Gerd Gigerenzer: decision under uncertainty, bounded rationality, risk communication, and when simple heuristics are legitimate.
  Source: https://www.gerd-gigerenzer.com/
- Loet Leydesdorff and scientometrics: science mapping, reference-set delineation, citation structure, and the risk of treating a map as the territory.
  Source: https://arxiv.org/abs/1208.4566
- Gyorgy Buzsaki: inside-out neuroscience, brain rhythms, active organism-environment loops, and the danger of reducing mechanism to passive stimulus coding.
  Source: https://faculty.washington.edu/seattle/brain-physics/textbooks/buzsaki.pdf
- Edouard Machery: construct validity, replication, external validity, and the limits of treating folk or inherited categories as stable scientific kinds.
  Source: https://www.cambridge.org/core/services/aop-cambridge-core/content/view/F41B751ECC31462CBBD46711BC733AEE/S003182480001638Xa.pdf/what_is_a_replication.pdf

## Simulated Panel Findings

### 1. Causal Structure

The topic VOI layer must not treat correlations, topic co-occurrence, or paper counts as causal information. A topic becomes high priority only when new information could change a claim in the web of belief: a mechanism, a boundary, a warrant, a causal direction, a theory discrimination, or a design implication. Pearl's standpoint therefore requires the payload to expose what claim could change and what assumptions remain untested.

### 2. Decision-Theoretic Scope

The current topic profile is not formal VOI. Howard's standpoint requires alternatives, priors, likelihoods, utilities, and information costs. The KA topic profile lacks those decision objects. It may rank and route attention, but the numeric value must be called a routing score and must carry `score_semantics = heuristic_routing_only_not_expected_value`.

### 3. Statistical Humility

Gelman's standpoint rejects overconfident single-number summaries where measures are noisy, models are unchecked, or data are sparse. The topic profile must show target confidence, missing fields, score components, and degenerate-rating checks. A medium rating with low extraction coverage is more honest than a high rating produced by a thin keyword match.

### 4. Values And Social Assumptions

Longino's standpoint requires the system to surface the value context. Design translation is not purely epistemic: it can serve different stakeholders and encode assumptions about comfort, productivity, health, equity, and cultural fit. The payload therefore records stakeholder scope, possible value conflict, and missing evidence.

### 5. Heuristic Legitimacy

Gigerenzer's standpoint allows heuristics when the environment is uncertain and the tool is used transparently. The topic VOI builder can be heuristic if it is simple, auditable, and bounded. It must not masquerade as an optimizing expected-utility engine.

### 6. Information Retrieval Coupling

Leydesdorff and information-retrieval standpoints require the topic profile to be coupled to search. A VOI target is useful only if the next search can test whether the opportunity remains open. Each target must include broad and narrow queries, known-work exclusions, and a query-test statement.

### 7. Mechanism Discipline

Buzsaki's standpoint resists passive stimulus-response simplification. Mechanism work should distinguish levels of analysis, organism action, timing, and measurable mediators. PNU summaries alone do not count as direct mechanism evidence.

### 8. Construct Validity And Replication

Machery's standpoint requires sharper treatment of constructs and replication. A measure count is not construct validity. A replication is not just another related paper; it should resample relevant experimental components and test reliability or scope. The profile therefore separates measurement quantity from measurement validity and exposes missing construct-validity fields.

## Resulting Governance Principles

1. Simulated panels are legitimate project governance tools only when labeled as simulated.
2. The current topic VOI layer remains provisional, but it is no longer "pending a real human panel" as a default project requirement.
3. Formal VOI remains pending a calibrated decision model, not merely a better panel.
4. A routing score is not expected value.
5. Missing extraction is not evidence of absence.
6. Every target must be article-finder-coupled.
7. Measurement, mechanism, population scope, and design translation require special missing-evidence discipline.

## Implementation Status

The 2026-05-20 simulated panel confirms the main design already implemented on 2026-05-19, with one correction: documentation should stop implying that a real-human panel is the normal next requirement. The correct next requirement is a calibrated formal decision model if the project wants formal VOI rather than provisional routing.

