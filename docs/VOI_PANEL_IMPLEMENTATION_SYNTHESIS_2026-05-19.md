# VOI Panel Implementation Synthesis

**Date**: 2026-05-19
**Status**: Codex implementation synthesis. This is not a real human panel response.
**Governing contract**: `contracts/TOPIC_VOI_PROFILE_CONTRACT_2026-05-19.md`

## Provenance

DK asked for a real panel if one was needed. A real human panel is needed before the Atlas treats the VOI method as academically settled. That panel cannot be honestly claimed to have run inside this coding session. What can be done now is the correct interim step: write the real-panel prompt, use the published positions of the named experts to produce an implementation synthesis, and mark the method as provisional until actual responses are obtained.

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

## Implementation Decision

This pass implements a corpus-signal profile. It reads current KA payloads and writes `data/ka_payloads/topic_voi.json`.

The builder is allowed to use Python for structured computation. Python is not authoring public science prose here; it is assigning auditable ratings from existing structured fields and generating article-finder query strings. The public-facing basis text is a terse audit explanation, not a science-writer claim.

The result is intentionally not final formal VOI. It is the first contract-backed, UI-visible, query-coupled topic profile.

## Last-Mile Requirements

The implementation is not done unless:

- the builder writes a complete payload;
- the verifier passes in strict mode;
- tests cover schema failure cases;
- the topic UI loads `topic_voi.json`;
- the UI has a VOI tab and shows article-finder checks;
- the method status remains `provisional_profile` until a real panel adjudicates it.

