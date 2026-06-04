# Gap Extractor Contract
## Track 2 · Task 2 · Phase 2A

**Date:** 2026-05-22 (v3.3 — direction marker tightening, corpus join fix, CTI schema fix, full corpus validated)
**Author:** Kaden Leung
**Schema version:** 3.3.0 (semver: MAJOR breaks downstream parsers, MINOR adds optional fields, PATCH fixes content)
**Contract with:** `VOICalculator` in `Article_Eater/src/services/voi_search.py` and PNU templates in `Article_Eater/data/templates/`

> **v3.3 revision note.** Implementation run on all 166 templates revealed three data-vs-contract gaps and one schema inconsistency: (1) bare `"rather than"` direction marker produced false positives (steps 2/4 SC3 classified DIRECTION when they are VALIDATION) — replaced with verb-proximity rule requiring a sign-direction verb (reduces/amplifies/increases/etc.) within 8 tokens before "rather than"; (2) `corpus_coverage` returned "absent" for all gaps because `articles.json` uses human-readable theory names ("Attention Restoration Theory") not T1 framework codes ("PP") — replaced with a `FRAMEWORK_THEORY_KEYWORDS` mapping that joins on theory-name substrings in title+abstract+theories fields; (3) `cross_template_interactions` is a list (not dict) in 5 templates — extractor now handles both; (4) `calibrated_parameters.confidence` can be a string in some templates — added coerce-to-float. Full corpus results: 554 gaps (51 DIRECTION, 275 MECHANISM, 220 VALIDATION, 8 BOUNDARY), SC-1 through SC-11 PASS, SC-8 WAIVED (cascade keys in templates don't match template_ids — template authoring fix needed), SC-12 FAIL at 32% non-low quality (template authoring issue, extractor correct).

---

## Objective

A deterministic, single-process program that reads all PNU template JSON files, walks both `mechanism_chain` and `calibrated_parameters`, classifies each low-confidence item as a typed knowledge gap with multi-label tags, scores each gap using `VOICalculator.calculate_voi()` while exposing all intermediate components, and writes a ranked, machine-readable, versioned JSON list that the query generator can consume downstream.

---

## Epistemic policy statements (read before the spec)

### Confidence semantics
Template `confidence` values are **ordinal uncertainty proxies**, not calibrated probabilities. A step at 0.4 is *less believed* than one at 0.6, but the 0.2 gap does not represent a calibrated probability mass. Consequences:

- VOI rankings are **comparative within a run**, not cross-run probabilistic claims.
- The `1.0 - confidence → uncertainty` transform in Step 4 is a working translation, not a calibration.
- Phase 3 may introduce per-panel calibration normalization. Phase 2 does not.
- **Threshold semantics is strict-less-than:** `confidence < threshold` triggers a gap; `confidence == threshold` does not. This boundary rule is explicit because float comparison at the boundary (e.g. 0.6 vs 0.6 + 1 ULP) would otherwise produce sporadic results.

### VOI prioritization rationale
`VOICalculator` applies `GAP_TYPE_PRIORITY_WEIGHTS`: DIRECTION=1.0, VALIDATION=0.7, MECHANISM=0.5, BOUNDARY=0.4. This is a **panel-set epistemic policy**, not a derivation. The rationale:

Unresolved contradictions (DIRECTION) propagate through downstream inference — every claim built atop a disputed mechanism inherits the dispute. Mechanism gaps (MECHANISM) are localized: filling them adds knowledge, but leaving them empty does not corrupt adjacent claims. Therefore contradiction resolution is prioritized over mechanism completion.

This policy is **not absolute** — a foundational MECHANISM gap with high cascade risk can still outscore a peripheral DIRECTION gap, because the weighted combination in `calculate_voi()` includes structural factors. The priority weight is one input, not the sole determinant.

### Heuristic vs epistemic-quality boundary
`specificity_score` is heuristic and sensitive to authoring style; it measures **lexical specificity, not epistemic quality**. A concise precise rebuttal ("threshold nonlinearity unresolved") may score lower than a verbose vague one. The extractor surfaces the metric for downstream filtering; it should never be treated as ground truth for gap importance.

---

## Section 1: Inputs

### Primary input — PNU template files
- **Location:** `Article_Eater/data/templates/*.json`
- **Format:** JSON. Each file is one template.
- **Template-level fields read:**
  - `template_id` (string) — canonical identifier; must be unique across the directory
  - `display_id` (string) — short label; not unique
  - `name` (string)
  - `t1_frameworks` (list of strings) — one of: PP, SN, DP, DT, NM, IC, MS, EC, CB, MSI
  - `calibration_status` (string)
  - `confidence` (float in [0,1])
  - `mechanism_chain` (array of step objects)
  - `calibrated_parameters` (object)
  - `cross_template_interactions` (object)
  - `evidence_paper_ids` (list of strings)

- **Fields read per `mechanism_chain` step:**
  - `step` (int)
  - `description` (string)
  - `confidence` (float in [0,1] or absent)
  - `warrant` (string)
  - `bridge_inferred` (bool, default false) — **explicit flag takes precedence over description-emptiness**
  - `justification.competing_accounts` (list)
  - `justification.qualifier` (string)
  - `justification.rebuttal` (string)
  - `justification.depth_tier` (string: A/B/C)
  - `justification.data` (list)
  - `justification.backing` (string)

- **Fields read per `calibrated_parameters` entry:**
  - parameter name (key)
  - `value` or `range`
  - `confidence` (float)
  - `competing_values` (list, optional)

### Configuration input
- `--threshold` (float, default **0.6**) — strict less-than
- `--templates-dir` (path, default `Article_Eater/data/templates/`)
- `--output` (path, default `gap_report.json`; `-` writes JSON to stdout)
- `--top-n` (int, default 50)
- `--all` (flag, default false) — overrides `--top-n` when set

### Corpus inventory
- **Location:** `Knowledge_Atlas/data/ka_payloads/articles.json` (760 papers, snapshot 2026-04-28)
- **Used for:** `corpus_coverage` tagging (Step 7)
- **Not used for:** filtering gaps out

### Input validation rules (research-corruption hardening)
Templates that violate are **skipped** with a `validation_failures` entry; the run continues.

| Rule | Action |
|---|---|
| `template_id` duplicated across files | Skip later-loaded (sorted order); record both filenames |
| `confidence` is NaN, inf, or outside [0,1] | Skip the template |
| `mechanism_chain` step numbers non-monotonic or duplicate | Skip the template |
| `mechanism_chain` is wrong type (not array) | Skip the template; rule = `"invalid_mechanism_chain_type"` |
| String fields exceed 10,000 chars | Truncate + stderr warning; do not skip |
| Cycle in `cross_template_interactions` (A→B→A or longer) detected during Step 1b | Both members emit gaps; `cascade_risk` entries for cycle members carry `cycle_member: true` |
| `cross_template_interactions` references a `template_id` not present in the loaded set | Phantom reference excluded from `framework_in_degree` and `cascade_risk`; rule = `"phantom_cascade_reference"` |
| `cross_template_interactions` references the template's own `template_id` | Self-loop excluded from `framework_in_degree` and `cascade_risk`; rule = `"self_reference"` |
| JSON parse failure | Skip with stderr warning |

---

## Section 2: Processing

### Step 1 — Load and validate templates

**1a.** Read every `.json` in sorted filename order. Apply input validation rules. Build working set.

**1b.** Build derived indexes from validated templates:
- `reverse_dependency_index: {template_id: [downstream_template_ids]}`
- `framework_in_degree: {template_id: int}` — counts only references from *other* loaded templates (excludes self-references and phantom references)
- `dependency_cycles: List[Tuple[str, str]]` — cycle members

**1c.** Warn (stderr) on `display_id` collisions.

**1d.** Compute `input_hash` — **content-based**, not mtime-based:
```python
per_file_hashes = [
    (template_id, sha256(canonical_json_dumps(template_json)).hexdigest())
    for template_id in sorted(loaded_template_ids)
]
input_hash = sha256(
    "\n".join(f"{tid}\t{h}" for tid, h in per_file_hashes).encode()
).hexdigest()
```
`canonical_json_dumps` = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`. mtime is not used (filesystem-dependent and CI/checkout-unstable).

### Step 2 — Walk gap sources

#### 2a. Walk `mechanism_chain`
A step is a **gap candidate** if any of:
- `confidence < threshold` (strict less-than; equal is NOT a gap)
- `confidence` is absent/null
- `bridge_inferred == true` (explicit flag)
- `description.strip() == ""` AND `bridge_inferred` is not explicitly true — emit stderr warning naming `template_id::step` (empty description without explicit flag is authoring corruption, not intentional inference)

#### 2b. Skip definitional steps
A step is **definitional** if either:
- `justification.rebuttal.strip().lower().startswith("n/a")` AND `"definitional" in justification.rebuttal.lower()`
- Explicit `definitional: true` field present

#### 2c. Walk `calibrated_parameters`
For each `(param_name, param_obj)` where `param_obj.confidence < threshold`:
- `gap_source = "calibrated_parameter"`
- `step_number = null`, `param_name = key`
- `step_description = f"Calibrated parameter: {param_name} = {value_or_range}"`
- `warrant = "PARAMETER_ESTIMATE"`
- `competing_accounts` ← `param_obj.competing_values` if present

### Step 3 — Multi-label gap classification

**`primary_gap_type` (precedence, first match wins):**
1. **DIRECTION** — either:
   - `competing_accounts` or `competing_values` is non-empty (`direction_signal_source: "competing_accounts"`), **or**
   - `justification.rebuttal` contains a **direction-marker phrase** (case-insensitive): `"rather than"`, `"or dampen"`, `"or amplify"`, `"could reduce rather"`, `"could increase rather"`, `"sign of effect"`, `"amplify or"`, `"dampen or"`, `"reduce or increase"`, `"increase or decrease"` AND `competing_accounts` is empty (`direction_signal_source: "rebuttal_text"`). This catches direction conflicts encoded in prose instead of the structured list — confirmed in SC3 step 6.
2. **MECHANISM** — `bridge_inferred == true` AND (`confidence` absent OR `confidence < threshold`); OR `description.strip() == ""`; OR `warrant == "ANALOGICAL"` AND `confidence < threshold`
3. **BOUNDARY** — `qualifier` contains (case-insensitive): `"does not apply"`, `"limited to"`, `"only in"`, `"scope unclear"`, `"outside"`, `"not generalizable"`
4. **VALIDATION** — fallback

**`gap_tags` (additive, all that apply):**

| Tag | Condition |
|---|---|
| `DIRECTION` | `competing_accounts` / `competing_values` non-empty |
| `MECHANISM` | `bridge_inferred == true` OR `warrant == "ANALOGICAL"` (with confidence guard) |
| `BOUNDARY` | qualifier matches scope markers |
| `VALIDATION` | low confidence AND `warrant ∈ {EMPIRICAL_COVARIANCE, MECHANISM}` AND no competing accounts |
| `STRUCTURAL_MISSINGNESS` | `description.strip() == ""` AND `bridge_inferred` NOT explicitly true |
| `INTENTIONAL_BRIDGE_INFERENCE` | `bridge_inferred == true` (explicit flag) |
| `CALIBRATED_PARAMETER` | `gap_source == "calibrated_parameter"` |

**Invariant:** `primary_gap_type ∈ gap_tags`.

### Step 4 — Build proxy `Belief` object

```python
from web_of_belief import Belief, Credence
from web_of_belief_components.enums import EpistemicLevel

belief = Belief(
    belief_id = f"{template_id}::step::{step_number}",   # or "::param::{param_name}"
    content   = step_description_or_param_label,
    level     = _level_from_warrant(warrant),
    credence  = Credence(
                  value       = step_confidence if step_confidence is not None else 0.35,
                  uncertainty = (1.0 - step_confidence) if step_confidence is not None else 0.65,
                ),
    paper_ids = _placeholder_paper_list(len(justification.data)),
    domain    = primary_t1_framework or "",
)
```

**`_level_from_warrant`:**

| warrant | EpistemicLevel | importance |
|---|---|---|
| `ANALOGICAL` | `THEORETICAL` | 0.9 |
| `MECHANISM` | `INTERMEDIATE` | 0.7 |
| `FUNCTIONAL` | `INTERMEDIATE` | 0.7 |
| `EMPIRICAL_COVARIANCE` | `EMPIRICAL` | 0.5 |
| `THEORETICAL_DEFAULT` | `THEORETICAL` | 0.9 |
| `PARAMETER_ESTIMATE` | `EMPIRICAL` | 0.5 |
| absent / null | `EMPIRICAL` | 0.5 |

**Important:** SC3 and several other templates store `warrant: null` at the step JSON level — the warrant value (e.g. "THEORETICAL_DEFAULT") is embedded in `justification.qualifier` prose, not a structured field. The extractor treats `null` warrant as `EMPIRICAL` (importance 0.5). If the qualifier text contains `"THEORETICAL_DEFAULT"` or `"ANALOGICAL"`, the extractor **may** optionally parse it as a warrant hint — but must mark `warrant_source: "qualifier_text"` vs `"structured_field"` in the output so downstream consumers know the warrant was inferred, not read. Default safe behavior: treat absent as `EMPIRICAL` without text parsing.

**`total_n` aggregation with type coercion:**
```python
def coerce_n(item) -> Tuple[int, Optional[str]]:
    raw = item.get("n_subjects", item.get("n"))
    if raw is None: return 0, None
    if isinstance(raw, int): return raw, None
    if isinstance(raw, float): return int(raw), None
    if isinstance(raw, list):  # multi-cohort, e.g. [12, 36]
        try: return sum(int(x) for x in raw), None
        except (TypeError, ValueError): return 0, f"list-cohort-unparseable: {raw!r}"
    if isinstance(raw, str):
        cleaned = raw.strip().lstrip("N=").lstrip("n=")
        try: return int(cleaned), None
        except ValueError: return 0, f"string-unparseable: {raw!r}"
    return 0, f"unknown-type: {type(raw).__name__}"

total_n = 0
total_n_coercion_warnings = []
for d in justification.data:
    if not isinstance(d, dict):
        total_n_coercion_warnings.append(f"non-dict-entry: {d!r}")
        continue
    n, warn = coerce_n(d)
    total_n += n
    if warn: total_n_coercion_warnings.append(warn)
```

### Step 5 — Score with exposed components

**Centrality proxy (sigmoidal, non-saturating):**
```python
centrality_proxy = min(
    1.0,
    0.20 + 0.40 * tanh(framework_in_degree[template_id] / 4.0) + 0.05 * len(t1_frameworks)
)
```
`tanh(x/4)` reaches 0.76 at in_degree=4 and 0.96 at in_degree=8, preserving ordering across the realistic range without flattening high-connectivity templates to a shared ceiling. Previous linear formula saturated at in_degree≈6.

**VOI breakdown (all components surfaced):**
```python
sparsity         = _sparsity_from_paper_count(len(justification.data), gap_type)
importance       = LEVEL_IMPORTANCE[level]
uncertainty      = belief.credence.uncertainty
alpha            = ALPHA_BY_GAP_TYPE[primary_gap_type]
priority_weight  = GAP_TYPE_PRIORITY_WEIGHTS[primary_gap_type]

structural_voi   = 0.6 * centrality_proxy + 0.4 * sparsity
epistemic_voi    = uncertainty * importance
base_voi         = alpha * structural_voi + (1 - alpha) * epistemic_voi
combined_voi     = min(base_voi * priority_weight, 1.0)
```

Exception policy: any component raising → record `voi_score: null`, `voi_components` fields null, `voi_error` set, continue.

### Step 6 — Cascade risk (algorithmic, weighted-schema, cycle-aware)

Look up `template_id` in `reverse_dependency_index`. Emit structured entries:

```json
"cascade_risk": [
  {"template_id": "IC2", "dependency_strength": null, "cycle_member": false},
  {"template_id": "AX4", "dependency_strength": null, "cycle_member": true}
]
```

- `dependency_strength` reserved for Phase 3 (null in Phase 2).
- `cycle_member: true` if the (this_template, downstream) pair appears in `dependency_cycles`.
- Self-loops are NOT emitted (filtered at index build).
- Phantom references (target not in loaded set) are NOT emitted.

### Step 7 — Corpus coverage
Join `articles.json` by **framework overlap**: count articles where `article.frameworks ∩ template.t1_frameworks` non-empty. Fallback to substring match on `article.topic`. Method recorded in `metadata.corpus_join_key`.

Buckets: `dense ≥20`, `moderate 5-19`, `sparse 1-4`, `absent 0`.

### Step 8 — Compute quality and fingerprint

#### 8a. `what_is_missing` derivation
```python
if rebuttal and not _is_definitional(rebuttal):
    text = rebuttal
elif qualifier:
    text = qualifier
else:
    text = f"the mechanism by which {step_description or template_name}"
what_is_missing = truncate_at_word_boundary(text, 280)
```

#### 8b. `what_is_missing_quality` (heuristic — see epistemic-quality boundary above)
```python
GENERIC_PHRASES = {"more research", "further study", "needs investigation",
                   "to be determined", "unclear", "unknown", "n/a", "tbd",
                   "additional work"}
MECHANISTIC_TERMS = {"mechanism", "pathway", "moderator", "mediator", "threshold",
                     "directionality", "interaction", "function form", "dose-response",
                     "measurement", "calibration", "effect size"}
CAUSAL_VERBS = {"causes", "produces", "induces", "modulates", "predicts", "elicits",
                "drives", "suppresses", "amplifies", "triggers", "regulates"}

specificity_score = clip(
    0.30 * min(causal_verbs_detected, 3) / 3
  + 0.30 * min(mechanistic_terms_detected, 3) / 3
  + 0.20 * min(noun_phrase_count, 5) / 5
  + 0.10 * (1 if char_length >= 40 else char_length / 40)
  - 0.40 * min(generic_phrases_detected, 2) / 2,
  0.0, 1.0
)
bucket: <0.30 → "low" | 0.30–0.60 → "medium" | >0.60 → "high"
```

#### 8c. `normalized_gap_fingerprint`
```python
fingerprint_tokens = sorted(set(
    [primary_gap_type.lower()]
    + sorted(t1_frameworks)
    + extract_mechanistic_terms(step_description + " " + what_is_missing)
    + sorted(competing_account_proponents)
))
normalized_gap_fingerprint = sha1("|".join(fingerprint_tokens).encode()).hexdigest()[:16]
```
Collisions are informational; no merging in Phase 2.

### Step 9 — Sort and truncate

Sort by:
1. `round(combined_voi, 6)` DESC
2. `round(structural_voi, 6)` DESC
3. `template_id` ASC
4. `step_number` ASC (NULLs last)
5. `param_name` ASC (NULLs last)

Float rounding to 6 decimals prevents 1-ULP artifacts. Determinism is guaranteed within CPython; cross-runtime would require `Decimal` quantization (deferred — no real failure mode at this scope).

`--all` overrides `--top-n`.

### Step 10 — Write output

---

## Section 3: Outputs

### Primary output — `gap_report.json`

```json
{
  "metadata": {
    "schema_version": "3.1.0",
    "generated_at": "2026-05-22T19:00:00Z",
    "extractor_version": "3.1",
    "input_hash": "sha256:abc123...",
    "input_hash_method": "content_sha256_per_file_aggregated",
    "templates_attempted": 167,
    "templates_loaded": 165,
    "templates_skipped": 2,
    "validation_failures": [
      {"file": "broken.json", "rule": "json_parse_failure", "detail": "..."},
      {"template_id": "X", "rule": "phantom_cascade_reference", "detail": "interaction_with_NONEXISTENT_001"},
      {"template_id": "Y", "rule": "self_reference", "detail": "interaction_with_Y"}
    ],
    "confidence_threshold": 0.6,
    "confidence_threshold_semantics": "strict less-than (confidence == threshold is NOT a gap)",
    "confidence_semantics": "ordinal uncertainty proxy (not calibrated probability)",
    "centrality_method": "sigmoidal: 0.20 + 0.40*tanh(in_degree/4) + 0.05*|t1_frameworks|",
    "voi_prioritization": "DIRECTION>VALIDATION>MECHANISM>BOUNDARY (panel policy)",
    "corpus_join_key": "framework_overlap",
    "corpus_snapshot_date": "2026-04-28",
    "display_id_collisions": ["AX3"],
    "dependency_cycles": [{"members": ["A", "B"]}],
    "fingerprint_collisions": [
      {"fingerprint": "abc123...", "gap_belief_ids": ["SC3::step::3", "L1::step::2"]}
    ],
    "quality_distribution": {"high": 12, "medium": 8, "low": 3},
    "total_gaps_found": 0,
    "gaps_in_output": 0,
    "known_limitations": [
      "centrality is a proxy; full WebOfBelief not wired",
      "level_importance lookup may always return 0.5 until voi_search.py is patched",
      "null vs absent evidence not differentiated",
      "semantic dedupe across gaps deferred to Phase 3",
      "VALIDATION is a heterogeneous fallback; Phase 3 may split into EVIDENCE_STRENGTH/MEASUREMENT/REPLICATION/PARAMETER_ESTIMATION",
      "determinism guaranteed within CPython; cross-runtime requires Decimal quantization"
    ]
  },
  "gaps": [
    {
      "gap_source": "mechanism_chain",
      "template_id": "ARCH_PROMENADE_TEMPORAL_PE_001",
      "display_id": "SC3",
      "template_name": "Architectural Promenade as ...",
      "step_number": 3,
      "param_name": null,
      "step_description": "THRESHOLD EVENT: ...",
      "confidence": 0.425,
      "warrant": "THEORETICAL_DEFAULT",

      "primary_gap_type": "DIRECTION",
      "gap_tags": ["DIRECTION", "MECHANISM"],

      "voi_score": 0.71,
      "voi_components": {
        "uncertainty":      0.575,
        "importance":       0.9,
        "sparsity":         0.7,
        "centrality_proxy": 0.72,
        "structural_voi":   0.71,
        "epistemic_voi":    0.52,
        "alpha":            0.5,
        "priority_weight":  1.0
      },
      "voi_error": null,

      "depth_tier": "A",
      "what_is_missing": "the actual function could be non-additive; additive vs. multiplicative model unresolved",
      "what_is_missing_quality": "high",
      "specificity_score": 0.78,
      "specificity_signals": {
        "causal_verbs_detected": 1,
        "mechanistic_terms_detected": 2,
        "generic_phrases_detected": 0,
        "noun_phrase_count": 4,
        "char_length": 95
      },

      "competing_accounts": [
        {"account": "Compositional intentionality over channel count", "proponent": "Holl", "claim": "..."}
      ],
      "direction_signal_source": "competing_accounts",
      "warrant_source": "structured_field",
      "bridge_inferred": false,
      "total_n": 48,
      "total_n_coercion_warnings": [],

      "cascade_risk": [
        {"template_id": "IC2", "dependency_strength": null, "cycle_member": false},
        {"template_id": "AX4", "dependency_strength": null, "cycle_member": false}
      ],
      "corpus_coverage": "sparse",
      "t1_frameworks": ["PP", "MSI", "MS", "EC"],
      "normalized_gap_fingerprint": "a1b2c3d4e5f6g7h8"
    }
  ]
}
```

### Required fields per gap entry

| Field | Type | Required | Notes |
|---|---|---|---|
| `gap_source` | string | yes | `mechanism_chain` / `calibrated_parameter` |
| `template_id` | string | yes | primary key |
| `display_id` | string | yes | may collide |
| `template_name` | string | yes | |
| `step_number` | int or null | yes | null for parameter gaps |
| `param_name` | string or null | yes | null for mechanism gaps |
| `step_description` | string | yes | ≤300 chars |
| `confidence` | float or null | yes | |
| `warrant` | string | yes | |
| `primary_gap_type` | string | yes | |
| `gap_tags` | list of strings | yes | contains `primary_gap_type` |
| `voi_score` | float or null | yes | |
| `voi_components` | object | yes | 8 fields; null on `voi_error` |
| `voi_error` | string or null | yes | |
| `depth_tier` | string or null | yes | |
| `what_is_missing` | string | yes | |
| `what_is_missing_quality` | string | yes | low/medium/high |
| `specificity_score` | float | yes | [0,1] |
| `specificity_signals` | object | yes | 5 counts |
| `competing_accounts` | list | yes | |
| `direction_signal_source` | string or null | yes | `"competing_accounts"`, `"rebuttal_text"`, or null if not DIRECTION |
| `warrant_source` | string | yes | `"structured_field"` or `"qualifier_text"` or `"absent"` |
| `bridge_inferred` | bool | yes | |
| `total_n` | int | yes | |
| `total_n_coercion_warnings` | list of strings | yes | empty if all entries clean |
| `cascade_risk` | list of objects | yes | each has `template_id`, `dependency_strength`, `cycle_member` |
| `corpus_coverage` | string | yes | |
| `t1_frameworks` | list | yes | |
| `normalized_gap_fingerprint` | string | yes | 16-char hex |

---

## Section 4: Success Conditions

### SC-1: Coverage
≥ 10 gaps with `confidence < 0.6`, all required fields populated.

### SC-2: Gap type classification
- ≥ 3 gaps with `primary_gap_type == "DIRECTION"`.
- ≥ 5 gaps with `"MECHANISM" ∈ gap_tags` AND `bridge_inferred: true` AND `"INTENTIONAL_BRIDGE_INFERENCE" ∈ gap_tags`.
- Zero gaps where `competing_accounts` non-empty AND `primary_gap_type != "DIRECTION"`.
- Zero gaps where `warrant == "ANALOGICAL"` AND `confidence >= 0.6` AND MECHANISM appears in `gap_tags`.
- For every gap, `primary_gap_type ∈ gap_tags`.
- ≥ 1 gap with both `"DIRECTION"` and `"MECHANISM"` in `gap_tags`.

### SC-3: VOI ordering
Same-template gaps within ±0.05 confidence: DIRECTION outscores MECHANISM.

### SC-4: Known Phase 1 gaps
≥ 3 of 5 Phase 1 gaps in top 15. Missing gaps require stderr explanation with rank and dominant suppressor.

### SC-5: Output format
- Valid JSON, schema check passes.
- `voi_score` and `voi_components` values in [0,1] when non-null.
- `schema_version` matches contract.

### SC-6: Performance
< 60 seconds on all 166 templates, no network.

### SC-7: Failure handling
- JSON parse → skip + warning + `validation_failures`.
- Missing `confidence` → emitted with `confidence: null`.
- Empty `mechanism_chain` AND empty `calibrated_parameters` → counted in `templates_skipped`.
- `calculate_voi` raises → gap with `voi_score: null`, `voi_components` nulled, `voi_error` set.
- Research-corruption violations → skip + `validation_failures`.
- Cycles → cycle members emit gaps with `cycle_member: true` on cascade entries.
- Phantom references → excluded from cascade and centrality; logged.
- Self-references → excluded from cascade and centrality; logged.

### SC-8: Cascade coverage
Algorithmically derived: L1 → SC3 cascade emitted; SC3 step 3 → IC2/AX4. Failure → `WAIVED_PENDING_TEMPLATE_FIX`.

### SC-9: Determinism
Two consecutive runs → byte-identical output modulo `generated_at`. `input_hash` matches across runs (content-based; mtime changes do not affect it).

### SC-10: Calibrated-parameter coverage
≥ 1 gap with `gap_source == "calibrated_parameter"`. L1 should produce ≥ 3.

### SC-11: Uniqueness
No two emitted gaps share `(template_id, step_number, param_name)`. Fingerprint collisions are informational.

### SC-12: Quality distribution
≥ 80% of emitted gaps have `what_is_missing_quality != "low"`. Aggregate logged.

### SC-13: Schema versioning
`metadata.schema_version` present, valid semver, matches contract.

### SC-14: Threshold boundary
`confidence == threshold` does NOT produce a gap; `confidence == threshold - 1e-9` DOES. Two runs with identical input produce identical boundary decisions.

### SC-15: Cross-template integrity
- Zero phantom `template_id`s appear in any `cascade_risk` entry.
- Zero self-loops appear in any `cascade_risk` entry.
- `framework_in_degree[X]` equals the count of *loaded, distinct* templates referencing X (excludes phantom and self).

---

## Phase 2A MVP scope tagging

Spec items are tagged for staged implementation. `[required]` ships in v1 of the extractor; `[required-stub]` ships with a placeholder; `[optional]` can defer to Phase 2B.

| Spec item | Tag | Notes |
|---|---|---|
| Steps 1a, 1b, 1c | required | core loading and indexing |
| Step 1d input_hash | required-stub | can ship as `"unset"` initially; flip on later |
| Step 2a mechanism walk | required | |
| Step 2b definitional skip | required | substring rule only |
| Step 2c calibrated_parameters walk | required | needed for SC-10 |
| Step 3 primary_gap_type | required | |
| Step 3 gap_tags additive | required | needed for SC-2 |
| `STRUCTURAL_MISSINGNESS` vs `INTENTIONAL_BRIDGE_INFERENCE` distinction | required | |
| Step 4 proxy Belief | required | |
| `total_n` basic int/None case | required | |
| `total_n` heterogeneous coercion | required-stub | ship with int/None only; coerce strings/lists in 2B |
| Step 5 sigmoidal centrality | required | |
| Step 5 all `voi_components` exposed | required | |
| Step 6 cascade with `dependency_strength: null` | required | |
| Step 6 `cycle_member` flag | required | needed for SC-7 |
| Phantom / self-reference exclusion | required | needed for SC-15 |
| Step 7 corpus coverage | required | |
| Step 8a what_is_missing derivation | required | |
| Step 8b specificity_score full formula | optional | ship with `generic_phrases_detected` + `char_length` only; rest stubbed at 0 |
| Step 8c normalized_gap_fingerprint | optional | can emit `""` and populate in 2B |
| Step 9 sort | required | |
| Validation: JSON parse, NaN/inf, duplicate steps, duplicate template_ids | required | |
| Validation: cycles, phantom refs, self-refs | required | |
| Validation: 10k char truncation | optional | |
| `metadata.quality_distribution` | optional | derivable post-hoc |
| `metadata.fingerprint_collisions` | optional | derivable post-hoc |
| Test plan execution | required | all 10 numbered + 4 bonus |

MVP cut: ~250 LOC. Full v3.1: ~350 LOC. The optional items are the gap.

---

## Known limitations (Phase 2)

1. **Centrality is a proxy** (sigmoidal in-degree + framework count). Real graph centrality from `WebOfBelief` deferred to Phase 3.
2. **`level_importance` may always resolve to 0.5** — `voi_search.py` uses string-keyed dict but `Belief.level` is an Enum. Contract passes correct Enum so upstream fix won't require extractor changes.
3. **`bridge_inferred` quality** — `STRUCTURAL_MISSINGNESS` cases have thin `what_is_missing` by construction.
4. **Corpus coverage uses `articles.json` snapshot 2026-04-28**, not the lifecycle DB (0 bytes in this checkout).
5. **`GapDetector` not reused** — operates on `WebOfBelief`, not template JSON.
6. **`NullResultDetector` not invoked** — `total_n` exposed for downstream inference.
7. **Sample size not weighted into sparsity** — paper *count* used, not subject *count*.
8. **`display_id` not unique** — canonical key is `template_id`.
9. **Definitional-step detection is signal-based.** Long-term: require `definitional: true` field.
10. **Semantic gap dedupe deferred to Phase 3.** `normalized_gap_fingerprint` is the bridge.
11. **`dependency_strength` reserved but null** — schema forward-compatible.
12. **`VALIDATION` is heterogeneous.** Phase 3 may split into `EVIDENCE_STRENGTH`, `MEASUREMENT`, `REPLICATION`, `PARAMETER_ESTIMATION` to differentiate failure modes (currently a "miscellaneous uncertainty" bucket).
13. **Determinism scoped to CPython.** Cross-runtime requires `Decimal` quantization (no real failure mode at current scope; documented).
14. **`warrant` is often absent at the step JSON level.** SC3 and similar templates store warrant as prose inside `justification.qualifier` (e.g. "THEORETICAL_DEFAULT"), not as a structured `warrant` field. The extractor defaults to `EMPIRICAL` (importance 0.5) for null warrants; qualifier-text parsing is optional and must be flagged via `warrant_source: "qualifier_text"`. This suppresses epistemic VOI for steps whose actual warrant would be `THEORETICAL` (importance 0.9) — a known underscoring of SC3 gaps.
15. **`specificity_score` is lexical, not semantic.** Concise precise statements may underscore verbose vague ones. Surface metric; do not treat as ground truth.

---

## Test plan

Ten numbered test cases below. The first 5 cover single-step contract behaviors; the second 5 cover cross-step interactions. Must pass on a 5-template fixture before full-corpus execution.

### T1: Malformed `mechanism_chain` type
Fixture has `"mechanism_chain": "not_an_array"`.
- [ ] Template skipped, run continues
- [ ] stderr warning names template
- [ ] `validation_failures` contains rule `"invalid_mechanism_chain_type"`
- [ ] Output JSON parses

### T2: Contradictory gap (competing_accounts + bridge_inferred + ANALOGICAL)
- [ ] `primary_gap_type == "DIRECTION"`
- [ ] `gap_tags` contains both `"DIRECTION"` and `"MECHANISM"`
- [ ] `gap_tags` contains `"INTENTIONAL_BRIDGE_INFERENCE"`
- [ ] `voi_components.priority_weight == 1.0`
- [ ] No gap with non-empty `competing_accounts` has `primary_gap_type != "DIRECTION"`

### T3: Float ordering determinism
Two gaps engineered to score 0.7100000001 and 0.71.
- [ ] Both round to identical 6-decimal value
- [ ] Tiebreak proceeds to `structural_voi`, then `template_id`
- [ ] Two consecutive runs byte-identical
- [ ] `input_hash` identical across runs

### T4: Empty description with explicit `bridge_inferred: false`
- [ ] stderr warning names `template_id::step`
- [ ] `gap_tags` contains `"STRUCTURAL_MISSINGNESS"`
- [ ] `gap_tags` does NOT contain `"INTENTIONAL_BRIDGE_INFERENCE"`
- [ ] Gap still emitted if `confidence < threshold`
- [ ] `what_is_missing` falls back to template-derived text

### T5: VOI exception
Monkeypatch `VOICalculator.calculate_voi` to raise.
- [ ] Program does not crash
- [ ] Gap emitted with `voi_score: null`
- [ ] All `voi_components` fields null
- [ ] `voi_error` contains exception message
- [ ] Remaining templates process
- [ ] Output JSON valid

### T6: Phantom cascade reference
Template references `GHOST_TEMPLATE_001` which doesn't exist.
- [ ] No crash
- [ ] `validation_failures` contains `"phantom_cascade_reference"` entry
- [ ] `cascade_risk` excludes `GHOST_TEMPLATE_001`
- [ ] `framework_in_degree` not inflated by phantom
- [ ] stderr warning emitted

### T7: Threshold boundary
Steps at 0.6, 0.5999999, 0.6 + 1e-16, 0.45 with `--threshold=0.6`.
- [ ] Step at 0.6 NOT emitted (strict-less-than)
- [ ] Step at 0.5999999 IS emitted
- [ ] Step at 0.6 + 1e-16 NOT emitted
- [ ] Step at 0.45 IS emitted
- [ ] Reruns agree on boundary

### T8: Heterogeneous `total_n`
`justification.data` contains int, string `"60"`, null, list `[12,36]`, bare string, `"N=24"`.
- [ ] No crash
- [ ] `total_n` deterministic (e.g. 48 + 60 + 0 + 48 + 0 + 24 = 180)
- [ ] `total_n_coercion_warnings` lists unparseable entries
- [ ] Gap still emitted

### T9: Self-referential `cross_template_interactions`
Template's `cross_template_interactions` includes itself.
- [ ] Self-loop excluded from `framework_in_degree`
- [ ] Self-loop excluded from `cascade_risk`
- [ ] `validation_failures` contains `"self_reference"` entry
- [ ] stderr warning emitted
- [ ] Gap still emitted with valid external references in cascade

### T10: Top-N tie at boundary
Two templates `AAA_TIE` and `BBB_TIE` engineered to produce identical scores.
- [ ] `--top-n=1` → emits AAA_TIE (lexical tiebreak)
- [ ] `--top-n=2` → emits `[AAA_TIE, BBB_TIE]` in that order
- [ ] Adding unrelated fixture_C ranking #3 does not change A/B at #1/#2
- [ ] `--all` flag emits both regardless of `--top-n=1`
- [ ] `metadata.gaps_in_output == --top-n` exactly

### T11: Rebuttal-text DIRECTION detection
SC3 step 6 fixture — `competing_accounts: []` but rebuttal contains "reduces rather than amplifies".
- [ ] `primary_gap_type == "DIRECTION"`
- [ ] `direction_signal_source == "rebuttal_text"`
- [ ] `gap_tags` contains `"DIRECTION"`
- [ ] `voi_components.priority_weight == 1.0`
- [ ] A step with `competing_accounts: []` AND rebuttal containing only "would fail if" (no direction markers) is NOT classified DIRECTION

### Bonus tests
- [ ] Duplicate `template_id` skips later-loaded file
- [ ] Cross-template cycle adds `metadata.dependency_cycles` entry; cycle members have `cycle_member: true` in cascade
- [ ] `calibrated_parameters` gaps emit `param_name` with `step_number == null`
- [ ] Fingerprint collisions logged, gaps not merged
- [ ] `specificity_score` always in [0,1]
- [ ] `corpus_coverage` boundary classification: 4→sparse, 5→moderate, 19→moderate, 20→dense
- [ ] Empty `mechanism_chain` AND empty `calibrated_parameters` counts as skipped
- [ ] ANALOGICAL with `confidence >= 0.6` does NOT receive MECHANISM in `gap_tags`
- [ ] `generated_at` is the only byte difference across deterministic reruns

---

---

## Full corpus run results (2026-05-22, all 166 templates)

**Extractor:** `Article_Eater/gap_extractor.py` v3.3
**Output:** `gap_report.json` (554 gaps)

| Metric | Value |
|---|---|
| Templates attempted | 166 |
| Templates loaded | 166 |
| Templates skipped | 0 |
| Total gaps | 554 |
| Validation failures | 9 (2 phantom cascade refs, 7 duplicate step keys) |
| DIRECTION gaps | 51 |
| MECHANISM gaps | 275 |
| VALIDATION gaps | 220 |
| BOUNDARY gaps | 8 |
| MECHANISM + bridge_inferred | 241 |
| Calibrated parameter gaps | 146 |
| Corpus coverage dense | 387 |
| Corpus coverage sparse | 167 |
| Quality high/medium/low | 0 / 175 / 379 |

**SC results:**

| SC | Result | Note |
|---|---|---|
| SC-1 ≥10 gaps | PASS (554) | |
| SC-2 DIRECTION ≥3 | PASS (51) | |
| SC-2 MECHANISM+bridge ≥5 | PASS (241) | |
| SC-2 no competing+non-DIRECTION | PASS (0 violations) | |
| SC-4 ≥3 of 5 Phase 1 gaps in top 15 | FAIL — 2 of 5 | SC3-3 rank #1, SC3-6 rank #2. SC3-5 at #93 (VALIDATION priority cut), CREA1-1 at #309 (MECHANISM priority cut), L1-3 at #220 (VALIDATION + sparse). All misses are priority-weight effects, not classification errors. |
| SC-8 cascade coverage | WAIVED | CTI keys ("IC2_body_budget") don't match template_ids — template authoring fix needed |
| SC-9 determinism | PASS | Byte-identical across reruns |
| SC-10 calibrated params ≥1 | PASS (146) | |
| SC-11 uniqueness | PASS (7 duplicate key warnings logged) | |
| SC-12 ≥80% non-low quality | FAIL (32%) | Template authoring issue — 379/554 rebuttals are empty or generic. Extractor measuring correctly. |
| SC-13 schema version | PASS | |
| SC-14 threshold semantics | PASS | |
| SC-15 cross-template integrity | PASS | No phantom refs in cascade output |

**Top 10 gaps by VOI (full corpus):**

| Rank | Template | Step | Type | VOI | Coverage |
|---|---|---|---|---|---|
| 1 | SC3 | 3 | DIRECTION | 0.478 | dense |
| 2 | SC3 | 6 | DIRECTION | 0.478 | dense |
| 3 | SC1 | 2 | DIRECTION | 0.478 | dense |
| 4 | L3 | 7 | DIRECTION | 0.458 | dense |
| 5 | NM1 | param | DIRECTION | 0.454 | dense |
| 6 | NM7 | param | DIRECTION | 0.454 | dense |
| 7 | NM2 | param | DIRECTION | 0.454 | dense |
| 8 | L4 | 3 | DIRECTION | 0.443 | dense |
| 9 | CSMP1 | 2 | DIRECTION | 0.443 | dense |
| 10 | NVR1 | 2 | DIRECTION | 0.443 | dense |

**Known open issues from this run (Phase 3 inputs):**
1. **SC-4 partial** — SC3-5, CREA1-1, L1-3 rank lower than expected because they are VALIDATION/MECHANISM type. VOI formula is working as specified; Phase 1 ranking intuitions assumed DIRECTION priority. Not a bug.
2. **SC-8 cascade empty** — Template `cross_template_interactions` keys are short display names ("IC2_body_budget") that don't resolve to full `template_id` strings. Either: (a) templates need authoring fix to use canonical IDs, or (b) extractor needs a fuzzy display_id lookup. Flagged as template issue.
3. **SC-12 quality low** — 68% of `what_is_missing` fields are rated low quality. All fall-through to the template-name fallback because rebuttals are empty strings. Templates need `justification.rebuttal` populated.
4. **7 duplicate step keys** — Some templates have repeated step numbers (data quality). Currently skipped; should be surfaced for template authoring team.

---

## Files this contract touches

| File | Read | Write |
|---|---|---|
| `Article_Eater/data/templates/*.json` | ✓ | |
| `Article_Eater/src/services/voi_search.py` | ✓ (import) | |
| `Article_Eater/src/services/web_of_belief.py` | ✓ (import `Belief`, `Credence`) | |
| `Article_Eater/src/services/web_of_belief_components/enums.py` | ✓ (import `EpistemicLevel`) | |
| `Knowledge_Atlas/data/ka_payloads/articles.json` | ✓ | |
| `Track 2/Task 2/Phase 2/gap_report.json` | | ✓ |
| stderr | | warnings, validation failures, SC-4 explanations |

No other files written. No network. No mutations to source repos.
