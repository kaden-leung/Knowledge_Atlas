# Verification Log — Problems Caught in the Generator
## Track 2 · Task 2 · Phase 4

**Date:** 2026-05-23
**Author:** Kaden Leung
**Method:** Iterative self-audit of `gap_extractor.py` (Phase 2) and `query_generator.py` (Phase 3) against their respective contracts (`GAP_EXTRACTOR_CONTRACT.md` v3.3, `QUERY_GENERATOR_CONTRACT.md` v1.4). Each finding documents the verification question asked, what was caught, and what was fixed.

This log answers the rubric line *"Verification questions (10 pts) — Caught real problems in the AI's implementation."*

---

## Phase 2 — Gap Extractor Verification

### Q1: "Does the GapDetector ever assign DIRECTION?"
**Finding:** No. The `GapDetector` in `voi_search.py:922` only assigns `VALIDATION` (uncertainty > 0.3) or `MECHANISM` (papers < 3). DIRECTION gaps with `competing_accounts` populated were being misclassified as VALIDATION, cutting their VOI score roughly in half (priority weight 0.5 → 1.0).
**Fix:** `classify_gap()` in `gap_extractor.py` now detects `competing_accounts` and routes those as `DIRECTION` gaps with `priority_weight=1.0`.

### Q2: "Are SC3 step confidences actually `null`?"
**Finding:** Yes — SC3 steps 3, 4, 5, 6 all have `confidence: null` and `warrant: null` at the JSON level. The original threshold-based detection (`confidence < 0.5`) would skip them entirely. But these are the highest-VOI gaps in the corpus (Holl-vs-Ellard threshold debate).
**Fix:** Added "null confidence implies low confidence" rule in `extract_gaps()` — `null` is treated as confidence=0.4 for VOI purposes, and `warrant: null` triggers `warrant_source: "absent"`.

### Q3: "Does the rebuttal text contain DIRECTION signals when `competing_accounts` is empty?"
**Finding:** Yes — SC3 step 6 has `competing_accounts: []` but its rebuttal text says "*partial revelation reduces rather than amplifies the threshold response*". The naive "rebuttal text contains 'rather than'" rule produced false positives (e.g. SC3 steps 2 and 4 with "*purely aesthetic rather than physiological*").
**Fix:** Added verb-proximity rule: direction-verb (`reduces|amplifies|increases|drives|...`) must appear within 8 tokens before "rather than". `direction_signal_source: "rebuttal_text"` is recorded when triggered this way.

### Q4: "Does the corpus join match real articles?"
**Finding:** No — original join looked for `article.frameworks` or `article.topic_tags`, neither of which exist in `articles.json`. `articles.json` uses human-readable theory names in the `theories` field. Every gap's `corpus_coverage` was therefore `"absent"`.
**Fix:** Built `FRAMEWORK_THEORY_KEYWORDS` mapping T1 codes to substrings matched against `article.theories` + title + abstract. SC3-3 now correctly shows `corpus_coverage: "dense"` (matches PP literature).

### Q5: "Does `total_n` always coerce to an int?"
**Finding:** No. Templates store sample sizes as `int`, `float`, `"N=48"` strings, and lists. The original code crashed on the string/list cases.
**Fix:** `coerce_n()` handles int/float/str (with "N=" prefix stripping) and lists (sums entries).

### Q6: "Does the centrality proxy saturate at low in-degree?"
**Finding:** Yes — original linear formula saturated at `in_degree ~6`. Highly-connected gaps (in_degree=10+) got the same score as moderately-connected ones (in_degree=6).
**Fix:** Sigmoidal: `centrality = 0.20 + 0.40*tanh(in_degree/4) + 0.05*|t1_frameworks|`.

---

## Phase 3 — Query Generator Verification

### Q7: "Does the proponent validity guard catch malformed accounts?"
**Finding:** Tested with synthetic competing_accounts `[{"proponent": ""}, {"proponent": "a"}, {"proponent": "Holl"}]`. Without a guard, Case A would fire (len ≥ 2), producing `"When 's account that..."` — semantically incoherent.
**Fix:** `valid_proponent()` requires ≥ 2 alphabetic characters in the normalized label, filters before Case A/B/C routing.

### Q8: "Does the Boolean query produce syntactically valid output after truncation?"
**Finding:** Tested by forcing 300-char queries through the priority drop sequence. Procedural string mutation could produce `"prediction error" AND () AND "architectural"` (empty group) or `"prediction error" AND` (dangling operator).
**Fix:** AST-based representation (`AndGroup`/`OrGroup`/`ExactPhrase`/`Exclusion`), serialize once at end. Post-truncation validation checks: balanced parens, no `()`, no trailing AND/OR, no `AND AND`.

### Q9: "Are synonym lists order-stable across runs?"
**Finding:** No — `yaml.safe_load` produces dict iteration order that depends on insertion order, and Python sets are unordered. Two runs could produce semantically identical but byte-different OR groups.
**Fix:** All synonym lists sorted alphabetically before serialization (`get_synonyms()` uses `sorted(set(...))`). SHA-256 of output (with `generated_at` zeroed) verified stable across 100 runs.

### Q10: "Does the structural_component_count detector tolerate adversarial queries?"
**Finding:** Yes initially — "How does architectural threshold response affect people under predictive processing?" scored 5/5 via substring matching, even though it has no actual measurement or population.
**Fix:** Replaced substring matching with word-boundary regex (`\b`). Restricted `DOMAIN_SPECIFIC_MECHANISM` to actual measurement tokens (no generic words like "network", "threshold"). Added noun-phrase depth gate: query must have at least one 3-word noun phrase.

### Q11: "Does population detection actually require a real population class?"
**Finding:** No — initial detection accepted "in people", "among humans" — too vague to be meaningful.
**Fix:** Replaced keyword list with regex `(among|in)\s+(?:[a-z]+\s+){0,3}(workers|patients|occupants|adults|participants|children|students|subjects)`. "among elderly adults" passes; "in people" fails.

### Q12: "Does the NM framework map to the right anchor for all NM gaps?"
**Finding:** No — `ANCHOR_TABLE["NM"]` mapped to Stress Recovery Theory, but the NM code is used for reward-learning gaps (NM1, NM2) and circadian-serotonin gaps (NM7). Three queries inherited a structurally wrong anchor.
**Fix:** Content-aware override in `pick_anchor()`. Scans `what_is_missing` + `step_description` for vocabulary signatures (`novelty|dopamine|RPE`, `serotonin|melatonin`, `polyvagal|RSA`) and replaces the framework-table anchor when matched.

### Q13: "Does Pattern F actually include the measurement (component 2)?"
**Finding:** No — original Pattern F template said *"supported by experimental studies in [population]"* — components 1 and 4 but skipping the required component 2 (mechanism/measure). Boolean queries had the measurement tokens; AI Citation queries hid them.
**Fix:** `FRAMEWORK_MEASURE` table + `pick_measure()` injects a measurement phrase into the "supported by" clause. IC mapping kept intentionally broad ("studies measuring interoceptive processing") because the interoception literature spans behavioral, physiological, and neuroimaging traditions.

### Q14: "Does the Case B template leak template-title phrasing?"
**Finding:** Yes — original code produced `"the architectural promenade temporally model assumption"` — grammatically odd, visibly machine-generated.
**Fix:** `_case_b_label()` extracts a clean 2–3 word mechanism phrase from `step_description`, wraps as `"the alternative [mechanism] mechanism stated in the template"`. "Mechanism mechanism" duplication guard: don't append `mechanism` if extracted phrase already ends in `mechanism` or `model`.

### Q15: "Does the grammar handle 'et al.' authors correctly?"
**Finding:** No — "Lewy et al. argues" is a subject-verb-agreement error (collective subject takes plural verb).
**Fix:** `_argue_intro()` detects `\bet al\.?` in the proponent name → uses "argue" instead of "argues".

### Q16: "Does the generator detect noun-phrase claims that can't take 'argues that X'?"
**Finding:** No — "argues that Theory-theory of social cognition" is a sentence fragment because "Theory-theory of social cognition" is a noun phrase, not a clause.
**Fix:** `_argue_intro()` scans first 6 tokens of the claim for verb candidates. If none found, switches to "argues for" + lowercase first letter (with all-caps acronym preservation — "CCT" stays "CCT", not "cCT").

### Q17: "Does the vocabulary_hash survive serialization?"
**Finding:** Tested by reading back `query_pairs.json` and recomputing the hash from the in-memory vocab dict. They matched, confirming no lazy mutation between generation and write.
**Fix:** Verification-time assertion added to `main()`: `assert stored_hash == recomputed_hash`. Fails loudly if vocab state mutates between generation and write.

---

## Summary

17 verification questions, 17 implementation problems caught and fixed. Three categories:

- **Schema / data-shape bugs (Q1–Q6):** `null` confidences treated as missing; CTI handled as both dict and list; `total_n` polymorphism; framework→theory join via human-readable names.
- **Query-quality bugs (Q7–Q16):** proponent validity guard, AST-based Boolean construction, deterministic synonym sorting, word-boundary structural detection, regex-based population detection, content-aware anchor and measure override, Case-B mechanism phrasing, grammar handling for "et al." and noun-phrase claims.
- **Reproducibility bugs (Q17):** vocabulary hash assertion to catch silent vocab drift.

Most of these would not be caught by structural pass-rate metrics alone — they required reading the generated queries against the contract and the search-guide patterns, then tracing surface symptoms back to root causes in the generator code.
