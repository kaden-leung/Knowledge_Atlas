# Topic VOI Profile Contract

**Contract id**: `TOPIC_VOI_PROFILE_CONTRACT_2026-05-19`
**Scope**: Per-topic Value of Information profiles on the Knowledge Atlas.
**Status**: Active, provisional-method contract pending real human panel review.

## Purpose

The topic VOI layer exists to answer one practical question: what would be most worth learning next about this topic? It must not reduce that question to a single opaque number. A topic can be high value because it needs better stimuli, better measures, deconfounding, mechanism-link tests, boundary-condition work, theory discrimination, replication, design translation, or cross-cultural extension. Those are different reasons and must remain visible.

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
   - `score`: numeric, 0.0 to 1.0.
   - `basis`: a human-readable explanation of which corpus signals drove the rating.
   - `evidence_signals`: structured fields sufficient to audit the rating.
   - `article_finder_query`: structured query object.
   - `internal_search_url`: KA search URL that lets the user check the existing corpus.
6. `student_projection`: the four targets shown by default for COGS 160 feasibility work.
7. `researcher_projection`: all ten targets, sorted by score.
8. `coverage_confidence` and `computed_at`.

## Article-Finder Coupling

Every non-`na` target must include an article-finder query with:

- `natural_language_query`: a plain-language query suitable for Google AI Citation or a subscription search assistant.
- `boolean_query`: a conservative Google Scholar / library style query.
- `structured_query`: fields `topic_id`, `target_id`, `include_terms`, `require_terms`, `exclude_known_papers`, `freshness_after_year`, and `candidate_sources`.
- `internal_search_url`: a `ka_search.html?q=...` link that checks the Atlas corpus first.

The query must be a way to test whether the opportunity is still open. It must not be a decorative label.

## Method Discipline

This contract permits heuristic scoring only when the payload marks `method_status` as `provisional_profile`. Heuristics may rank and route topics, but they may not be described as formal expected-value calculations.

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

## Last-Mile Verification

The last mile is not complete until all of these commands pass:

```bash
python3 scripts/build_topic_voi_payload.py
python3 scripts/verify_topic_voi_contract.py --strict
pytest tests/test_topic_voi_contract.py
```

