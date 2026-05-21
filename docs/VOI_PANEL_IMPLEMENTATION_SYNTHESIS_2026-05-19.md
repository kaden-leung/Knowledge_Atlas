# VOI Panel Implementation Synthesis

**Date**: 2026-05-19
**Status**: Codex implementation synthesis from a source-grounded simulated expert panel. This is not a real human panel response.
**Governing contract**: `contracts/TOPIC_VOI_PROFILE_CONTRACT_2026-05-19.md`

## Provenance

DK clarified that KA panels are normally simulated expert panels, not live human respondents. The correct provenance standard is therefore not "pending real people"; it is "source-grounded simulated panel, clearly labeled." This synthesis uses named thinkers only as standpoint anchors and does not claim correspondence, review, or endorsement by those people. The current method remains provisional because it is a routing profile, not a calibrated formal VOI decision model.

The source-grounded simulated panel record is `docs/VOI_SOURCE_GROUNDED_SIMULATED_PANEL_2026-05-20.md`.

## Simulated Panel Corrections Incorporated

The second implementation pass incorporated four simulated expert lanes:

1. **Causal and epistemic structure**: the profile must measure epistemic leverage, not topical importance. Each target must identify the belief, mechanism, scope, or design claim that could change. Missing extraction is not evidential absence.
2. **Decision theory and statistics**: the public system must not dignify heuristic decimals as formal expected value. The payload now marks `score_semantics` as `heuristic_routing_only_not_expected_value`, exposes `routing_score`, and records that the formal decision context is absent.
3. **Information retrieval and bibliometrics**: each target now carries broad and narrow queries, known-work exclusions, query-test language, topic graph links, citation-context proxies, and corpus-snapshot fields.
4. **Construct validity and value sensitivity**: measurement quantity is separated from measurement quality; PNU summaries alone do not count as direct mechanism evidence; population and culture claims expose extraction status; design translation records the stakeholder and value context.

## Convergent Implementation Positions

The provisional implementation follows five positions that are stable across the relevant literatures.

1. **Profile, not scalar**. Pearl, Mayo, Thagard, Longino, and Gelman would all object, for different reasons, to hiding distinct evidential opportunities inside one authority number. The UI must show the ten-target profile.
2. **Decision-theoretic humility**. Howard-style VOI requires a decision, prior, likelihood model, cost, and utility function. The current Atlas does not yet have all of those. The implementation must call itself `provisional_profile`, not formal expected VOI.
3. **Article-finder coupling**. Every VOI opportunity must be testable by asking whether the literature has already filled it. The payload therefore carries a natural-language query, Boolean query, structured query, and internal KA search URL for every target.
4. **Severity and structure matter**. Mayo and Pearl force the system to distinguish a merely numerous literature from a severe, deconfounded, structurally informative literature.
5. **Corpus incompleteness must be visible**. Bergstrom, West, Leydesdorff, and Longino would all reject a VOI score that pretends corpus coverage is complete. Each topic therefore carries a `coverage_confidence`.

## Operating Principles

- VOI means expected epistemic leverage, not topical interestingness.
- A high value topic is one where a feasible new study or search could change the Atlas's beliefs, warrants, mechanisms, scope, or design advice.
- VOI target ratings must remain tied to the web of belief: warrant strength, severity, mechanism links, replications, contradictions, scope, and theory discrimination.
- Student VOI is a projection of the same profile, restricted to targets that can guide a 7-to-10-week project.
- Researcher VOI preserves the full ten-target profile.
- The system must prefer "unknown because not extracted" over invented certainty.
- The UI must make the reason for each target visible before a user acts on it.
- The UI must display ordinal ratings first. Numeric routing scores are audit aids, not authority.
- Article-finder queries are part of the claim: a target is useful only if the query can test whether the opportunity remains open.

## Implementation Decision

This pass implements a corpus-signal profile. It reads current KA payloads and writes `data/ka_payloads/topic_voi.json`.

The builder is allowed to use Python for structured computation. Python is not authoring public science prose here; it is assigning auditable ratings from existing structured fields and generating article-finder query strings. The public-facing basis text is a terse audit explanation, not a science-writer claim.

The result is intentionally not final formal VOI. It is the first contract-backed, UI-visible, article-finder-coupled topic profile.

## Last-Mile Requirements

The implementation is not done unless:

- the builder writes a complete payload;
- the verifier passes in strict mode;
- tests cover schema failure cases;
- the topic UI loads `topic_voi.json`;
- the UI has a VOI tab and shows article-finder checks;
- the payload exposes score semantics, formula version, formula components, target confidence, missing evidence, and signal strength;
- the verifier rejects degenerate all-high target distributions, unsorted researcher projections, and target/query mismatches;
- the method status remains `provisional_profile` until a calibrated formal decision model exists.
