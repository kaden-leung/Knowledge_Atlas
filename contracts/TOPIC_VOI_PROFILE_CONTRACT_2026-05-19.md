# Topic VOI Profile Contract

**Contract id**: `TOPIC_VOI_PROFILE_CONTRACT_2026-05-19`
**Scope**: Per-topic Value of Information profiles on the Knowledge Atlas.
**Status**: Active, provisional-method contract pending real human panel review.

## Purpose

The topic VOI layer exists to answer one practical question: what would be most worth learning next about this topic? It must not reduce that question to a single opaque number. A topic can be worth further attention because it needs better stimuli, construct-valid measurement, causal or severe design, deconfounding, mechanism-link tests, boundary-condition work, theory discrimination, replication, design translation, or population-scope evidence. Those are different reasons and must remain visible.

The current payload is a provisional, AI-simulated expert-panel implementation. It is not a real human panel judgment. It is also not a formal expected-value calculation, because no decision alternatives, priors, likelihoods, utilities, or search costs have been specified.

## Required Output

Every generated topic VOI payload must contain:

1. `contract_id` equal to `TOPIC_VOI_PROFILE_CONTRACT_2026-05-19`.
2. `target_definitions` for exactly ten targets:
   - `target_1_better_stimuli`
   - `target_2_better_measures`
   - `target_3_better_design`
   - `target_4_deconfounding`
   - `target_5_mechanism_weak_links`
   - `target_6_boundary_conditions`
   - `target_7_theory_discrimination`
   - `target_8_replication_priority`
   - `target_9_design_translation`
   - `target_10_weird_extension`
3. One `topics` entry per visible topic in `data/ka_payloads/topics.json`.
4. For each topic, a `target_vector` object with exactly those ten target ids.
5. For each target entry:
   - `rating`: one of `high`, `medium`, `low`, `na`.
   - `score` and `routing_score`: numeric, 0.0 to 1.0, rounded to two decimals and marked as heuristic routing only.
   - `score_semantics`: exactly `heuristic_routing_only_not_expected_value`.
   - `score_formula_version` and `score_components`.
   - `basis`: a human-readable explanation of which corpus signals drove the rating.
   - `target_confidence`, `target_coverage_confidence`, `signal_strength`, `positive_signals`, `negative_signals`, `missing_required_signals`, and `missing_evidence_flags`.
   - `evidence_signals`: structured fields sufficient to audit the rating.
   - `article_finder_query`: structured query object.
   - `internal_search_url`: KA search URL that lets the user check the existing corpus.
6. `student_projection`: the four targets shown by default for COGS 160 feasibility work.
7. `researcher_projection`: all ten targets, sorted by score.
8. `coverage_confidence` with named components, `topic_graph_links`, `citation_context`, `corpus_snapshot`, and `computed_at`.

## Article-Finder Coupling

Every non-`na` target must include an article-finder query with:

- `natural_language_query`: a plain-language query suitable for Google AI Citation or a subscription search assistant.
- `boolean_query`: a conservative Google Scholar / library style query.
- `broad_query` and `narrow_query`: one query to discover the neighborhood and one query to test the target.
- `known_work_terms`: title/DOI/PDF terms that should not be mistaken for fresh evidence.
- `query_test`: fields explaining what would keep the opportunity open and what would close or lower its priority.
- `structured_query`: fields `topic_id`, `target_id`, `include_terms`, `require_terms`, `exclude_known_papers`, `external_exclusion_terms`, `freshness_after_year`, and `candidate_sources`.
- `internal_search_url`: a `ka_search.html?q=...` link that checks the Atlas corpus first.

The query must be a way to test whether the opportunity is still open. It must not be a decorative label.

## Method Discipline

This contract permits heuristic scoring only when the payload marks `method_status` as `provisional_profile`. Heuristics may rank and route topics, but they may not be described as formal expected-value calculations.

The UI must display the ordinal rating first. Numeric routing scores may be available for audit, but the public language must not use phrases such as "highest-value topic bundles", "expected value", "optimal", or "VOI score" unless the same view also states that the quantity is heuristic routing only.

The first production method may use existing payload fields:

- topic paper count, maturity, mean credence, mean omega
- replication and contradiction counts
- article type distribution
- theory and construct tags
- instruments, measures, sensors, and visual/stimulus asset fields
- science-summary and PNU status fields
- topic memberships, IV roots, DV focuses
- existing question-bank and gap text

The method must not invent missing evidence. If a target depends on fields not yet extracted, the target must say so in `basis` and lower `coverage_confidence`.

Special target rules:

- Construct and measurement quality must distinguish measurement quantity from measurement validity. Sensors are not automatically better than self-report, and self-report is not automatically invalid.
- Mechanism-link uncertainty must not treat a PNU summary as direct mechanism evidence unless level of analysis, causal link, and observable mediator evidence are extracted.
- Population and cultural scope must not infer cross-cultural adequacy from silence. It must expose population, country, language, recruitment, and measurement-invariance extraction status.
- Design translation must mark the stakeholder and value context, because usefulness to practice and truth of the causal claim are distinct.

## Success Conditions

SC-VOI-1: Payload exists at `data/ka_payloads/topic_voi.json`.

SC-VOI-2: The payload has exactly ten target definitions and every topic has exactly ten target entries.

SC-VOI-3: No target entry lacks an article-finder query.

SC-VOI-4: The UI renders VOI as a profile/grid, not as a single authority score.

SC-VOI-5: Student view defaults to targets 1, 2, 4, and 8; researcher view preserves all ten.

SC-VOI-6: Every rating has an auditable basis tied to corpus signals.

SC-VOI-7: The verifier fails if any topic from `topics.json` is missing.

SC-VOI-8: The verifier fails if any `internal_search_url` does not point to KA search.

SC-VOI-9: The payload states clearly that the current method is provisional pending the real panel.

SC-VOI-10: No single composite VOI authority score is exposed as the final answer.

SC-VOI-11: The payload and UI state that the current panel is AI-simulated and not a named human panel.

SC-VOI-12: Every target has `signal_strength`, score components, missing-evidence flags, and target confidence.

SC-VOI-13: Cross-cultural and population-scope targets expose extraction status rather than treating missing population evidence as evidence of WEIRD limitation.

SC-VOI-14: Construct/measurement targets expose construct-validity fields or missing-field flags.

SC-VOI-15: Mechanism targets do not treat PNU summaries alone as direct mechanism evidence.

SC-VOI-16: Researcher projections are sorted, top targets match the projection, and degenerate all-high target distributions fail verification.

## Last-Mile Verification

The last mile is not complete until all of these commands pass:

```bash
python3 scripts/build_topic_voi_payload.py
python3 scripts/verify_topic_voi_contract.py --strict
pytest tests/test_topic_voi_contract.py
```
