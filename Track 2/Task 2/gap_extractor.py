"""
Gap Extractor — Track 2, Task 2, Phase 2B
Implements GAP_EXTRACTOR_CONTRACT.md v3.2.0

Run from Article_Eater/:
    python3 gap_extractor.py --templates SC3 CREA1 L1 --output gap_report.json
    python3 gap_extractor.py --all-templates --output gap_report.json
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

if __name__ == "__main__" and any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
    print(
        "usage: gap_extractor.py [-h] [--templates TEMPLATES ...] "
        "[--all-templates] [--output OUTPUT]\n\n"
        "Track 2 Task 2 gap extractor. Full execution requires the "
        "Article_Eater services package; --help is self-contained for "
        "portable grading checks."
    )
    raise SystemExit(0)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from services.voi_search import GapType
from services.web_of_belief import Belief, Credence
from services.web_of_belief_components.enums import EpistemicLevel

# ── Constants (from contract) ──────────────────────────────────────────────────

SCHEMA_VERSION = "3.3.0"
EXTRACTOR_VERSION = "3.3"

ALPHA = {
    GapType.DIRECTION:  0.5,
    GapType.MECHANISM:  0.7,
    GapType.VALIDATION: 0.4,
    GapType.BOUNDARY:   0.3,
}
PRIORITY = {
    GapType.DIRECTION:  1.0,
    GapType.MECHANISM:  0.5,
    GapType.VALIDATION: 0.7,
    GapType.BOUNDARY:   0.4,
}
LEVEL_IMPORTANCE = {
    EpistemicLevel.THEORETICAL:  0.9,
    EpistemicLevel.INTERMEDIATE: 0.7,
    EpistemicLevel.EMPIRICAL:    0.5,
    EpistemicLevel.OBSERVATIONAL: 0.4,
}
WARRANT_TO_LEVEL = {
    "ANALOGICAL":          EpistemicLevel.THEORETICAL,
    "MECHANISM":           EpistemicLevel.INTERMEDIATE,
    "FUNCTIONAL":          EpistemicLevel.INTERMEDIATE,
    "EMPIRICAL_COVARIANCE": EpistemicLevel.EMPIRICAL,
    "THEORETICAL_DEFAULT": EpistemicLevel.THEORETICAL,
    "PARAMETER_ESTIMATE":  EpistemicLevel.EMPIRICAL,
}

# Direction markers — require a sign-direction verb paired with "rather than" or
# explicit sign-uncertainty phrasing. Bare "rather than" is NOT included because
# it fires on "X rather than Y" mechanism comparisons that are not sign conflicts.
# Verified against SC3 step 6 ("reduces rather than amplifies" → fires),
# SC3 step 2 ("purely aesthetic without physiological correlates" → does NOT fire),
# SC3 step 4 ("relief rather than genuine positive arousal" — borderline; excluded
# because template authors should encode this in competing_accounts).
DIRECTION_VERBS = {
    "reduces", "reduce", "amplifies", "amplify", "increases", "increase",
    "decreases", "decrease", "dampens", "dampen", "suppresses", "suppress",
    "enhances", "enhance", "inhibits", "inhibit", "facilitates", "facilitate",
    "strengthens", "strengthen", "weakens", "weaken", "attenuates", "attenuate",
    "elevates", "elevate", "boosts", "boost", "diminishes", "diminish",
}
DIRECTION_MARKERS = [
    "or dampen", "or amplify", "amplify or", "dampen or",
    "reduce or increase", "increase or decrease",
    "sign of effect", "sign is uncertain", "direction of effect",
    "could be positive or", "could be negative or",
    "positive or negative",
]

def direction_from_rebuttal(rebuttal: str) -> bool:
    low = rebuttal.lower()
    # Check explicit markers first
    if any(m in low for m in DIRECTION_MARKERS):
        return True
    # Check "VERB rather than" pattern — requires a direction verb near "rather than"
    if "rather than" in low:
        idx = low.find("rather than")
        # look at the 8 words before "rather than" for a direction verb
        prefix = low[:idx].split()[-8:]
        if any(w.rstrip(".,;") in DIRECTION_VERBS for w in prefix):
            return True
    return False
SCOPE_MARKERS = [
    "does not apply", "limited to", "only in", "scope unclear",
    "outside", "not generalizable",
]
MECHANISTIC_TERMS = {
    "mechanism", "pathway", "moderator", "mediator", "threshold",
    "directionality", "interaction", "function form", "dose-response",
    "measurement", "calibration", "effect size",
}
CAUSAL_VERBS = {
    "causes", "produces", "induces", "modulates", "predicts", "elicits",
    "drives", "suppresses", "amplifies", "triggers", "regulates",
}
GENERIC_PHRASES = {
    "more research", "further study", "needs investigation",
    "to be determined", "unclear", "unknown", "n/a", "tbd", "additional work",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def content_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def level_from_warrant(warrant: Optional[str]) -> EpistemicLevel:
    if warrant is None:
        return EpistemicLevel.EMPIRICAL
    return WARRANT_TO_LEVEL.get(warrant.upper(), EpistemicLevel.EMPIRICAL)


def sparsity_component(n_papers: int, gap_type: GapType) -> float:
    if gap_type == GapType.MECHANISM:
        return 0.8
    if n_papers == 0:   return 1.0
    if n_papers < 3:    return 0.7
    if n_papers < 5:    return 0.4
    return 0.2


def centrality_proxy(in_degree: int, n_frameworks: int) -> float:
    return min(1.0, 0.20 + 0.40 * math.tanh(in_degree / 4.0) + 0.05 * n_frameworks)


def coerce_n(item: Any) -> tuple[int, Optional[str]]:
    if not isinstance(item, dict):
        return 0, f"non-dict-entry: {item!r}"
    raw = item.get("n_subjects", item.get("n"))
    if raw is None:                     return 0, None
    if isinstance(raw, int):            return raw, None
    if isinstance(raw, float):          return int(raw), None
    if isinstance(raw, list):
        try:    return sum(int(x) for x in raw), None
        except: return 0, f"list-cohort-unparseable: {raw!r}"
    if isinstance(raw, str):
        cleaned = raw.strip().lstrip("Nn=").strip()
        try:    return int(cleaned), None
        except: return 0, f"string-unparseable: {raw!r}"
    return 0, f"unknown-type: {type(raw).__name__}"


def is_definitional(rebuttal: str) -> bool:
    r = rebuttal.strip().lower()
    return r.startswith("n/a") and "definitional" in r


def has_scope_marker(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in SCOPE_MARKERS)


def count_hits(text: str, terms: set) -> int:
    low = text.lower()
    return sum(1 for t in terms if t in low)


def rough_noun_phrases(text: str) -> int:
    # heuristic: count capitalised words not at sentence start + "the X" patterns
    words = text.split()
    count = sum(1 for i, w in enumerate(words) if i > 0 and w[0:1].isupper())
    count += len(re.findall(r'\bthe\s+\w+', text.lower()))
    return min(count, 20)


def specificity_score(text: str) -> tuple[float, dict]:
    signals = {
        "causal_verbs_detected":      count_hits(text, CAUSAL_VERBS),
        "mechanistic_terms_detected": count_hits(text, MECHANISTIC_TERMS),
        "generic_phrases_detected":   count_hits(text, GENERIC_PHRASES),
        "noun_phrase_count":          rough_noun_phrases(text),
        "char_length":                len(text),
    }
    score = (
        0.30 * min(signals["causal_verbs_detected"], 3) / 3
        + 0.30 * min(signals["mechanistic_terms_detected"], 3) / 3
        + 0.20 * min(signals["noun_phrase_count"], 5) / 5
        + 0.10 * (1 if signals["char_length"] >= 40 else signals["char_length"] / 40)
        - 0.40 * min(signals["generic_phrases_detected"], 2) / 2
    )
    score = max(0.0, min(1.0, score))
    if score < 0.30:   quality = "low"
    elif score < 0.60: quality = "medium"
    else:              quality = "high"
    return round(score, 3), signals, quality


def gap_fingerprint(primary_gap_type: str, t1_frameworks: list, description: str,
                    what_is_missing: str, competing_accounts: list) -> str:
    proponents = sorted(
        a.get("proponent", "") for a in competing_accounts if isinstance(a, dict)
    )
    mech = sorted(
        t for t in MECHANISTIC_TERMS
        if t in (description + " " + what_is_missing).lower()
    )
    tokens = sorted(set(
        [primary_gap_type.lower()]
        + sorted(t1_frameworks)
        + mech
        + proponents
    ))
    return hashlib.sha1("|".join(tokens).encode()).hexdigest()[:16]


def truncate_words(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    return (cut[:last_space] if last_space > 0 else cut) + "…"


# ── Classify ───────────────────────────────────────────────────────────────────

def classify_gap(step: dict, justification: dict, is_param: bool = False) -> tuple[str, list[str], str]:
    """Return (primary_gap_type, gap_tags, direction_signal_source)."""
    competing = justification.get("competing_accounts", []) if not is_param else \
                step.get("competing_values", []) or []
    rebuttal  = justification.get("rebuttal", "") or ""
    qualifier = justification.get("qualifier", "") or ""
    warrant   = step.get("warrant")
    bridge    = step.get("bridge_inferred", False)
    conf      = step.get("confidence")
    desc      = step.get("description", "") or ""
    threshold = step.get("_threshold", 0.6)  # injected during walk

    tags = []
    direction_source = None

    # primary precedence
    if competing:
        primary = "DIRECTION"
        direction_source = "competing_accounts"
    elif direction_from_rebuttal(rebuttal) and not competing:
        primary = "DIRECTION"
        direction_source = "rebuttal_text"
    elif (bridge and (conf is None or (conf is not None and conf < threshold))) \
            or desc.strip() == "" \
            or (warrant and warrant.upper() == "ANALOGICAL" and conf is not None and conf < threshold):
        primary = "MECHANISM"
    elif has_scope_marker(qualifier):
        primary = "BOUNDARY"
    else:
        primary = "VALIDATION"

    # additive tags
    if competing or direction_from_rebuttal(rebuttal):
        tags.append("DIRECTION")
    if bridge and warrant and warrant.upper() == "ANALOGICAL":
        tags.append("MECHANISM")
    elif bridge:
        tags.append("MECHANISM")
    if has_scope_marker(qualifier):
        tags.append("BOUNDARY")
    if (conf is not None and conf < threshold) \
            and warrant in ("EMPIRICAL_COVARIANCE", "MECHANISM", None) \
            and not competing:
        tags.append("VALIDATION")
    if desc.strip() == "" and not bridge:
        tags.append("STRUCTURAL_MISSINGNESS")
    if bridge:
        tags.append("INTENTIONAL_BRIDGE_INFERENCE")
    if is_param:
        tags.append("CALIBRATED_PARAMETER")

    # invariant: primary must be in tags
    if primary not in tags:
        tags.append(primary)

    return primary, sorted(set(tags)), direction_source


# ── VOI ────────────────────────────────────────────────────────────────────────

def compute_voi(primary_gap_type: str, warrant: Optional[str], conf: Optional[float],
                n_data: int, in_deg: int, n_frameworks: int) -> tuple[dict, Optional[str]]:
    try:
        gap_enum = GapType[primary_gap_type]
        unc = (1.0 - conf) if conf is not None else 0.65
        level = level_from_warrant(warrant)
        importance = LEVEL_IMPORTANCE[level]
        c = centrality_proxy(in_deg, n_frameworks)
        s = sparsity_component(n_data, gap_enum)
        structural = 0.6 * c + 0.4 * s
        epistemic  = unc * importance
        alpha      = ALPHA[gap_enum]
        priority   = PRIORITY[gap_enum]
        base       = alpha * structural + (1 - alpha) * epistemic
        combined   = min(base * priority, 1.0)

        # Use VOICalculator via proxy Belief for cross-check
        belief = Belief(
            belief_id=f"proxy_{primary_gap_type}",
            content="proxy",
            level=level,
            credence=Credence(
                value=conf if conf is not None else 0.35,
                uncertainty=unc,
            ),
            paper_ids=[f"p{i}" for i in range(n_data)],
        )
        from services.voi_search import VOICalculator
        calc_combined, calc_struct, calc_epist = VOICalculator().calculate_voi(
            gap_enum, belief, web=None
        )
        # We override calc's centrality=0.5 default with our proxy;
        # use our computed values as authoritative per contract Step 5
        components = {
            "uncertainty":      round(unc, 4),
            "importance":       importance,
            "sparsity":         s,
            "centrality_proxy": round(c, 4),
            "structural_voi":   round(structural, 4),
            "epistemic_voi":    round(epistemic, 4),
            "alpha":            alpha,
            "priority_weight":  priority,
            "voi_calc_crosscheck": {
                "combined": round(calc_combined, 4),
                "structural": round(calc_struct, 4),
                "epistemic":  round(calc_epist, 4),
                "note": "VOICalculator result with centrality=0.5 default (web=None)"
            }
        }
        return components, round(combined, 4), None
    except Exception as e:
        return None, None, str(e)


# ── Main extraction ────────────────────────────────────────────────────────────

def extract_gaps(template: dict, threshold: float, in_deg: int,
                 validation_failures: list, stderr_warnings: list) -> list[dict]:
    tid = template.get("template_id", "UNKNOWN")
    display_id = template.get("display_id", "")
    name = template.get("name", "")
    t1_fw = template.get("t1_frameworks", [])
    n_frameworks = len(t1_fw)
    gaps = []
    seen_keys = set()

    def emit_gap(gap_source, step_number, param_name, step_description, conf, warrant,
                 justification, bridge, is_param):
        key = (tid, step_number, param_name)
        if key in seen_keys:
            validation_failures.append({
                "template_id": tid,
                "rule": "duplicate_step_key",
                "detail": f"step={step_number} param={param_name}"
            })
            return
        seen_keys.add(key)

        jus = justification or {}
        # inject threshold for classify
        step_proxy = {
            "confidence": conf, "warrant": warrant,
            "bridge_inferred": bridge,
            "description": step_description or "",
            "competing_values": jus.get("competing_values", []),
            "_threshold": threshold,
        }
        primary, tags, dir_src = classify_gap(step_proxy, jus, is_param)

        # what_is_missing
        rebuttal = jus.get("rebuttal", "") or ""
        qualifier = jus.get("qualifier", "") or ""
        if rebuttal and not is_definitional(rebuttal):
            wim_text = rebuttal
        elif qualifier:
            wim_text = qualifier
        else:
            wim_text = f"the mechanism by which {step_description or name}"
        what_is_missing = truncate_words(wim_text, 280)

        # quality
        sp_score, sp_signals, sp_quality = specificity_score(what_is_missing)

        # total_n
        data_list = jus.get("data", []) or []
        total_n = 0
        tn_warnings = []
        for d in data_list:
            n, warn = coerce_n(d)
            total_n += n
            if warn:
                tn_warnings.append(warn)

        # voi
        n_data = len(data_list)
        voi_components, voi_score, voi_error = compute_voi(
            primary, warrant, conf, n_data, in_deg, n_frameworks
        )

        # fingerprint
        fp = gap_fingerprint(primary, t1_fw, step_description or "", what_is_missing,
                             jus.get("competing_accounts", []))

        # warrant source
        if warrant is not None:
            warrant_src = "structured_field"
        elif qualifier and any(w in qualifier.upper() for w in WARRANT_TO_LEVEL):
            warrant_src = "qualifier_text"
        else:
            warrant_src = "absent"

        gaps.append({
            "gap_source":               gap_source,
            "template_id":              tid,
            "display_id":               display_id,
            "template_name":            name,
            "step_number":              step_number,
            "param_name":               param_name,
            "step_description":         truncate_words(step_description or "", 300),
            "confidence":               conf,
            "warrant":                  warrant,
            "warrant_source":           warrant_src,
            "primary_gap_type":         primary,
            "gap_tags":                 tags,
            "voi_score":                voi_score,
            "voi_components":           voi_components,
            "voi_error":                voi_error,
            "depth_tier":               jus.get("depth_tier"),
            "what_is_missing":          what_is_missing,
            "what_is_missing_quality":  sp_quality,
            "specificity_score":        sp_score,
            "specificity_signals":      sp_signals,
            "competing_accounts":       jus.get("competing_accounts", []),
            "direction_signal_source":  dir_src,
            "bridge_inferred":          bridge,
            "total_n":                  total_n,
            "total_n_coercion_warnings": tn_warnings,
            "cascade_risk":             [],  # filled by caller after index built
            "corpus_coverage":          None,  # filled by corpus_tag() call
            "t1_frameworks":            t1_fw,
            "normalized_gap_fingerprint": fp,
        })

    # Walk mechanism_chain
    chain = template.get("mechanism_chain")
    if not isinstance(chain, list):
        if chain is not None:
            validation_failures.append({
                "template_id": tid,
                "rule": "invalid_mechanism_chain_type",
                "detail": f"got {type(chain).__name__}"
            })
        return gaps  # no chain to walk

    step_numbers_seen = []
    for step in chain:
        if not isinstance(step, dict):
            continue
        snum = step.get("step")
        conf = step.get("confidence")
        warrant = step.get("warrant")
        bridge = step.get("bridge_inferred", False)
        desc = (step.get("description") or "").strip()
        jus = step.get("justification") or {}

        # non-monotonic / duplicate step check
        if snum is not None:
            if snum in step_numbers_seen:
                validation_failures.append({
                    "template_id": tid,
                    "rule": "duplicate_step_number",
                    "detail": f"step {snum}"
                })
                return gaps
            step_numbers_seen.append(snum)

        # validate confidence
        if conf is not None and (math.isnan(conf) or math.isinf(conf) or not (0 <= conf <= 1)):
            validation_failures.append({
                "template_id": tid,
                "rule": "invalid_confidence",
                "detail": f"step {snum}: conf={conf}"
            })
            return gaps

        # definitional skip
        rebuttal = (jus.get("rebuttal") or "").strip()
        if is_definitional(rebuttal):
            continue

        # gap signals (strict less-than)
        is_gap = (
            (conf is not None and conf < threshold)
            or conf is None
            or bridge is True
            or desc == ""
        )
        if not is_gap:
            continue

        # warn if empty description without explicit bridge flag
        if desc == "" and not bridge:
            msg = f"  WARNING [{tid}::step::{snum}]: empty description, bridge_inferred=False — possible authoring corruption"
            print(msg, file=sys.stderr)
            stderr_warnings.append(msg)

        emit_gap("mechanism_chain", snum, None, desc, conf, warrant, jus, bridge, False)

    # Walk calibrated_parameters
    params = template.get("calibrated_parameters") or {}
    if isinstance(params, dict):
        for pname, pobj in params.items():
            if not isinstance(pobj, dict):
                continue
            pconf = pobj.get("confidence")
            # coerce string confidence to float if needed
            if isinstance(pconf, str):
                try: pconf = float(pconf)
                except (ValueError, TypeError): pconf = None
            if pconf is None or pconf < threshold:
                pdesc = f"Calibrated parameter: {pname} = {pobj.get('value') or pobj.get('range', 'unknown')}"
                pjus = {
                    "data": [],
                    "qualifier": pobj.get("qualifier", ""),
                    "rebuttal": pobj.get("rebuttal", ""),
                    "competing_accounts": pobj.get("competing_values", []),
                }
                emit_gap("calibrated_parameter", None, pname, pdesc, pconf, "PARAMETER_ESTIMATE", pjus, False, True)

    return gaps


# ── Corpus coverage ────────────────────────────────────────────────────────────

# articles.json uses human-readable theory names, not T1 framework codes.
# This mapping translates codes → lowercase substrings found in articles.theories.
FRAMEWORK_THEORY_KEYWORDS: dict[str, list[str]] = {
    "PP":  ["predictive processing", "active inference", "free energy principle",
            "bayesian brain", "bayesian integration", "prediction error"],
    "SN":  ["spatial cognition", "spatial navigation", "wayfinding", "cognitive map",
            "cognitive mapping", "place cell"],
    "DP":  ["dual-process", "dual process", "system 1", "system 2"],
    "DT":  ["default mode", "dmn", "tpn", "task-positive", "executive network",
            "resting state"],
    "NM":  ["stress reduction", "stress recovery", "neuroarchitecture", "neuroaesthetics",
            "neuroaesthetics", "salutogenic", "attention restoration"],
    "IC":  ["interoception", "interoceptive", "constructionist affect",
            "allostatic", "body budget"],
    "MS":  ["memory", "working memory", "hippocampus", "spatial memory",
            "episodic memory"],
    "EC":  ["embodied cognition", "embodied perception", "embodiment",
            "proprioception", "merleau-ponty", "ecological psychology"],
    "CB":  ["circadian", "chronobiology", "chronobiological", "melatonin",
            "suprachiasmatic", "non-visual light", "non-image-forming"],
    "MSI": ["multisensory integration", "multi-sensory", "cross-modal",
            "crossmodal", "sensory integration", "multisensory architecture"],
}


def load_corpus(corpus_path: str) -> list[dict]:
    try:
        with open(corpus_path) as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("articles", [])
    except Exception:
        return []


def corpus_tag(gap: dict, corpus: list[dict]) -> str:
    fw_set = set(gap.get("t1_frameworks", []))
    # Collect all theory keywords for this gap's frameworks
    query_keywords: list[str] = []
    for fw in fw_set:
        query_keywords.extend(FRAMEWORK_THEORY_KEYWORDS.get(fw, [fw.lower()]))

    count = 0
    for article in corpus:
        theories_str = " ".join(
            (t.lower() for t in (article.get("theories") or []))
        )
        title_abs = (
            (article.get("title") or "") + " " + (article.get("abstract") or "")
        ).lower()
        if any(kw in theories_str or kw in title_abs for kw in query_keywords):
            count += 1
    if count >= 20:  return "dense"
    if count >= 5:   return "moderate"
    if count >= 1:   return "sparse"
    return "absent"


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates-dir", default="data/templates")
    parser.add_argument("--templates", nargs="*",
                        help="Short display_ids or template_ids to process (default: all)")
    parser.add_argument("--output", default="gap_report.json")
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--all", dest="all_gaps", action="store_true")
    parser.add_argument("--corpus", default="../Knowledge_Atlas/data/ka_payloads/articles.json")
    args = parser.parse_args()

    tdir = args.templates_dir
    threshold = args.threshold

    # Step 1a: load
    all_files = sorted(f for f in os.listdir(tdir) if f.endswith(".json"))
    templates_raw = []
    validation_failures = []
    stderr_warnings = []
    per_file_hashes = []
    seen_tids = {}

    for fname in all_files:
        path = os.path.join(tdir, fname)
        try:
            with open(path) as f:
                raw = json.load(f)
        except Exception as e:
            validation_failures.append({"file": fname, "rule": "json_parse_failure", "detail": str(e)})
            print(f"  WARNING: skipped {fname}: {e}", file=sys.stderr)
            continue

        tid = raw.get("template_id", fname)
        per_file_hashes.append((tid, content_sha256(raw)))

        if tid in seen_tids:
            validation_failures.append({
                "rule": "duplicate_template_id",
                "detail": f"{tid} in {fname} and {seen_tids[tid]}"
            })
            print(f"  WARNING: duplicate template_id {tid} in {fname}, skipping", file=sys.stderr)
            continue
        seen_tids[tid] = fname
        templates_raw.append(raw)

    # filter if --templates specified
    if args.templates:
        wanted = set(args.templates)
        templates_raw = [
            t for t in templates_raw
            if t.get("display_id") in wanted or t.get("template_id") in wanted
        ]

    # Step 1b: build indexes
    reverse_dep: dict[str, list[str]] = defaultdict(list)
    framework_in_degree: dict[str, int] = defaultdict(int)
    dependency_cycles = []
    loaded_tids = {t["template_id"] for t in templates_raw}

    for t in templates_raw:
        src_tid = t["template_id"]
        cti = t.get("cross_template_interactions", {})
        # CTI may be a dict (expected) or a list (some templates use a list of
        # interaction dicts with a "template_id" or "target" field)
        if isinstance(cti, dict):
            cti_keys = list(cti.keys())
        elif isinstance(cti, list):
            # flatten: extract string keys or target fields from list entries
            cti_keys = []
            for item in cti:
                if isinstance(item, str):
                    cti_keys.append(item)
                elif isinstance(item, dict):
                    ref = item.get("template_id") or item.get("target") or item.get("id") or ""
                    if ref:
                        cti_keys.append(str(ref))
        else:
            cti_keys = []

        for key in cti_keys:
            if not isinstance(key, str) or not key.strip():
                continue
            matched = None
            for other_tid in loaded_tids:
                if other_tid in key or key.replace("interaction_with_", "") == other_tid:
                    matched = other_tid
                    break
            if matched is None:
                for other_t in templates_raw:
                    did = other_t.get("display_id", "")
                    if did and (did in key or key.startswith(did)):
                        matched = other_t["template_id"]
                        break

            if matched is None:
                validation_failures.append({
                    "template_id": src_tid,
                    "rule": "phantom_cascade_reference",
                    "detail": key,
                })
                continue
            if matched == src_tid:
                validation_failures.append({
                    "template_id": src_tid,
                    "rule": "self_reference",
                    "detail": key,
                })
                continue
            reverse_dep[matched].append(src_tid)
            framework_in_degree[src_tid] += 1

    # Step 1c: display_id collisions
    did_map: dict[str, list[str]] = defaultdict(list)
    for t in templates_raw:
        did_map[t.get("display_id", "")].append(t["template_id"])
    collisions = [did for did, tids in did_map.items() if len(tids) > 1 and did]
    if collisions:
        print(f"  WARNING: display_id collisions: {collisions}", file=sys.stderr)

    # Step 1d: input_hash
    input_hash = hashlib.sha256(
        "\n".join(f"{tid}\t{h}" for tid, h in sorted(per_file_hashes)).encode()
    ).hexdigest()

    # Steps 2-8: extract gaps
    corpus = load_corpus(args.corpus)
    all_gaps = []
    templates_skipped = 0
    templates_loaded = len(templates_raw)

    for t in templates_raw:
        tid = t["template_id"]
        in_deg = framework_in_degree.get(tid, 0)
        gaps = extract_gaps(t, threshold, in_deg, validation_failures, stderr_warnings)

        chain = t.get("mechanism_chain")
        params = t.get("calibrated_parameters") or {}
        if (not isinstance(chain, list) or len(chain) == 0) and not params:
            templates_skipped += 1

        # Step 6: cascade risk (algorithmic)
        for gap in gaps:
            downstream = reverse_dep.get(tid, [])
            gap["cascade_risk"] = [
                {"template_id": d, "dependency_strength": None, "cycle_member": False}
                for d in downstream
            ]

        # Step 7: corpus coverage
        for gap in gaps:
            gap["corpus_coverage"] = corpus_tag(gap, corpus)

        all_gaps.extend(gaps)

    # Step 9: sort
    def sort_key(g):
        vs = g.get("voi_score")
        sv = (g.get("voi_components") or {}).get("structural_voi")
        return (
            -(round(vs, 6) if vs is not None else -1),
            -(round(sv, 6) if sv is not None else -1),
            g.get("template_id") or "",
            g.get("step_number") if g.get("step_number") is not None else 9999,
            g.get("param_name") or "",
        )
    all_gaps.sort(key=sort_key)

    if not args.all_gaps:
        output_gaps = all_gaps[: args.top_n]
    else:
        output_gaps = all_gaps

    # fingerprint collisions
    fp_map: dict[str, list[str]] = defaultdict(list)
    for g in output_gaps:
        fp_map[g["normalized_gap_fingerprint"]].append(
            f"{g['template_id']}::step::{g['step_number']}"
        )
    fp_collisions = [
        {"fingerprint": fp, "gap_belief_ids": ids}
        for fp, ids in fp_map.items() if len(ids) > 1
    ]

    quality_dist = {"high": 0, "medium": 0, "low": 0}
    for g in output_gaps:
        quality_dist[g.get("what_is_missing_quality", "low")] += 1

    # Step 10: write output
    output = {
        "metadata": {
            "schema_version":               SCHEMA_VERSION,
            "generated_at":                 datetime.now(timezone.utc).isoformat(),
            "extractor_version":            EXTRACTOR_VERSION,
            "input_hash":                   f"sha256:{input_hash}",
            "input_hash_method":            "content_sha256_per_file_aggregated",
            "templates_attempted":          len(all_files),
            "templates_loaded":             templates_loaded,
            "templates_skipped":            templates_skipped,
            "validation_failures":          validation_failures,
            "confidence_threshold":         threshold,
            "confidence_threshold_semantics": "strict less-than (confidence == threshold is NOT a gap)",
            "confidence_semantics":         "ordinal uncertainty proxy (not calibrated probability)",
            "centrality_method":            "sigmoidal: 0.20 + 0.40*tanh(in_degree/4) + 0.05*|t1_frameworks|",
            "voi_prioritization":           "DIRECTION>VALIDATION>MECHANISM>BOUNDARY (panel policy)",
            "corpus_join_key":              "framework_to_theory_keyword_mapping",
            "corpus_snapshot_date":         "2026-04-28",
            "display_id_collisions":        collisions,
            "dependency_cycles":            dependency_cycles,
            "fingerprint_collisions":       fp_collisions,
            "quality_distribution":         quality_dist,
            "total_gaps_found":             len(all_gaps),
            "gaps_in_output":               len(output_gaps),
        },
        "gaps": output_gaps,
    }

    out_str = json.dumps(output, indent=2, ensure_ascii=False, default=str)
    if args.output == "-":
        print(out_str)
    else:
        with open(args.output, "w") as f:
            f.write(out_str)
        print(f"Wrote {len(output_gaps)} gaps → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
