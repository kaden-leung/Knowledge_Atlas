# Real Panel Prompt: Topic-Level Value of Information for the Knowledge Atlas

**Date**: 2026-05-19
**Owner**: DK / Knowledge Atlas
**Use**: Send to real human advisors or run through subscription-AI panel simulation. Do not represent simulation as real external expert response.

## Panel

The panel should include at least the following perspectives:

- Judea Pearl - causal inference, DAGs, do-calculus, confounding.
- Andrew Gelman - Bayesian workflow, multilevel modeling, Type S / Type M error.
- David MacKay or an equivalent information theorist - information gain, coding, entropy.
- Ronald Howard or a decision-analysis successor - classical value of information.
- Carl Bergstrom or Jevin West - computational information science, citation networks, science of science.
- Loet Leydesdorff or a modern informetrics scholar - bibliometrics and entropy measures over literatures.
- Herbert Simon or a decision-science successor - bounded rationality and satisficing.
- Deborah Mayo - severe testing and error-statistical evidential value.
- Paul Thagard - explanatory coherence and theory change.
- Helen Longino - social epistemology and value-laden research priorities.
- Edouard Machery - replication, construct validity, cross-cultural psychology.
- Gyorgy Buzsaki - mechanism, neural generalization, weak mechanism links.

## Context

The Knowledge Atlas has topic pages for environmental cognition, neuroarchitecture, architectural cognition, and adjacent fields. Each topic contains papers, theories, mechanisms, PNUs, measures, instruments, sensors, and science-writer summaries. The system needs to tell students and researchers not merely what is known, but what would be worth learning next.

The current implementation has a provisional ten-target VOI profile. It is not a full expected-value calculation. It uses existing corpus signals to rate each topic on ten kinds of information opportunity:

1. better stimuli
2. better measures
3. better design
4. deconfounding
5. mechanism weak links
6. boundary conditions
7. theory discrimination
8. replication priority
9. design translation
10. WEIRD / cross-cultural extension

## Questions

Please answer as your assigned expert would, but keep the answer operational. The output must help engineers build a contract-backed system.

1. Which of the ten targets are true VOI targets, and which should be renamed, split, or rejected?
2. Should the Atlas expose a single VOI score, a profile, or a profile plus derived summaries?
3. What corpus fields are minimally required to rate each target honestly?
4. What is the right relationship between classical decision-theoretic VOI and the Atlas's practical "what would be worth learning next" use?
5. How should the system account for corpus incompleteness?
6. How should every VOI opportunity be coupled to an article-finder query?
7. What must be different in the student projection and researcher projection?
8. Which claims must the system refuse to make until better data exists?
9. What success conditions and verifiers would prevent the implementation from turning into an opaque heuristic?
10. What would count as a last-mile failure?

## Required Output Format

Return JSON with:

- `panelist`
- `core_position`
- `accepted_targets`
- `rejected_or_split_targets`
- `required_fields`
- `aggregation_position`
- `article_finder_coupling`
- `student_projection`
- `researcher_projection`
- `refusal_rules`
- `success_conditions`
- `last_mile_failures`

