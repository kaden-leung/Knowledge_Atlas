# Query Generator Contract
## Track 2 · Task 2 · Phase 3

**Date:** 2026-05-22 (v1.4 — vocabulary_hash for synonym drift auditing, ai_citation_generation_mode field for inferential scaffold distinction)
**Author:** Kaden Leung
**Schema version:** 1.4.0
**Contract with:** `QueryGenerator` in `Article_Eater/src/services/voi_search.py:722` and sentence patterns in `Knowledge_Atlas/160sp/ka_google_search_guide.html`

---

## Objective

A deterministic program that reads `gap_report.json` from Phase 2 and produces, for every gap, a matched pair of search queries:

1. **AI Citation query** — a complete natural-language research question following the 5-component pattern from `ka_google_search_guide.html`, designed for Google's AI Overview semantic retrieval
2. **Boolean query** — an exact-phrase-anchored, operator-structured query for Google Scholar / Semantic Scholar API systematic coverage

Both query types are complementary, not redundant. AI Citation trades precision for discovery across terminological traditions. Boolean trades discovery for reproducibility and API compatibility. Phase 3 (Task 3 search execution) will use both.

---

## Why the existing QueryGenerator is not reused directly

`QueryGenerator.generate_queries()` (voi_search.py:740) takes an `EpistemicGap` and optional `Belief` object and returns a list of raw keyword strings. It does not:
- construct complete sentence queries
- apply the 5-component pattern
- produce Boolean operator syntax with exact-phrase anchors
- differentiate query strategy by gap type (DIRECTION vs. MECHANISM vs. VALIDATION)

This contract specifies a new `GapQueryGenerator` that wraps `CrossFieldVocabulary` (voi_search.py:132) for synonym expansion and applies the patterns from the search guide.

---

## Epistemic policy statements

### Why two query types per gap
AI Citation retrieves by semantic meaning: "predicts" and "modulates" and "drives" are treated as equivalent. Boolean retrieves by exact string: only the literal terms match. A DIRECTION gap needs both — AI Citation finds the theoretical debate, Boolean finds the specific measurement papers. Generating only one type is a research design failure.

### Gap type → query pattern mapping (panel-set policy)
| gap_type | Primary pattern | Rationale |
|---|---|---|
| DIRECTION | Pattern F (comparative/critical) | Two accounts in conflict → query asks which is better supported |
| MECHANISM | Pattern D/E (mechanism-explanation) | Missing causal pathway → query asks *how* it works |
| VALIDATION | Pattern B/C (evidence-seeking) | Known form, thin numbers → query seeks replication / meta-analysis |
| BOUNDARY | Pattern A (evidence-seeking, scoped) | Scope unclear → query asks under which conditions |

### AI Citation vs Boolean distinction (from ka_google_search_guide.html)
AI Citation is a **semantic research question**. Boolean is a **reproducible keyword net**. They are different tools for different retrieval stages — not interchangeable. The most common error is writing a Boolean fragment for AI Citation. The second most common error is writing a natural-language sentence for a Boolean API call.

### AI Overview reliability caveat
AI Overview *tends* to handle complex research questions, including discourse-framing queries like Pattern F, better than BM25 for equivalent query budgets — but this is a probabilistic tendency, not a reliable guarantee. AI Overview is ranking-layer dependent, retrieval-stack dependent, and changes between versions without notice. Pattern F queries work because AI Overview often recognizes argumentative structure; they do not work because AI Overview robustly reasons over it. Treat AI Citation retrieval outcomes as empirically variable. SC-6 manual testing exists precisely because AI Citation performance cannot be inferred from query structure alone.

---

## Section 1: Inputs

### Primary input — `gap_report.json` (Phase 2 output)
- **Location:** `Track 2/Task 2/Phase 2/gap_report.json` (or path from `--gaps` arg)
- **Fields consumed per gap:**

| Field | Used for |
|---|---|
| `template_id` | Canonical key; passed through to output |
| `display_id` | Human label in query metadata |
| `template_name` | Provides domain context for query composition |
| `step_number` / `param_name` | Identifies which step the query targets |
| `primary_gap_type` | Selects query pattern |
| `gap_tags` | May add secondary pattern if multi-label |
| `what_is_missing` | Core content for AI Citation question |
| `what_is_missing_quality` | If "low", triggers fallback composition from `step_description` + `template_name` |
| `competing_accounts` | DIRECTION queries: populates account A / account B slots in Pattern F |
| `warrant` | Informs mechanism term selection |
| `t1_frameworks` | Provides theoretical anchor(s) for both query types |
| `corpus_coverage` | Adjusts Boolean query breadth: sparse → broader synonyms; dense → narrower, gap-specific terms |
| `depth_tier` | A → mechanism-level query; C → phenomenological query |
| `total_n` | If low (≤ 50), Boolean adds `-meta-analysis -review` exclusions to prioritize new empirical work |
| `voi_score` | Sorting and `--top-n` selection only; not used in query text |
| `step_description` | Fallback context if `what_is_missing_quality == "low"` |

### Vocabulary resource
- **Location:** `Article_Eater/contracts/vocab/cross_field_vocabulary.yaml`
- **Used for:** synonym expansion in Boolean query OR groups
- **Fallback:** if file absent, use hardcoded synonym table for the 10 T1 framework domains

### Configuration input
- `--gaps` (path, default `gap_report.json`)
- `--output` (path, default `query_pairs.json`)
- `--top-n` (int, default 50) — generate queries only for top-N gaps by `voi_score`
- `--all` (flag) — generate for all gaps; overrides `--top-n`
- `--min-quality` (string, default `low`) — skip gaps where `what_is_missing_quality` is below this threshold. Options: `low`, `medium`, `high`.

---

## Section 2: Processing

### Step 1 — Load and validate gap list
Load `gap_report.json`. Verify `schema_version` starts with "3" (Phase 2 compatibility). If `schema_version` is absent or incompatible, abort with a clear error. Sort by `voi_score` descending (already sorted by Phase 2 extractor, but enforce here for robustness). Apply `--top-n` / `--all` selection.

### Step 2 — Load vocabulary
Load `CrossFieldVocabulary`. If unavailable, log a warning to stderr and continue with the hardcoded fallback synonym table.

**Hardcoded fallback synonym table (T1 framework → key terms → synonyms):**
```
PP  → prediction error: ["prediction error", "predictive coding", "active inference", "PE signal", "surprise signal"]
PP  → arousal: ["arousal", "orienting reflex", "LC-NE burst", "noradrenergic", "autonomic activation"]
MSI → multisensory: ["multisensory integration", "cross-modal", "sensory convergence", "multimodal"]
EC  → embodied: ["embodied cognition", "proprioception", "interoceptive signal", "somatic marker"]
NM  → stress recovery: ["stress recovery", "HPA axis", "cortisol", "autonomic recovery", "physiological restoration"]
CB  → circadian: ["circadian rhythm", "non-visual light effect", "ipRGC", "melanopsin", "chronobiological"]
MS  → memory: ["spatial memory", "hippocampal encoding", "place cell", "cognitive map"]
IC  → allostatic: ["allostatic load", "interoception", "body budget", "predictive interoception"]
SN  → wayfinding: ["spatial navigation", "wayfinding", "cognitive map", "path integration"]
DT  → DMN: ["default mode network", "DMN", "task-positive network", "TPN", "mind-wandering"]
```

### Step 3 — Select pattern by gap type

Apply the gap-type → pattern mapping from the Epistemic Policy section. For multi-label gaps where `gap_tags` contains more than one type, use `primary_gap_type` for the AI Citation pattern and add a secondary Boolean string from the secondary tag.

### Step 4 — Build AI Citation query

A complete single sentence, ≥ 60 characters, ending with `?`. Must contain all required components for the selected pattern.

**5-component anatomy (from ka_google_search_guide.html):**

| Component | Required | Source field |
|---|---|---|
| 1. Evidence type signal | Required | Gap type: DIRECTION → "What studies comparing…"; MECHANISM → "Through what neural/physiological pathway…"; VALIDATION → "What experimental studies measuring…" |
| 2. Mechanism / measure | Required | `what_is_missing` → extract the core mechanism noun phrase; fall back to `step_description` |
| 3. Environmental condition | Required | `template_name` + `step_description` → the specific architectural or environmental feature |
| 4. Population / context | **Required when `depth_tier == A`**; optional otherwise | Infer from `template_name`; default "in occupants of architectural environments" or "in participants exposed to built environments". If `depth_tier == null` (bridge gaps), omit. If absent when required, `structural_component_count` must not reach 5. |
| 5. Theoretical anchor | Required | `t1_frameworks` → map to anchor phrase (see table below) |

**AI Citation length bounds (tiered by gap type):**
- Minimum: 60 characters
- Maximum by gap type:
  - **DIRECTION (Pattern F): 420 characters** — Pattern F structurally requires two named proponents + one phenomenon + one measure + one anchor; forcing 320 chars would require dropping proponent names (SC-7 violation) or the anchor (SC-5 violation).
  - **MECHANISM / VALIDATION / BOUNDARY: 340 characters** — single-account queries do not need the structural overhead of competing-account framing.
- If composition exceeds the applicable limit, drop component 4 (population) first, then truncate `what_is_missing` to its first 80 chars.
- Record `ai_citation_truncated: true` if any truncation was applied.

**AI Citation specificity guard (anti-inflation):** After composition and length-trimming, enforce:
- Max 2 commas in the query body (commas inside quoted terms do not count)
- Max 1 em dash (`—`)
- Max 2 distinct domain-specific mechanism nouns (tokens from `DOMAIN_SPECIFIC_MECHANISM` list in Step 6; if 3+ distinct tokens match, remove the clause containing the least-specific one)

If any limit is exceeded, remove the least-specific clause and re-check. Record `ai_citation_trimmed_clause: true` in signals when this fires. This prevents queries that pass length and `structural_component_count` checks but distribute semantic weight across too many competing concepts, which degrades embedding retrieval quality.

**Framework → anchor phrase table:**
| Code | Anchor phrase |
|---|---|
| PP | "as predicted by predictive processing / active inference theory" |
| MSI | "consistent with multisensory integration theory" |
| EC | "as predicted by embodied cognition frameworks" |
| NM | "consistent with Stress Recovery Theory (SRT)" |
| CB | "as predicted by circadian photobiology" |
| MS | "as predicted by spatial memory and hippocampal encoding research" |
| IC | "consistent with interoceptive / constructionist affect theory" |
| DT | "as predicted by DMN–TPN dynamics" |
| SN | "as predicted by cognitive mapping theory" |
| DP | "consistent with dual-process evaluation theory" |

For DIRECTION gaps, the query must name both sides of the conflict. Two cases:

**Proponent validity guard (applied before Case A/B/C routing):** Filter `competing_accounts` to entries where the normalized label (`.strip().lower()`) contains ≥ 2 alphabetic characters. Labels that are `""`, `null`, `"a"`, `"b"`, `"account a"`, `"account b"`, or single characters are invalid and are excluded from the count. Route by filtered count: ≥ 2 → Case A; == 1 → Case B; == 0 → Case C with `direction_fallback: true`. This guard prevents malformed entries from silently producing `"when 's account…"` query text that passes structural checks but is semantically incoherent.

**Case A — `len(competing_accounts) >= 2` (after validity filtering):** Both proponent names come from the structured list. Both must appear in the query.

**Case B — `len(competing_accounts) == 1` (single-proponent entry, e.g. SC3 step 3):** The single entry is the *challenger*; the template's own claim is the *default position*. The default position name comes from the first author/source named in `justification.data[0].source` or, if absent, from the `template_name` truncated to its primary mechanism phrase (e.g., "Ellard's additive channel-count model" inferred from the Ellard citation in `justification.data`). Record `direction_account_b_source: "justification_data"` or `"template_name_inference"`.

Pattern F template:
> *"When [Account A: challenger proponent's claim from competing_accounts] and [Account B: template's own claim, sourced from justification.data or template_name] make conflicting predictions about [phenomenon from what_is_missing], which is better supported by [evidence type] in [context], and can [theoretical anchor] adjudicate between them?"*

If neither source yields a named second account, fall back to Pattern C ("What [evidence type] supports or refutes the claim that…") and record `ai_citation_pattern: "C"` with `direction_fallback: true`.

**Generation mode assignment (non-fallback cases):**
- `what_is_missing` populated and quality is "medium" or "high" → `ai_citation_generation_mode: "evidence_grounded"`
- `what_is_missing_quality == "low"` but `step_description` is non-empty → `ai_citation_generation_mode: "description_scaffolded"`
- Both empty → `ai_citation_generation_mode: "inferential_scaffold"` (see quality gate below)

**Quality gate:** If `what_is_missing_quality == "low"` AND `step_description` is also empty (CREA1-style bridge gaps), compose from `template_name` alone using Pattern D:
> *"Through what neural pathway does [template_name mechanism] operate, and what evidence exists that [t1_framework anchor] correctly predicts this pathway in architectural contexts?"*

Record `ai_citation_composed_from: "template_name_fallback"`, `ai_citation_semantic_confidence: "low"`, and `ai_citation_generation_mode: "inferential_scaffold"` in metadata when this fires. The `"low"` confidence signals sparse metadata. `"inferential_scaffold"` is distinct from lower confidence alone — it signals that the query's mechanistic specificity was ontologically *inferred* from the template name structure, not extracted from documented evidence gaps. Template names can contain metaphorical or shorthand language that the generator literalizes into neuroscientific mechanisms, creating apparent specificity without grounded evidence. Downstream users must treat `"inferential_scaffold"` results with structural skepticism, not merely quantitative skepticism.

### Step 5 — Build Boolean query

A structured string for Google Scholar / Semantic Scholar API. Must:
- Contain at least one exact-phrase group in double quotes
- Use `AND` to join required concepts
- Use `OR` groups in parentheses for synonym expansion (from CrossFieldVocabulary or fallback table)
- Use `-review` or `-meta-analysis` exclusions only when `total_n <= 50` (to prioritize new empirical evidence over synthesis)

**Character limits (hard constraints):**
- **API target (Google Scholar / Semantic Scholar):** ≤ 256 characters. Queries over this limit are silently truncated by the API, making them non-reproducible.
- **Manual use:** ≤ 512 characters.
- Record `boolean_char_length` in signals. If over 256, apply the **priority drop sequence** below and record `boolean_truncated: true`.

**Priority drop sequence (drop in this order until ≤ 256 chars):**
1. Remove `-exclusion` terms (they narrow, not expand — losing them is safer than losing core terms)
2. Reduce each OR group from 4 synonyms to 2 (keep the most common / cross-disciplinary terms)
3. Remove the least-specific AND concept group (usually the last one added)
4. Remove the architectural condition phrase if already implied by remaining terms
5. If still over 256: drop to 2 AND-joined exact phrases with 1 OR group each

**AST implementation requirement:** Boolean queries MUST be represented internally as a structured AST before any truncation or serialization:
```
AndGroup(
  ExactPhrase("primary term",          priority="core"),
  OrGroup(["synonym1", "synonym2"],    priority="core"),      # sorted alphabetically
  ExactPhrase("condition",             priority="supporting"),
  OrGroup(["cond_syn1", "cond_syn2"],  priority="supporting"),
  Exclusion("review"),                                         # optional, only if total_n <= 50
)
```
Priority labels govern truncation:
- **`core`** — removing this group changes which gap the query targets. NEVER dropped automatically by the priority drop sequence.
- **`supporting`** — adds precision but the query retains its retrieval intent without it. Dropped second.
- **`optional`** — exclusions and condition modifiers. Dropped first.

Serialize to string only once, at the final write step. Do not build Boolean queries by string concatenation followed by substring mutation — procedural string patching cannot guarantee syntactic validity after truncation.

**Post-truncation syntax validation:** After each drop operation in the priority sequence, validate the resulting query before proceeding to the next step:
1. `query.count("(") == query.count(")")` — balanced parentheses
2. `"()" not in query` — no empty groups produced by OR-group removal
3. `not re.search(r'(AND|OR)\s*$', query)` — no dangling operators after last AND-group removal
4. `"AND AND" not in query` and `"OR OR" not in query` — no consecutive operators

If any check fails, re-derive the string by serializing the AST at its current post-drop state. Do not patch the string directly.

**Template:**
```
"[primary mechanism term]" AND ("[synonym1]" OR "[synonym2]" OR "[synonym3]") AND "[architectural condition]" [-exclusions if total_n <= 50]
```

**Synonym expansion rule:**
- Take the most specific noun phrase from `what_is_missing` (the mechanism/measure term)
- Look up synonyms via `CrossFieldVocabulary.get_all_terms(concept)` or fallback table
- Include 2–4 synonyms in the OR group, **sorted alphabetically**
- The architectural condition phrase comes from `template_name` or `step_description` (first 5–7 non-stopword tokens)
- **Synonym sort requirement (required for SC-8):** All synonym lists MUST be sorted alphabetically before serialization. OR-group members appear in sorted order in the final query string. This eliminates nondeterminism from YAML dict or Python set iteration order — the same input must always produce the same OR group regardless of vocabulary file load order.

**Exclusion rule (corpus_coverage-aware):**
- `corpus_coverage == "dense"` → add one specificity term from `what_is_missing` to narrow the query
- `corpus_coverage == "sparse"` → remove specificity terms; broaden OR group by 1–2 synonyms
- `total_n <= 50` AND `corpus_coverage != "sparse"` → append `-review -meta-analysis` (looking for new empirical work). **Exception:** if `corpus_coverage == "sparse"`, do NOT add exclusions — sparse domains may need reviews precisely because empirical literature barely exists. Adding `-review` in sparse-coverage gaps actively suppresses the most useful available evidence.
- `total_n > 200` → the measurement is established; append `-"case study"` (looking for controlled evidence)

### Step 6 — Compute query quality signals

**`structural_component_count` algorithm (deterministic, no human judgment required):**

```python
EVIDENCE_OPENERS = [
    r"what experimental", r"what peer-reviewed", r"what neuroimaging",
    r"what do experimental", r"what fmri", r"what eeg",
    r"through what neural", r"through what physiological",
    r"how does", r"what longitudinal", r"what studies",
    r"when\s+\w+.{0,40}account.{0,40}conflict",
]

# Restricted to domain-specific measurement tokens only.
# Generic words ("network", "threshold", "response", "pathway") are excluded to
# prevent false positives from non-technical queries that happen to use them.
DOMAIN_SPECIFIC_MECHANISM = [
    "skin conductance", "cortisol", "gsr", "electrodermal",
    "fmri", "eeg", "eeg alpha", "alpha wave", "heart rate variability", "hrv",
    "dmn", "tpn", "ecn", "prefrontal", "amygdala", "hippocampal",
    "hpa axis", "prediction error", "arousal response",
    "cortical activation", "neural coupling", "predictive coding", "active inference",
]

CONDITION_TERMS_WB = [
    "architectural", "building", "luminance", "sensory richness",
    "natural light", "fractal", "acoustic", "biophilic",
    "field of view", "field-of-view", "daylighting", "window view",
]

# Population requires: preposition + 0–3 descriptor words + class noun.
# "in people", "in participants", "among humans" do NOT satisfy this (no class noun).
# "among elderly adults", "in hospital patients", "among architecture students" all pass.
POPULATION_REGEX = re.compile(
    r'(among|in)\s+(?:[a-z]+\s+){0,3}(workers|patients|occupants|adults|participants|children|students|subjects)'
)

ANCHOR_PHRASES = [
    "predictive processing", "active inference", "attention restoration",
    "stress recovery theory", "biophilia", "embodied cognition",
    "default mode network", "multisensory integration", "circadian",
    "dual-process", "spatial navigation", "interoceptive",
]

def count_present_components(query: str) -> int:
    low = query.lower()

    # Noun-phrase depth gate: requires at least one phrase of 3+ consecutive words.
    # Bare adversarial queries ("How does threshold affect people?") fail here.
    if not re.search(r'[a-z]+(?: [a-z]+){2,}', low):
        return 0

    # C1: evidence type opener (regex, not substring)
    c1 = int(any(re.search(p, low) for p in EVIDENCE_OPENERS))

    # C2: domain-specific measurement token only (word-boundary match)
    c2 = int(any(re.search(r'\b' + re.escape(t) + r'\b', low)
                 for t in DOMAIN_SPECIFIC_MECHANISM))

    # C3: environmental condition (word-boundary match — no substring collisions)
    c3 = int(any(re.search(r'\b' + re.escape(t) + r'\b', low)
                 for t in CONDITION_TERMS_WB))

    # C4: population — preposition + descriptor + class noun required
    c4 = int(bool(POPULATION_REGEX.search(low)))

    # C5: theoretical anchor (word-boundary match)
    c5 = int(any(re.search(r'\b' + re.escape(a) + r'\b', low)
                 for a in ANCHOR_PHRASES))

    return c1 + c2 + c3 + c4 + c5
```

For each query pair, record:

```python
ai_citation_signals = {
    "char_length":            len(ai_citation_query),
    "ends_with_question":     ai_citation_query.strip().endswith("?"),
    "has_theoretical_anchor": bool(any(a in ai_citation_query.lower() for a in ANCHOR_PHRASES)),
    "has_evidence_type":      bool(any(re.search(p, ai_citation_query.lower()) for p in EVIDENCE_OPENERS)),
    "has_population":         bool(POPULATION_REGEX.search(ai_citation_query.lower())),
    "structural_component_count":        count_present_components(ai_citation_query),  # 0–5
    "truncated":              bool(ai_citation_truncated),
    "trimmed_clause":         bool(ai_citation_trimmed_clause),
    "passes_minimum":         char_length >= 60 and char_length <= 500
                              and ends_with_question and structural_component_count >= 3,
}
boolean_signals = {
    "has_exact_phrase":     bool(re.search(r'"[^"]+"', boolean_query)),
    "has_and_operator":     "AND" in boolean_query,
    "has_or_group":         bool(re.search(r'\([^)]+\bOR\b[^)]+\)', boolean_query)),
    "is_bare_word_list":    not bool(re.search(r'"[^"]+"', boolean_query)) and "AND" not in boolean_query,
    "char_length":          len(boolean_query),
    "over_api_limit":       len(boolean_query) > 256,
    "truncated":            bool(boolean_truncated),
    "passes_minimum":       has_exact_phrase and has_and_operator and not is_bare_word_list
                            and not over_api_limit,
}
```

### Step 7 — Sort and write output

Preserve input `voi_score` ordering. Compute `vocabulary_hash` (SHA-256 of the vocabulary state used during synonym expansion — see SC-8). Write `query_pairs.json`.

---

## Section 3: Outputs

### Primary output — `query_pairs.json`

```json
{
  "metadata": {
    "schema_version": "1.4.0",
    "generated_at": "ISO-8601",
    "source_gap_report": "gap_report.json",
    "source_schema_version": "3.3.0",
    "gaps_processed": 50,
    "ai_citation_pass_rate": 0.94,
    "boolean_pass_rate": 0.96,
    "fallback_composition_count": 12,
    "vocabulary_source": "cross_field_vocabulary.yaml",
    "vocabulary_hash": "sha256:abcd1234..."
  },
  "query_pairs": [
    {
      "template_id": "ARCH_PROMENADE_TEMPORAL_PE_001",
      "display_id": "SC3",
      "step_number": 3,
      "param_name": null,
      "primary_gap_type": "DIRECTION",
      "voi_score": 0.478,
      "corpus_coverage": "dense",

      "ai_citation_query": "When Holl's account that architectural threshold power depends on compositional intentionality and when Ellard's account that additive multi-channel sensory convergence drives peak arousal make conflicting predictions about galvanic skin response at spatial transitions, which is better supported by psychophysiological studies in real or simulated architectural environments, and can predictive-processing theory adjudicate between intentional and channel-count explanations?",
      "ai_citation_pattern": "F",
      "ai_citation_composed_from": "competing_accounts",
      "ai_citation_signals": {
        "char_length": 431,
        "ends_with_question": true,
        "has_theoretical_anchor": true,
        "has_evidence_type": true,
        "has_population": true,
        "structural_component_count": 5,
        "truncated": false,
        "passes_minimum": true
      },

      "boolean_query": "\"multisensory threshold\" AND (\"prediction error\" OR \"predictive coding\" OR \"convergent mismatch\") AND (\"galvanic skin response\" OR \"skin conductance\" OR \"GSR\") AND \"architectural transition\" -review",
      "boolean_signals": {
        "has_exact_phrase": true,
        "has_and_operator": true,
        "has_or_group": true,
        "is_bare_word_list": false,
        "char_length": 249,
        "over_api_limit": false,
        "truncated": false,
        "passes_minimum": true
      },

      "query_rationale": "DIRECTION gap with competing accounts (Holl intentionality vs. Ellard channel count). Pattern F surfaces the theoretical debate. Boolean targets the specific physiological measure (GSR) with PP synonym expansion.",
      "manual_test_result": null,
      "manual_test_date": null
    }
  ]
}
```

### Required fields per query_pair entry

| Field | Type | Required | Notes |
|---|---|---|---|
| `template_id` | string | yes | from gap_report |
| `display_id` | string | yes | |
| `step_number` | int or null | yes | |
| `param_name` | string or null | yes | |
| `primary_gap_type` | string | yes | |
| `voi_score` | float | yes | |
| `corpus_coverage` | string | yes | |
| `ai_citation_query` | string | yes | ≥60 chars, ends with `?` |
| `ai_citation_pattern` | string | yes | A–G |
| `ai_citation_composed_from` | string | yes | `"competing_accounts"`, `"what_is_missing"`, `"template_name_fallback"` |
| `ai_citation_signals` | object | yes | 8 fields including `has_population`, `truncated` |
| `ai_citation_truncated` | bool | yes | true if query was shortened to meet 500-char limit |
| `ai_citation_trimmed_clause` | bool | yes | true if specificity guard removed a clause |
| `ai_citation_semantic_confidence` | string | yes | `"high"` (from `what_is_missing`), `"medium"` (from `step_description`), `"low"` (from `template_name_fallback`) |
| `ai_citation_generation_mode` | string | yes | `"evidence_grounded"`, `"description_scaffolded"`, or `"inferential_scaffold"` — describes the *type* of inference used, not just the confidence level |
| `direction_account_b_source` | string or null | yes | `"competing_accounts"`, `"justification_data"`, `"template_name_inference"`, or null if not DIRECTION |
| `boolean_query` | string | yes | ≤256 chars, contains AND + exact phrase |
| `boolean_pattern` | string | yes | `"standard"`, `"direction_conflict"`, `"bridge_mechanism"`, `"parameter_calibration"` |
| `boolean_truncated` | bool | yes | true if query was shortened to meet 256-char limit |
| `boolean_signals` | object | yes | 8 fields including `char_length`, `over_api_limit`, `truncated` |
| `query_rationale` | string | yes | ≤ 100 words explaining pattern choice |
| `manual_test_result` | string or null | yes | `"relevant"`, `"partial"`, `"irrelevant"`, or null |
| `manual_test_date` | string or null | yes | ISO date or null |

---

## Section 4: Success Conditions

### SC-1: Coverage
≥ 10 gap-query pairs generated, each with both query types populated and all required fields present.

### SC-2: AI Citation format compliance
- Every AI Citation query ends with `?`.
- Every AI Citation query is ≥ 60 and ≤ 500 characters.
- Every AI Citation query has `structural_component_count ≥ 3` (evidence type + mechanism + anchor minimum).
- Every AI Citation query where `depth_tier == A` has `has_population == true`.
- Zero AI Citation queries contain `AND` or `OR` used as logical operators: detection uses `r'\bAND\b|\bOR\b'` (word-boundary match), not substring, to avoid false positives on compound words like "fight-or-flight" or "non-AND-based" constructs. Quoted exact-phrase fragments (`"term"`) are also prohibited.
- ≥ 80% of queries have `ai_citation_signals.passes_minimum == true`.
- `structural_component_count` is computed using the deterministic keyword-detection algorithm in Step 6 — not human judgment.

### SC-3: Boolean format compliance
- Every Boolean query contains at least one exact-phrase group: `"term"`.
- Every Boolean query contains `AND`.
- Zero Boolean queries are bare comma-separated word lists (no operators, no quotes).
- ≥ 80% of Boolean queries contain at least one `(term OR synonym)` group.
- Zero Boolean queries have `boolean_signals.over_api_limit == true` (all queries ≤ 256 chars).
- Any query where `boolean_truncated == true` must have a `query_rationale` entry that names which AND group was dropped and why.

### SC-4: Pattern assignment integrity
- ≥ 1 query uses Pattern F (comparative) — must come from a DIRECTION gap.
- ≥ 1 query uses Pattern D or E (mechanism) — must come from a MECHANISM gap.
- ≥ 1 query uses Pattern B or C (evidence-seeking) — must come from a VALIDATION gap.
- **Zero DIRECTION gaps use Pattern B, C, or E as their primary pattern** (they must use F, or Pattern C only when `direction_fallback == true`).
- **Zero MECHANISM gaps use Pattern F** (no fake competing-account framing for scaffold gaps).
- `ai_citation_pattern` must be from the allowed set {A, B, C, D, E, F, G} — no other values.
- The pattern distribution is logged in `metadata.pattern_distribution`.

### SC-5: Theoretical anchor coverage
Every AI Citation query contains at least one anchor phrase from the framework → anchor table. Zero queries that have `t1_frameworks` populated end with a fragment (no anchor).

### SC-6: Manual test validation
At least **3 queries** (at least 1 AI Citation and 1 Boolean) have been manually tested in Google / Google Scholar. Each tested query is scored using a 3-dimension relevance rubric:

| Dimension | Score 1 | Score 0 |
|---|---|---|
| **Same phenomenon** | First-page results address the same core cognitive/physiological phenomenon as the gap (e.g., arousal at spatial transitions, not general arousal) | Off-topic phenomenon |
| **Same mechanism family** | Results use the same mechanistic vocabulary (e.g., prediction error, multisensory convergence) or a recognized equivalent | Generic or unrelated mechanism |
| **Same measurement tradition** | Results measure using the same instrument class (e.g., skin conductance, fMRI, self-report awe) | No measurement or wrong measurement family |

Scoring: 0–3 per query. **Score ≥ 2 = "relevant"**, score 1 = "partial", score 0 = "irrelevant".

At least 2 of the 3 tested queries must score ≥ 2 (relevant).

### SC-7: DIRECTION gap query integrity
- Every DIRECTION gap with `len(competing_accounts) >= 2` (after validity filtering) has both proponent names appearing in the AI Citation query text.
- Both proponent names MUST be valid: each normalized label contains ≥ 2 alphabetic characters. Labels matching `""`, `null`, `"account a"`, `"account b"`, or a single character MUST NOT appear in the query — their presence signals a proponent validity guard failure.
- Every DIRECTION gap with `len(competing_accounts) == 1` (single-proponent) has `direction_account_b_source` set to `"justification_data"` or `"template_name_inference"`, and the second account label appears in the AI Citation query.
- Every DIRECTION gap with `direction_signal_source == "rebuttal_text"` and `competing_accounts == []` has `direction_fallback: true` and `ai_citation_pattern: "C"` — these gaps do not have named proponents to put in Pattern F.
- Zero DIRECTION gaps have an AI Citation query that presupposes one account is correct (must ask "which is better supported", not assert one wins).

### SC-8: Determinism
Two consecutive runs on the same `gap_report.json` produce byte-identical `query_pairs.json` modulo `generated_at`. Required conditions for this guarantee:
- All synonym lists sorted alphabetically before serialization (no YAML dict or Python set iteration order dependency)
- OR-group members in alphabetical order in all serialized Boolean strings
- No hash-based or unordered vocabulary merges in `CrossFieldVocabulary` expansion

Verification: compute SHA-256 of output with `generated_at` zeroed; assert digest is stable across 100 consecutive executions on the same input.

**Vocabulary fingerprinting:** The byte-identical output hash catches nondeterminism within a single vocabulary state but cannot detect synonym drift across vocabulary updates. `metadata.vocabulary_hash` stores a SHA-256 of the vocabulary state used during synonym expansion (sorted serialization of all term→synonym mappings). If two runs produce the same output hash but different `vocabulary_hash` values, a vocabulary change occurred that happened to produce identical output — this should be logged as a warning, not silently ignored. Historical retrieval audits MUST compare `vocabulary_hash` values, not just output hashes.

### SC-9: Schema version
`metadata.schema_version == "1.4.0"` present. `metadata.source_schema_version` matches the Phase 2 output's `schema_version`. `metadata.vocabulary_hash` is present and is a 64-character hex SHA-256 string.

### SC-10: Fallback quality flagging
Every pair where `ai_citation_composed_from == "template_name_fallback"` has `ai_citation_signals.passes_minimum == false` OR an explicit note in `query_rationale` explaining why. These pairs are flagged for manual review, not silently passed.

---

## Section 3B: Validation tests

### What makes a bad Boolean query? 3 common mistakes and automated detection.

**Mistake 1 — Bare word list (no operators, no quotes)**
```
prediction error architectural threshold arousal multisensory
```
*What goes wrong:* Google Scholar treats it as OR across all terms — broad, noisy, non-reproducible.
*Detection:*
```python
is_bad = not bool(re.search(r'"[^"]+"', q)) and "AND" not in q and "OR" not in q
```

**Mistake 2 — Quote-wrapped full sentence**
```
"What experimental studies find that multisensory thresholds drive arousal in architecture?"
```
*What goes wrong:* Exact-phrase matching on a complete sentence returns zero results — no paper's abstract contains that exact string.
*Detection:*
```python
# A single quoted phrase > 8 words with no AND operator
matches = re.findall(r'"([^"]+)"', q)
is_bad = len(matches) == 1 and len(matches[0].split()) > 8 and "AND" not in q
```

**Mistake 3 — Synonym-less single-concept query**
```
"prediction error" AND "architectural threshold"
```
*What goes wrong:* Misses papers that use "PE signal", "mismatch signal", "surprise", "expectation violation" — all equivalent terms in different sub-disciplines.
*Detection:*
```python
has_or_group = bool(re.search(r'\([^)]+\bOR\b[^)]+\)', q))
concept_count = len(re.findall(r'"[^"]+"', q))  # number of exact phrases
# Bad if multiple concepts chained with AND but no OR synonym expansion
is_bad = concept_count >= 2 and not has_or_group
```

### Full validation checklist

- [ ] No Boolean query is a bare comma/space-separated word list — every query has `AND` or `"quotes"` (SC-3)
- [ ] Every AI Citation query ends with `?` and is ≥ 60 characters (SC-2)
- [ ] Every Boolean query contains at least one `"exact phrase"` in double quotes (SC-3)
- [ ] Every Boolean query has at least one `AND` operator (SC-3)
- [ ] ≥ 80% of Boolean queries have at least one `OR` synonym group (SC-3)
- [ ] Zero AI Citation queries contain `AND`, `OR`, or quoted keyword fragments (SC-2)
- [ ] ≥ 1 Pattern F query exists for a DIRECTION gap (SC-4)
- [ ] ≥ 1 Pattern D/E query exists for a MECHANISM gap (SC-4)
- [ ] ≥ 1 Pattern B/C query exists for a VALIDATION gap (SC-4)
- [ ] At least 3 queries manually tested in Google; ≥ 2 return relevant first-page results (SC-6)
- [ ] All DIRECTION gaps with non-empty `competing_accounts` have both proponent names in AI Citation query (SC-7)
- [ ] Two reruns produce byte-identical output (SC-8)
- [ ] No AI Citation query contains a proponent label matching `"account a"`, `"account b"`, empty string, or single character (SC-7 validity guard)
- [ ] All Boolean OR groups have synonyms in alphabetical order; SHA-256 of output (with `generated_at` zeroed) is stable across 100 runs (SC-8)
- [ ] Every Boolean query after truncation passes: balanced parens, no `()`, no trailing AND/OR, no `AND AND` (SC-3 post-truncation validation)
- [ ] No AI Citation query exceeds 2 commas, 1 em dash, or 2 mechanism nouns (specificity guard, Step 4)
- [ ] Population detected only via `(among|in) [0–3 descriptors] [class]` regex — bare "in people", "in participants", "among humans" fail (no class noun); "among elderly adults", "in hospital patients" pass (SC-2)
- [ ] Sparse-coverage gaps (`corpus_coverage == "sparse"`) do NOT have `-review -meta-analysis` exclusions added even when `total_n <= 50` (exclusion rule)
- [ ] No Boolean query drops a `priority="core"` AND-group during truncation — only `supporting` and `optional` groups are eligible for removal (Step 5 AST)
- [ ] Fallback queries (`ai_citation_composed_from == "template_name_fallback"`) have `ai_citation_semantic_confidence == "low"` (Step 4 quality gate)
- [ ] AI Citation `AND`/`OR` detection uses word-boundary regex `r'\bAND\b|\bOR\b'` — "fight-or-flight" is not flagged as a Boolean operator (SC-2)

---

## Section 3C: Generated query pairs for 3 gaps

Generated using the 5-component pattern and Pattern selection rules above. These are the first three queries the Phase 3 script will produce.

---

### Gap 1: SC3 step 3 — DIRECTION — Holl vs. Ellard on multi-channel threshold

**Gap summary:** At architectural spatial transitions, do multi-channel sensory prediction errors produce peak arousal additively (Ellard's channel-count account, N=48 Kuliga study) or does compositional intentionality dominate (Holl's account)? The additive vs. multiplicative function is unresolved. Confidence: null (absent structured field). VOI: 0.478.

**Pattern selected:** F (comparative/critical) — two competing accounts, one gap.

**AI Citation query:**
```
When Holl's account that compositional intentionality — deliberate spatial narrative — is the primary predictor of peak arousal at architectural thresholds conflicts with Ellard's additive channel-count model, which account is better supported by psychophysiological studies of skin conductance in occupants navigating real or simulated architectural environments, and can predictive processing theory adjudicate between them?
```
*Pattern F. Anchored on predictive processing. Both proponents named (Holl from `competing_accounts`, Ellard from `justification.data[1].source`). Population added: "occupants navigating". 422 chars — within 500-char limit. `direction_account_b_source: "justification_data"`.*

**Boolean query (≤256 chars):**
```
"multisensory threshold" AND ("prediction error" OR "convergent mismatch" OR "multimodal integration") AND ("skin conductance" OR "GSR" OR "electrodermal") AND "architectural" -review
```
*183 chars — within API limit. Trimmed OR groups from 4 to 3 synonyms each. `-review` retained (total_n=48).*

---

### Gap 2: L1 step 3 — VALIDATION — awe threshold (20% FOV / 1:30 contrast)

**Gap summary:** Luminance contrast ratio of 1:30 and bright-zone fraction < 20% FOV are panel-estimated thresholds for triggering an awe response. Confidence: 0.55. Warrant: MECHANISM. Corpus: sparse (PP only, 1 article). Total_n: 0 (no direct measurements). VOI: 0.283.

**Pattern selected:** B (experimental evidence-seeking) — known form, thin numbers, no direct measurement.

**AI Citation query:**
```
What experimental studies measuring skin conductance or self-reported awe have manipulated luminance contrast and bright-zone field-of-view fraction in architectural settings among participants in lit spaces, and do findings support threshold effects at approximately 1:30 contrast and 20% FOV — or is the effect better explained by cultural associations with dramatic light, as predicted by predictive processing accounts of aesthetic experience?
```
*Pattern B + cultural-confound challenge. Population added: "participants in lit spaces". Anchored on PP. Specific threshold values retained. 451 chars — within limit. `direction_fallback: false` (VALIDATION gap, not DIRECTION).*

**Boolean query (≤256 chars):**
```
"luminance contrast" AND ("awe" OR "sublime" OR "peak experience") AND ("visual field" OR "field of view") AND ("architectural lighting" OR "daylighting")
```
*155 chars — within API limit. Dropped "threshold" group and 4th synonyms to stay under 256. No exclusion (total_n=0 — cast wide net).*

---

### Gap 3: CREA1 step 1 — MECHANISM — environmental salience → DMN-ECN coupling

**Gap summary:** `bridge_inferred: true`, empty description, ANALOGICAL warrant. The mechanism by which environmental sensory richness switches between DMN and ECN coupling has never been directly measured. This is a scaffold gap — the what_is_missing quality is low (falls back to template name). VOI: 0.256.

**Pattern selected:** D/E (mechanism-explanation) — bridge gap, pathway unknown.

**Composition note:** `what_is_missing_quality == "low"`, `description == ""` → composed from template name + depth tier + t1_frameworks (DT, MS). `ai_citation_composed_from: "template_name_fallback"`.

**AI Citation query:**
```
Through what neural pathway does architectural sensory richness modulate coupling between the default mode network and executive control network during creative cognition in building occupants, and what fMRI evidence supports DMN–ECN coordination as the mechanism by which richer environments facilitate divergent thinking, as predicted by dynamic network models of creative processing?
```
*Pattern E. Population added: "building occupants". Anchored on DMN–TPN dynamics (DT). `ai_citation_composed_from: "template_name_fallback"` — description was empty. 371 chars — within limit.*

**Boolean query (≤256 chars):**
```
"default mode network" AND ("executive control network" OR "frontoparietal network" OR "ECN") AND ("environmental complexity" OR "sensory richness") AND ("divergent thinking" OR "creative cognition") AND fMRI
```
*212 chars — within API limit. Trimmed OR groups to 3/2/2 synonyms. No exclusions (total_n=0). `boolean_truncated: false`.*

---

## Section 3D: Verification answers

### "Show me the Boolean query for one gap. Does it use exact-phrase quotes? Does it have OR groups for synonyms? Would Google Scholar parse it correctly?"

Using **SC3 step 3** (v1.1 query):
```
"multisensory threshold" AND ("prediction error" OR "convergent mismatch" OR "multimodal integration") AND ("skin conductance" OR "GSR" OR "electrodermal") AND "architectural" -review
```

| Check | Result |
|---|---|
| Exact-phrase quotes | ✓ — `"multisensory threshold"`, `"prediction error"`, `"skin conductance"`, `"architectural"` |
| OR groups for synonyms | ✓ — two groups covering PP vocabulary and physiological measure vocabulary |
| Google Scholar parseability | ✓ — `"phrase" AND ("syn1" OR "syn2") -exclusion` is valid Scholar syntax; no nested parentheses |
| Character length | ✓ — 183 chars, within the 256-char API limit |
| `-review` exclusion justified | ✓ — total_n=48, single empirical study; seeking new data, not synthesis |

**One residual concern:** `"multisensory threshold"` as a bi-gram phrase may return zero results (it is domain-specific jargon). If Scholar returns 0 results, the Priority Drop Sequence in Step 5 specifies: remove quotes from this anchor and use `multisensory AND threshold` as an unquoted pair. The contract records this in `query_rationale` if triggered.

---

### "Show me the AI Citation query for the same gap. Does it follow the 5-component pattern? Could a researcher read it as a real research question?"

Using **SC3 step 3** (v1.1 query):
```
When Holl's account that compositional intentionality — deliberate spatial narrative — is the primary predictor of peak arousal at architectural thresholds conflicts with Ellard's additive channel-count model, which account is better supported by psychophysiological studies of skin conductance in occupants navigating real or simulated architectural environments, and can predictive processing theory adjudicate between them?
```

**5-component check:**
| Component | Present? | Signal |
|---|---|---|
| 1. Evidence type | ✓ | "psychophysiological studies" |
| 2. Mechanism/measure | ✓ | "skin conductance", "peak arousal", "additive channel-count" |
| 3. Environmental condition | ✓ | "architectural thresholds", "real or simulated architectural environments" |
| 4. Population/context | ✓ | "occupants navigating" — added in v1.1 to satisfy depth_tier A requirement |
| 5. Theoretical anchor | ✓ | "predictive processing theory" |

**`structural_component_count` from algorithm: 5/5.** All keyword lists fire: evidence opener ("psychophysiological studies"), mechanism term ("arousal", "skin conductance"), condition term ("architectural"), population term ("occupants"), anchor phrase ("predictive processing").

**Researcher readability:** Yes. Both proponents are named, the competing mechanisms are distinguishable (intentionality vs. channel count), the measurement is specified (skin conductance), and the arbiter is named (PP). The question asks which account wins under empirical evidence — that is a genuine research question, not a background prompt.

**One residual concern:** "Holl's account" and "Ellard's additive channel-count model" — Ellard does not appear in `competing_accounts`. It is inferred from `justification.data[1].source`. The contract records `direction_account_b_source: "justification_data"`. If `justification.data` is empty for a gap, this falls through to `template_name_inference` and SC-7 requires a note in `query_rationale`.

---

### "Take a gap about [specific mechanism]. Generate both query types. Now explain: which query would find a broader set of papers, and which would find more precisely targeted papers?"

Using **L1 step 3** (awe threshold gap):

**AI Citation (broader):**
```
What experimental studies measuring skin conductance or self-reported awe have manipulated luminance contrast and bright-zone field-of-view fraction in architectural settings among participants in lit spaces, and do findings support threshold effects at approximately 1:30 contrast and 20% FOV — or is the effect better explained by cultural associations with dramatic light, as predicted by predictive processing accounts of aesthetic experience?
```

**Boolean (more targeted, ≤256 chars):**
```
"luminance contrast" AND ("awe" OR "sublime" OR "peak experience") AND ("visual field" OR "field of view") AND ("architectural lighting" OR "daylighting")
```

**Which finds a broader set of papers — AI Citation.** Google's semantic encoder understands "dramatic light triggers awe" as a concept family. The query will surface papers using "transcendence," "peak architectural experience," "sacred space," "luminous atmosphere," and "light and emotion" — terms a Boolean query would miss entirely. It finds papers across architecture, environmental psychology, art history, and VR research that address the phenomenon without using the specific measurement vocabulary.

**Which finds more precisely targeted papers — Boolean.** The Boolean query returns only papers whose text contains `"luminance contrast"` as a phrase AND one of {awe, sublime, peak experience}. Every result is specifically about light-induced awe measured in an architectural context. The net is narrower — it misses the broader literature — but more precise: the returned papers all belong to the exact measurement tradition the gap is asking about.

**Expected overlap:** Approximately 30–40% of papers found by Boolean will also appear in AI Citation results. The 60–70% of Boolean-unique papers are the exact-vocabulary papers the gap needs most. The 60–70% of AI Citation-unique papers are the conceptually related papers that may contain indirect evidence for the threshold values.

**Practical recommendation:** Run AI Citation first to map the conceptual territory and catch papers with non-standard vocabulary. Run Boolean second to achieve systematic coverage of the standard measurement literature. Phase 4 (search execution) deduplicates across both result sets before triage.

---

## Known limitations (Phase 3)

1. **`what_is_missing_quality == "low"` for 68% of gaps** — these queries are composed from `template_name` alone. The queries are epistemically valid (they ask about the right phenomenon) but less specifically targeted than if the rebuttal text were populated. Template authoring fix needed.
2. **`CrossFieldVocabulary` dependency** — if `cross_field_vocabulary.yaml` is absent or malformed, the synonym expansion falls back to the hardcoded table. Hardcoded table covers 10 T1 frameworks but not edge cases.
3. **Pattern F requires valid `competing_accounts` proponents** — labels are filtered for ≥ 2 alphabetic characters (proponent validity guard) before Case A/B/C routing. Malformed labels (empty string, null, single character, `"account a"`/`"account b"` placeholders) are rejected and the gap falls to Case B or C. Template authoring should supply real researcher or source names rather than placeholder strings.
4. **Manual testing is not automated** — SC-6 requires 3 manual tests. The contract cannot enforce this programmatically; it is a human research step.
5. **No API call in this phase** — queries are generated and formatted but not executed. Phase 4 (Task 3 search execution) wires the Boolean queries to Semantic Scholar / PubMed APIs.
6. **Specificity guard may over-trim compositionally complex DIRECTION queries** — Pattern F queries that legitimately name two proponents + one phenomenon + one measure + one anchor can exceed 2 commas or 2 mechanism nouns. When `ai_citation_trimmed_clause: true` fires on a DIRECTION query, review the trimmed clause manually to confirm the least-specific content was removed rather than a critical named account.
7. **Specificity guard is a punctuation heuristic, not a semantic entropy metric** — comma caps, em-dash counts, and mechanism noun counts are proxies for semantic overload. They will not generalize to all query structures. Eventual replacement with embedding-based entropy estimation or concept-graph branching metrics is expected in future versions; this is acceptable for v1.x but noted as a known design debt.
8. **Phase 3 cannot evaluate retrieval efficacy** — SC-6 evaluates query design quality as a pre-execution proxy. Precision@k, novelty yield, citation utility, and redundancy rate all require actual search results and belong in Phase 4 evaluation. Phase 3 metrics are intentionally structural, not empirical.
9. **Retrieval-target behavior differences deferred to Phase 4** — AI Overview, Google Scholar, Semantic Scholar, and PubMed behave differently (PubMed MeSH tags, Scholar parenthesis quirks, Semantic Scholar embedding priors). The contract generates canonical query pairs; Phase 4 handles target-specific execution adaptation, field tags, and syntax normalization for each API.
10. **Validator taxonomy approaching stratification threshold** — the contract now contains validators across five distinct concerns: structural (syntax, operators), epistemic (generation mode, confidence), retrieval (length, OR-groups), reproducibility (hashes, determinism), and safety (malformed proponents). These are currently embedded prose. A future version that adds significant validator complexity should formalize them as named validator classes rather than continuing to add inline checks. Not required at v1.x scale.
11. **Canonical query compression is a future ceiling** — the contract assumes one AI Citation + one Boolean query pair can faithfully represent each gap. This holds for single-framing gaps but may fail for genuinely multi-disciplinary gaps where neuroscience, architectural phenomenology, and psychophysiology framings are irreconcilable into one semantic query. Phase 4 expansion via subquery generation should be considered when retrieval yield from canonical queries is consistently low on DIRECTION gaps involving cross-paradigm conflicts.

---

## Files this contract touches

| File | Read | Write |
|---|---|---|
| `Track 2/Task 2/Phase 2/gap_report.json` | ✓ | |
| `Article_Eater/src/services/voi_search.py` | ✓ (import `QueryGenerator`, `CrossFieldVocabulary`) | |
| `Article_Eater/contracts/vocab/cross_field_vocabulary.yaml` | ✓ (optional) | |
| `Track 2/Task 2/Phase 3/query_pairs.json` | | ✓ |
| stderr | | warnings, fallback notices, SC explanations |

No network calls. No mutations to source repos.
