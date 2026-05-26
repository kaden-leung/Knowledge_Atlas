"""
GapQueryGenerator — Phase 3 implementation of QUERY_GENERATOR_CONTRACT.md v1.4
Reads gap_report.json (Phase 2) → writes query_pairs.json
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# ---------------------------------------------------------------------------
# Schema / version
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.4.0"
COMPATIBLE_GAP_SCHEMA_PREFIX = "3"

# ---------------------------------------------------------------------------
# Framework → anchor phrase (contract table)
# ---------------------------------------------------------------------------

ANCHOR_TABLE = {
    "PP":  "as predicted by predictive processing / active inference theory",
    "MSI": "consistent with multisensory integration theory",
    "EC":  "as predicted by embodied cognition frameworks",
    "NM":  "consistent with Stress Recovery Theory (SRT)",
    "CB":  "as predicted by circadian photobiology",
    "MS":  "as predicted by spatial memory and hippocampal encoding research",
    "IC":  "consistent with interoceptive / constructionist affect theory",
    "DT":  "as predicted by DMN–TPN dynamics",
    "SN":  "as predicted by cognitive mapping theory",
    "DP":  "consistent with dual-process evaluation theory",
}

# Short theory name for use inside sentences (e.g. "can X adjudicate")
SHORT_ANCHOR = {
    "PP":  "predictive processing theory",
    "MSI": "multisensory integration theory",
    "EC":  "embodied cognition theory",
    "NM":  "Stress Recovery Theory",
    "CB":  "circadian photobiology",
    "MS":  "hippocampal-spatial memory theory",
    "IC":  "interoceptive affect theory",
    "DT":  "DMN–TPN network theory",
    "SN":  "cognitive mapping theory",
    "DP":  "dual-process theory",
}

# Framework → measurement tradition phrase (for AI Citation Pattern F)
# IC is intentionally broad ("studies measuring interoceptive processing") rather than
# fMRI-specific, because the interoception literature includes behavioral, physiological,
# and self-report traditions in addition to neuroimaging.
FRAMEWORK_MEASURE = {
    "PP":  "psychophysiological studies measuring skin conductance or arousal response",
    "MSI": "multimodal experimental studies measuring cross-modal integration",
    "EC":  "studies measuring embodied or proprioceptive responses",
    "NM":  "studies measuring cortisol, heart rate variability, or stress recovery markers",
    "CB":  "chronobiology studies measuring melanopic irradiance or melatonin",
    "MS":  "fMRI and behavioral studies of hippocampal-spatial encoding",
    "IC":  "studies measuring interoceptive processing",
    "DT":  "fMRI studies of DMN–TPN network dynamics",
    "SN":  "behavioral and neuroimaging studies of spatial navigation",
    "DP":  "behavioral studies of dual-process evaluation",
}

# Content-aware measurement override — same triggers as anchor override.
# Reward/novelty gaps need dopaminergic measurement framing, not cortisol.
_MEASURE_OVERRIDE_RULES = [
    (
        re.compile(r"\b(novelty|dopamine|dopaminergic|RPE|reward prediction|wanting|liking|information gain|curiosity)\b", re.I),
        "fMRI and dopaminergic-imaging studies of reward and novelty processing",
    ),
    (
        re.compile(r"\b(serotonin|serotonergic|5-HT|melatonin|circadian phase|raphe)\b", re.I),
        "studies measuring serotonin synthesis, melatonin, or circadian phase markers",
    ),
    (
        re.compile(r"\b(polyvagal|vagal tone|RSA|respiratory sinus arrhythmia)\b", re.I),
        "psychophysiological studies measuring respiratory sinus arrhythmia and vagal tone",
    ),
]


def pick_measure(frameworks: list, wim: str = "", step_desc: str = "") -> str:
    """Pick measurement phrase: content-aware override first, then framework table."""
    text = (wim or "") + " " + (step_desc or "")
    for pattern, override in _MEASURE_OVERRIDE_RULES:
        if pattern.search(text):
            return override
    for fw in frameworks:
        if fw in FRAMEWORK_MEASURE:
            return FRAMEWORK_MEASURE[fw]
    return "experimental studies"


# Framework → primary concept for Boolean expansion
FRAMEWORK_CONCEPTS = {
    "PP":  "prediction error",
    "MSI": "multisensory integration",
    "EC":  "embodied cognition",
    "NM":  "stress recovery",
    "CB":  "circadian rhythm",
    "MS":  "spatial memory",
    "IC":  "interoception",
    "DT":  "default mode network",
    "SN":  "spatial navigation",
    "DP":  "dual process",
}

# ---------------------------------------------------------------------------
# Hardcoded fallback synonyms (sorted alphabetically per contract SC-8)
# ---------------------------------------------------------------------------

FALLBACK_SYNONYMS = {
    "prediction error":      ["active inference", "PE signal", "predictive coding", "surprise signal"],
    "arousal":               ["autonomic activation", "arousal", "LC-NE burst", "noradrenergic", "orienting reflex"],
    "multisensory":          ["cross-modal", "multimodal", "multisensory integration", "sensory convergence"],
    "embodied cognition":    ["embodied cognition", "interoceptive signal", "proprioception", "somatic marker"],
    "stress recovery":       ["autonomic recovery", "cortisol", "HPA axis", "physiological restoration", "stress recovery"],
    "circadian rhythm":      ["chronobiological", "circadian rhythm", "ipRGC", "melanopsin", "non-visual light effect"],
    "spatial memory":        ["cognitive map", "hippocampal encoding", "place cell", "spatial memory"],
    "interoception":         ["allostatic load", "body budget", "interoception", "predictive interoception"],
    "spatial navigation":    ["cognitive map", "path integration", "spatial navigation", "wayfinding"],
    "default mode network":  ["default mode network", "DMN", "mind-wandering", "task-positive network", "TPN"],
    "skin conductance":      ["electrodermal", "galvanic skin response", "GSR", "skin conductance"],
    "cortisol":              ["cortisol", "HPA axis", "salivary cortisol", "stress hormone"],
}

# ---------------------------------------------------------------------------
# Boolean AST
# ---------------------------------------------------------------------------

@dataclass
class ExactPhrase:
    term: str
    priority: str = "core"    # core | supporting | optional


@dataclass
class OrGroup:
    terms: list
    priority: str = "core"

    def sorted_terms(self):
        return sorted(self.terms)


@dataclass
class Exclusion:
    term: str


@dataclass
class AndGroup:
    groups: list

    def serialize(self) -> str:
        parts = []
        for g in self.groups:
            if isinstance(g, ExactPhrase):
                parts.append(f'"{g.term}"')
            elif isinstance(g, OrGroup):
                joined = " OR ".join(f'"{t}"' for t in g.sorted_terms())
                parts.append(f"({joined})")
            elif isinstance(g, Exclusion):
                term = g.term
                if " " in term:
                    parts.append(f'-"{term}"')
                else:
                    parts.append(f"-{term}")
        return " AND ".join(p for p in parts if not p.startswith("-")) + \
               (" " + " ".join(p for p in parts if p.startswith("-"))).rstrip()

    def validate(self, s: str) -> list:
        errors = []
        if s.count("(") != s.count(")"):
            errors.append("unbalanced parentheses")
        if "()" in s:
            errors.append("empty group")
        if re.search(r"(AND|OR)\s*$", s):
            errors.append("dangling operator")
        if "AND AND" in s or "OR OR" in s:
            errors.append("consecutive operators")
        return errors

    def drop_to_limit(self, max_chars: int) -> tuple:
        """Drop groups by priority until serialized string fits max_chars.
        Returns (serialized_str, was_truncated)."""
        DROP_ORDER = ["optional", "supporting"]

        def try_serialize(groups):
            ag = AndGroup(groups)
            s = ag.serialize()
            errs = ag.validate(s)
            return s, errs

        current = list(self.groups)
        s, _ = try_serialize(current)
        if len(s) <= max_chars:
            return s, False

        for priority_to_drop in DROP_ORDER:
            removable = [g for g in current if getattr(g, "priority", None) == priority_to_drop]
            for item in removable:
                current.remove(item)
                s, errs = try_serialize(current)
                if not errs and len(s) <= max_chars:
                    return s, True
                if errs:
                    # Re-derive from remaining groups
                    s, _ = try_serialize(current)
                    if len(s) <= max_chars:
                        return s, True

        # Step 5: collapse to 2 core phrases + 1 OR group
        core_phrases = [g for g in current if isinstance(g, ExactPhrase) and g.priority == "core"]
        core_or = [g for g in current if isinstance(g, OrGroup) and g.priority == "core"]
        minimal = core_phrases[:1] + core_or[:1]
        if minimal:
            s, _ = try_serialize(minimal)
            return s, True

        return try_serialize(current)[0], True


# ---------------------------------------------------------------------------
# Structural component count (contract Step 6)
# ---------------------------------------------------------------------------

EVIDENCE_OPENERS = [
    r"what experimental", r"what peer-reviewed", r"what neuroimaging",
    r"what do experimental", r"what fmri", r"what eeg",
    r"through what neural", r"through what physiological",
    r"how does", r"what longitudinal", r"what studies",
    r"when\s+\w+.{0,40}account.{0,40}conflict",
    # Measure-phrase signals — Pattern F injects these via pick_measure().
    # Word-boundary "studies" combined with a known evidence adjective.
    r"\b(psychophysiological|chronobiology|behavioral|neuroimaging|"
    r"longitudinal|experimental|peer-reviewed|fmri|eeg|"
    r"dopaminergic-imaging|multimodal)\s+(and\s+\w+\s+)?studies\b",
    r"\bstudies\s+(measuring|of)\b",
]

DOMAIN_SPECIFIC_MECHANISM = [
    "skin conductance", "cortisol", "gsr", "electrodermal",
    "fmri", "eeg", "eeg alpha", "alpha wave", "heart rate variability", "hrv",
    "dmn", "tpn", "ecn", "prefrontal", "amygdala", "hippocampal",
    "hpa axis", "prediction error", "arousal response",
    "cortical activation", "neural coupling", "predictive coding", "active inference",
    "melanopsin", "serotonin", "dopamine", "serotonin synthesis", "raphe",
    "melatonin", "circadian", "iprgc", "scn", "cone-opponent",
    "galvanic skin", "electrodermal activity", "working memory load",
    "novelty response", "dopaminergic", "ventral striatum",
    "rsa", "vagal", "heart rate", "interoceptive",
]

CONDITION_TERMS_WB = [
    "architectural", "building", "luminance", "sensory richness",
    "natural light", "fractal", "acoustic", "biophilic",
    "field of view", "field-of-view", "daylighting", "window view",
    "spatial transition", "threshold", "daylight", "light level",
    "color temperature", "cct", "space syntax", "integration value",
]

POPULATION_REGEX = re.compile(
    r"(among|in)\s+(?:[a-z]+\s+){0,3}(workers|patients|occupants|adults|participants|children|students|subjects|navigators|visitors)"
)

ANCHOR_PHRASES = [
    "predictive processing", "active inference", "attention restoration",
    "stress recovery theory", "biophilia", "embodied cognition",
    "default mode network", "multisensory integration", "circadian",
    "dual-process", "spatial navigation", "interoceptive",
    "space syntax", "predictive coding",
    # Content-override anchors (must be recognized by signal detection)
    "dopaminergic reward-learning", "polyvagal theory",
    "neurohormonal regulation", "cognitive mapping",
]


def count_structural_components(query: str) -> int:
    low = query.lower()
    if not re.search(r"[a-z]+(?: [a-z]+){2,}", low):
        return 0
    c1 = int(any(re.search(p, low) for p in EVIDENCE_OPENERS))
    c2 = int(any(re.search(r"\b" + re.escape(t) + r"\b", low) for t in DOMAIN_SPECIFIC_MECHANISM))
    c3 = int(any(re.search(r"\b" + re.escape(t) + r"\b", low) for t in CONDITION_TERMS_WB))
    c4 = int(bool(POPULATION_REGEX.search(low)))
    c5 = int(any(re.search(r"\b" + re.escape(a) + r"\b", low) for a in ANCHOR_PHRASES))
    return c1 + c2 + c3 + c4 + c5


# ---------------------------------------------------------------------------
# Vocabulary loading + hash
# ---------------------------------------------------------------------------

def load_vocabulary(vocab_path: str) -> tuple:
    """Returns (concept_to_synonyms dict, vocabulary_hash str)."""
    path = Path(vocab_path)
    if not path.exists() or not YAML_AVAILABLE:
        return FALLBACK_SYNONYMS, _hash_vocab(FALLBACK_SYNONYMS)

    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
        vocab = {}
        for concept, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            synonyms = []
            for key in ("cnfa_terms", "psychology_terms", "neuroscience_terms", "architecture_terms"):
                terms = entry.get(key, [])
                if isinstance(terms, list):
                    synonyms.extend(terms)
            if synonyms:
                # Sort alphabetically per SC-8
                vocab[concept] = sorted(set(synonyms))
        merged = {**FALLBACK_SYNONYMS, **vocab}
        return merged, _hash_vocab(merged)
    except Exception as e:
        print(f"WARNING: vocab load failed ({e}); using fallback", file=sys.stderr)
        return FALLBACK_SYNONYMS, _hash_vocab(FALLBACK_SYNONYMS)


def _hash_vocab(vocab: dict) -> str:
    s = json.dumps(vocab, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(s.encode()).hexdigest()


def get_synonyms(vocab: dict, concept: str, max_synonyms: int = 3) -> list:
    concept_lower = concept.lower().strip()
    if concept_lower in vocab:
        return vocab[concept_lower][:max_synonyms]
    for k, v in vocab.items():
        if concept_lower in k or k in concept_lower:
            return v[:max_synonyms]
    return [concept_lower]


# ---------------------------------------------------------------------------
# Proponent validity guard
# ---------------------------------------------------------------------------

def valid_proponent(label) -> bool:
    if not label or not isinstance(label, str):
        return False
    normalized = label.strip().lower()
    bad = {"", "a", "b", "account a", "account b", "account_a", "account_b", "none", "null"}
    if normalized in bad:
        return False
    return len(re.findall(r"[a-zA-Z]", normalized)) >= 2


def extract_proponent_name(account: dict) -> str:
    proponent = account.get("proponent", "") or ""
    # Strip parenthetical qualifiers like "(panel debate)"
    name = re.sub(r"\s*\(.*?\)", "", proponent).strip()
    # Take just the first author name if multiple
    name = name.split(",")[0].strip()
    return name if name else proponent.strip()


# ---------------------------------------------------------------------------
# Anchor phrase selection
# ---------------------------------------------------------------------------

# Content-aware anchor override patterns.
# The framework code (e.g. NM) is sometimes used for semantically distinct gaps:
# NM gaps about novelty/dopamine should NOT anchor on Stress Recovery Theory.
# These regexes detect mechanistic vocabulary and override the framework-table anchor.
_ANCHOR_OVERRIDE_RULES = [
    # (regex pattern, long anchor, short anchor) — first match wins
    (
        re.compile(r"\b(novelty|dopamine|dopaminergic|RPE|reward prediction|wanting|liking|information gain|curiosity)\b", re.I),
        "as predicted by dopaminergic reward-learning theory",
        "dopaminergic reward-learning theory",
    ),
    (
        re.compile(r"\b(serotonin|serotonergic|5-HT|melatonin|circadian phase|HPA|cortisol|raphe)\b", re.I),
        "as predicted by circadian photobiology and neurohormonal regulation",
        "circadian and neurohormonal regulation",
    ),
    (
        re.compile(r"\b(polyvagal|vagal tone|RSA|respiratory sinus arrhythmia|ventral vagal|safety signal)\b", re.I),
        "as predicted by Polyvagal Theory",
        "Polyvagal Theory",
    ),
]


def _override_anchor(wim: str, step_desc: str) -> tuple:
    """Return (long, short) anchor strings if content matches an override rule,
    otherwise (None, None) to defer to the framework table."""
    text = (wim or "") + " " + (step_desc or "")
    for pattern, long_a, short_a in _ANCHOR_OVERRIDE_RULES:
        if pattern.search(text):
            return long_a, short_a
    return None, None


def pick_anchor(frameworks: list, wim: str = "", step_desc: str = "") -> str:
    """Pick anchor: content-aware override first, then framework table."""
    long_override, _ = _override_anchor(wim, step_desc)
    if long_override:
        return long_override
    for fw in frameworks:
        if fw in ANCHOR_TABLE:
            return ANCHOR_TABLE[fw]
    return "as predicted by environmental psychology theory"


def pick_short_anchor(frameworks: list, wim: str = "", step_desc: str = "") -> str:
    _, short_override = _override_anchor(wim, step_desc)
    if short_override:
        return short_override
    for fw in frameworks:
        if fw in SHORT_ANCHOR:
            return SHORT_ANCHOR[fw]
    return "environmental psychology theory"


# ---------------------------------------------------------------------------
# AI Citation query builders
# ---------------------------------------------------------------------------

DEPTH_POPULATION = {
    "A": "in building occupants",
    "B": "in participants exposed to built environments",
    "C": "",
}


def population_phrase(gap: dict) -> str:
    tier = gap.get("depth_tier")
    if tier is None:
        return ""
    return DEPTH_POPULATION.get(tier, "in participants")


def trim_wim(wim: str, max_chars: int = 120) -> str:
    wim = wim.strip()
    if len(wim) > max_chars:
        wim = wim[:max_chars].rsplit(" ", 1)[0] + "…"
    # Strip trailing failure-condition preamble
    wim = re.sub(r"^(The claim would fail if[^:]*:\s*\([a-z]\)\s*)", "", wim)
    wim = wim.strip('" ')
    return wim


# ---------------------------------------------------------------------------
# Improvement #3: deterministic specific-population extractor.
# Pulls a more specific population/condition phrase from step_description
# when one is regex-derivable; otherwise falls back to the static depth-tier
# default. Per design review: no NLP, no parsing — regex only.
# ---------------------------------------------------------------------------

_SPECIFIC_POP_PATTERNS = [
    # "[subject] [activity] [1-3 token condition]" — hyphenated words count as one token,
    # whitespace is the only token separator. This prevents capping at "a high-integration"
    # when "space" should also be included.
    re.compile(
        r"\b(occupants?|navigators?|visitors?|adults?|participants?|patients?|users?)"
        r"\s+(?:exposed to|navigating|in|under|during|viewing)\s+"
        r"([a-z][a-z\-]*(?:\s+[a-z][a-z\-]*){0,3})",
        re.I,
    ),
    # "[adjective] daylight / threshold / etc."
    re.compile(
        r"\b((?:time-varying|dynamic|natural|architectural|biophilic|circadian|spatial)"
        r"\s+(?:daylight|threshold|luminance|sensory|transitions?|environments?|cues?|exposure))\b",
        re.I,
    ),
]


def compose_specific_population(gap: dict) -> str:
    """Return a sharper '[preposition] [descriptor] [class]' phrase if extractable
    from step_description; else fall back to the depth-tier default."""
    step_desc = gap.get("step_description", "") or ""
    tier = gap.get("depth_tier")
    default = DEPTH_POPULATION.get(tier, "") if tier else ""

    # Pattern A: subject + activity + condition
    m = _SPECIFIC_POP_PATTERNS[0].search(step_desc)
    if m:
        subject = m.group(1).lower().rstrip("s") + "s"  # normalize plural
        condition = m.group(2).strip().lower()
        return f"in {subject} exposed to {condition}"

    # Pattern B: prefix a default population with an extracted environmental adjective phrase
    m2 = _SPECIFIC_POP_PATTERNS[1].search(step_desc)
    if m2 and default:
        env_phrase = m2.group(1).lower()
        # "in participants exposed to built environments" → "in participants exposed to [env_phrase]"
        if "exposed to" in default:
            return re.sub(r"exposed to .+$", f"exposed to {env_phrase}", default)
        return f"{default} under {env_phrase}"

    return default


def _argue_intro(name: str, claim: str) -> dict:
    """Build a grammatically correct 'argues that/for' clause.
    Handles: 'et al.' plural verb, duplicate proponent prefix in claim,
    noun-phrase claims that don't take 'that' (use 'argues for' instead)."""
    name = (name or "").strip()
    claim = (claim or "").strip()

    # Strip duplicate proponent prefix: "Grossman's critique" when name="Grossman"
    last = re.split(r"\s+", name)[-1] if name else ""
    if last:
        # Drop leading "[Last]'s" / "[Last]" from the claim
        claim = re.sub(rf"^\s*{re.escape(last)}('s)?\s+", "", claim, count=1, flags=re.IGNORECASE)

    # Drop a leading capitalized determiner "The " that creates "argues that The X..." awkwardness
    claim = re.sub(r"^The\s+", "", claim).strip()

    # Verb agreement: "Lewy et al." takes plural "argue"
    is_plural = bool(re.search(r"\bet al\.?\s*$", name))
    verb = "argue" if is_plural else "argues"

    # Detect noun-phrase claims (no verb in first 6 tokens) → use "argues for".
    # Window widened to 6 to catch verbs at depth (e.g. "X of Y of Z depends on W").
    first_tokens = claim.split()[:6]
    has_verb = any(
        re.match(
            r"(is|are|was|were|has|have|does|do|can|may|might|will|reduces?|increases?|"
            r"drives?|mediates?|produces?|depends?|affects?|operates?|emerges?|requires?|"
            r"engages?|generates?|encodes?|switches?|modulates?)$",
            t.rstrip(",.;:"), re.I,
        )
        for t in first_tokens
    )
    if not has_verb:
        preposition = "for"
        # Lowercase first letter for "argues for X" when claim starts with a regular capitalized
        # noun — but preserve acronyms (CCT, RPE, fMRI) and recognized proper-noun phrases.
        if claim and claim[0].isupper() and not _is_proper_noun_start(claim):
            first_word = claim.split()[0] if claim else ""
            if not (len(first_word) >= 2 and first_word.isupper()):
                claim = claim[0].lower() + claim[1:]
    else:
        preposition = "that"

    return {"name": name, "verb": verb, "preposition": preposition, "claim": claim}


def _is_proper_noun_start(s: str) -> bool:
    """Heuristic: claim starts with a proper noun if first word matches
    Theory-name patterns like 'Theory-theory' or 'Polyvagal'."""
    first = s.split()[0] if s else ""
    return bool(re.match(r"^[A-Z][a-z]+-[A-Za-z]", first)) or first in {
        "Polyvagal", "Theory-theory", "Bayesian", "Hebbian", "Pavlovian", "Skinnerian",
    }


def _case_b_label(gap: dict) -> str:
    """Build a clean label for the template's default-position account in Case B.
    Avoids the 'X model assumption' template-leak and the 'mechanism mechanism'
    duplication."""
    step_desc = gap.get("step_description", "") or ""
    template_name = gap.get("template_name", "") or ""

    # Try to extract a clean mechanism phrase from step_desc first noun phrase
    mech = _extract_clean_mechanism(step_desc) or _extract_clean_mechanism(template_name)
    if not mech:
        return "the alternative template-based prediction"

    # Mechanism-mechanism duplication guard (per review)
    if mech.lower().rstrip().endswith("mechanism") or mech.lower().rstrip().endswith("model"):
        return f"the alternative {mech} stated in the template"
    return f"the alternative {mech} mechanism stated in the template"


def _extract_clean_mechanism(text: str) -> str:
    """Pull a 2–4 word noun phrase suitable for use after 'the alternative ...'.
    Reuses arch-phrase artifact stripping."""
    if not text:
        return ""
    lines = [ln.strip() for ln in re.split(r"[;\n]", text) if ln.strip()]
    clean = lines[0] if lines else text
    if ":" in clean:
        clean = clean.split(":", 1)[0]
    clean = _TEMPLATE_ARTIFACTS.sub(" ", clean)
    clean = re.sub(r"^[\s→▶•:]+", "", clean).strip()
    words = [w for w in clean.split() if re.match(r"^[a-zA-Z][a-zA-Z\-]*$", w)]
    # Drop adverbs (most end in -ly) so we don't get "architectural cues previously mechanism"
    content = [
        w for w in words
        if w.lower() not in STOPWORDS and not w.lower().endswith("ly")
    ][:3]
    return " ".join(content).lower() if len(content) >= 2 else ""


_DANGLING_CONJUNCTIONS = re.compile(
    r"\s+(and|but|or|nor|yet|so|—|which|that|while|whereas|not|rather)\s*$",
    re.IGNORECASE,
)


def _clip_claim(text: str, max_chars: int = 100) -> str:
    """Clip claim at a clause boundary; strip dangling conjunctions afterward."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return _dangling_strip(text.rstrip(";,. "))
    # Prefer semicolon or period (stronger clause boundary) over comma
    for sep in (";", ".", ","):
        idx = text.rfind(sep, 0, max_chars)
        if idx > 30:
            candidate = text[:idx].rstrip()
            candidate = _dangling_strip(candidate)
            if len(candidate) > 20:
                return candidate
    # Fallback: word boundary
    clipped = text[:max_chars].rsplit(" ", 1)[0]
    return _dangling_strip(clipped.rstrip(";,."))


def _dangling_strip(s: str) -> str:
    """Remove trailing conjunctions and balance parentheses left by truncation."""
    s = _DANGLING_CONJUNCTIONS.sub("", s).rstrip(";,. ")
    # If parens are unbalanced (open > close), trim back to the last balanced point.
    if s.count("(") > s.count(")"):
        idx = s.rfind("(")
        if idx > 20:
            s = s[:idx].rstrip(";,. ")
            s = _DANGLING_CONJUNCTIONS.sub("", s).rstrip(";,. ")
    return s


def build_pattern_F(gap: dict) -> tuple:
    """Returns (query_str, composed_from, direction_account_b_source, generation_mode)"""
    accounts = gap.get("competing_accounts", [])
    valid_accounts = [a for a in accounts if valid_proponent(a.get("proponent", ""))]

    wim = gap.get("what_is_missing", "")
    step_desc = gap.get("step_description", "")
    anchor = pick_anchor(gap.get("t1_frameworks", []), wim, step_desc)
    short_anc = pick_short_anchor(gap.get("t1_frameworks", []), wim, step_desc)
    measure_phrase = pick_measure(gap.get("t1_frameworks", []), wim, step_desc)
    pop = compose_specific_population(gap)

    if len(valid_accounts) >= 2:
        a_name = extract_proponent_name(valid_accounts[0])
        # claim > account > implication as fallback
        a_claim = _clip_claim(
            valid_accounts[0].get("claim", "") or valid_accounts[0].get("account", ""), 90
        )
        b_name = extract_proponent_name(valid_accounts[1])
        b_claim = _clip_claim(
            valid_accounts[1].get("claim", "") or valid_accounts[1].get("account", ""), 90
        )
        a_intro = _argue_intro(a_name, a_claim)
        b_intro = _argue_intro(b_name, b_claim)
        pop_clause = f" {pop}" if pop else ""
        query = (
            f"When {a_intro['name']} {a_intro['verb']} {a_intro['preposition']} {a_intro['claim']}, "
            f"versus {b_intro['name']}'s claim that {b_intro['claim']}, "
            f"which is better supported by {measure_phrase}{pop_clause}, "
            f"and can {short_anc} adjudicate between them?"
        )
        return query, "competing_accounts", "competing_accounts", "evidence_grounded"

    elif len(valid_accounts) == 1:
        a_name = extract_proponent_name(valid_accounts[0])
        a_claim = _clip_claim(
            valid_accounts[0].get("claim", "") or valid_accounts[0].get("account", ""), 90
        )
        # Case B: named challenger vs. template's default prediction.
        # Pull primary mechanism from step_desc rather than template title for cleaner B-label.
        b_label = _case_b_label(gap)
        a_intro = _argue_intro(a_name, a_claim)
        pop_clause = f" {pop}" if pop else ""
        query = (
            f"When {a_intro['name']} {a_intro['verb']} {a_intro['preposition']} {a_intro['claim']}, "
            f"versus {b_label}, "
            f"which account is better supported by {measure_phrase}{pop_clause}, "
            f"and can {short_anc} adjudicate between them?"
        )
        return query, "competing_accounts+template_name", "justification_data", "evidence_grounded"

    else:
        # Case C: rebuttal-text DIRECTION, no named proponents → Pattern C fallback
        wim = trim_wim(gap.get("what_is_missing", ""), 110)
        step_desc = gap.get("step_description", "")[:80]
        pop_clause = f" {pop}" if pop else ""
        query = (
            f"What experimental evidence supports or refutes the claim that "
            f"{wim or step_desc}{pop_clause}, {anchor}?"
        )
        return query, "what_is_missing", None, "evidence_grounded"


def build_pattern_DE(gap: dict) -> tuple:
    wim_raw = gap.get("what_is_missing", "")
    wim = trim_wim(wim_raw, 110)
    step_desc = gap.get("step_description", "")
    anchor = pick_anchor(gap.get("t1_frameworks", []), wim_raw, step_desc)
    short_anc = pick_short_anchor(gap.get("t1_frameworks", []), wim_raw, step_desc)
    pop = compose_specific_population(gap)
    quality = gap.get("what_is_missing_quality", "low")

    if quality in ("medium", "high") and wim:
        mechanism_phrase = wim
        composed_from = "what_is_missing"
        generation_mode = "evidence_grounded"
    elif step_desc:
        mechanism_phrase = step_desc[:80]
        composed_from = "step_description"
        generation_mode = "description_scaffolded"
    else:
        template_name = gap.get("template_name", "architectural process")
        mechanism_phrase = f"the {template_name.lower()} mechanism"
        composed_from = "template_name_fallback"
        generation_mode = "inferential_scaffold"

    pop_clause = f" {pop}" if pop else ""
    query = (
        f"Through what neural or physiological pathway does {mechanism_phrase}, "
        f"and what fMRI or psychophysiological evidence{pop_clause} supports "
        f"{short_anc} as predicting this pathway, {anchor}?"
    )
    return query, composed_from, generation_mode


def build_pattern_BC(gap: dict) -> tuple:
    wim_raw = gap.get("what_is_missing", "")
    wim = trim_wim(wim_raw, 110)
    step_desc = gap.get("step_description", "")
    anchor = pick_anchor(gap.get("t1_frameworks", []), wim_raw, step_desc)
    pop = compose_specific_population(gap)
    quality = gap.get("what_is_missing_quality", "low")

    if quality in ("medium", "high") and wim:
        phenomenon = wim
        composed_from = "what_is_missing"
        generation_mode = "evidence_grounded"
    elif step_desc:
        phenomenon = _clip_claim(step_desc, 90)
        composed_from = "step_description"
        generation_mode = "description_scaffolded"
    else:
        template_name = gap.get("template_name", "the environmental effect")
        phenomenon = f"the {template_name.lower()} effect"
        composed_from = "template_name_fallback"
        generation_mode = "inferential_scaffold"

    pop_clause = f" {pop}" if pop else ""
    query = (
        f"What experimental studies measuring physiological or behavioral outcomes "
        f"find that {phenomenon}{pop_clause}, "
        f"and do replications support the effect, {anchor}?"
    )
    return query, composed_from, generation_mode


def build_pattern_A(gap: dict) -> tuple:
    wim_raw = gap.get("what_is_missing", "")
    wim = trim_wim(wim_raw, 110)
    step_desc = gap.get("step_description", "")
    anchor = pick_anchor(gap.get("t1_frameworks", []), wim_raw, step_desc)
    pop = compose_specific_population(gap)
    quality = gap.get("what_is_missing_quality", "low")

    if quality in ("medium", "high") and wim:
        phenomenon = wim
        composed_from = "what_is_missing"
        generation_mode = "evidence_grounded"
    else:
        phenomenon = _clip_claim(step_desc, 90) if step_desc else gap.get("template_name", "")[:60]
        composed_from = "step_description" if step_desc else "template_name_fallback"
        generation_mode = "description_scaffolded" if step_desc else "inferential_scaffold"

    pop_clause = f" {pop}" if pop else ""
    query = (
        f"What peer-reviewed evidence shows that {phenomenon}{pop_clause}, "
        f"and under which boundary conditions does {anchor} predict this relationship?"
    )
    return query, composed_from, generation_mode


def build_ai_citation(gap: dict) -> dict:
    gap_type = gap.get("primary_gap_type", "MECHANISM")
    direction_account_b_source = None
    direction_fallback = False

    if gap_type == "DIRECTION":
        accounts = gap.get("competing_accounts", [])
        valid_accounts = [a for a in accounts if valid_proponent(a.get("proponent", ""))]
        if valid_accounts:
            query, composed_from, direction_account_b_source, generation_mode = build_pattern_F(gap)
            pattern = "F"
        else:
            # rebuttal_text DIRECTION with no named proponents → Pattern C
            query, composed_from, generation_mode = build_pattern_BC(gap)
            pattern = "C"
            direction_fallback = True
    elif gap_type == "MECHANISM":
        query, composed_from, generation_mode = build_pattern_DE(gap)
        pattern = "E"
    elif gap_type == "VALIDATION":
        query, composed_from, generation_mode = build_pattern_BC(gap)
        pattern = "B"
    else:  # BOUNDARY
        query, composed_from, generation_mode = build_pattern_A(gap)
        pattern = "A"

    # Length enforcement (tiered caps)
    max_len = 420 if gap_type == "DIRECTION" else 340
    truncated = False
    if len(query) > max_len:
        query = query[:max_len].rsplit(" ", 1)[0]
        if not query.endswith("?"):
            query += "?"
        truncated = True

    # Ensure ends with ?
    if not query.strip().endswith("?"):
        query = query.rstrip(".") + "?"

    # Specificity guard: max 2 commas and max 1 em dash for single-account patterns.
    # Pattern F (DIRECTION) is exempt — its dialectical structure requires more commas,
    # and the 420-char limit already controls length. (Contract Known Limitation #6)
    trimmed_clause = False
    if pattern != "F":
        comma_count = query.count(",")
        dash_count = query.count("—")
        if comma_count > 2 or dash_count > 1:
            parts = query.split(",")
            if len(parts) > 3:
                trimmed = ",".join(parts[:2]) + "?"
                query = trimmed
                trimmed_clause = True

    return {
        "query": query,
        "pattern": pattern,
        "composed_from": composed_from,
        "generation_mode": generation_mode,
        "semantic_confidence": (
            "low" if composed_from == "template_name_fallback"
            else "medium" if composed_from == "step_description"
            else "high"
        ),
        "direction_account_b_source": direction_account_b_source,
        "direction_fallback": direction_fallback,
        "truncated": truncated,
        "trimmed_clause": trimmed_clause,
    }


# ---------------------------------------------------------------------------
# Boolean query builder
# ---------------------------------------------------------------------------

def build_boolean(gap: dict, vocab: dict) -> dict:
    frameworks = gap.get("t1_frameworks", [])
    wim = gap.get("what_is_missing", "")
    step_desc = gap.get("step_description", "")
    template_name = gap.get("template_name", "")
    gap_type = gap.get("primary_gap_type", "MECHANISM")
    total_n = gap.get("total_n") or 0
    corpus_coverage = gap.get("corpus_coverage", "absent")

    # Primary concept from first framework
    primary_fw = frameworks[0] if frameworks else "PP"
    primary_concept = FRAMEWORK_CONCEPTS.get(primary_fw, "environmental cognition")
    primary_synonyms = get_synonyms(vocab, primary_concept, max_synonyms=3)

    # Secondary concept: domain-specific measure from wim or step_desc (not author names)
    secondary_concept = _extract_mechanism_term(wim, step_desc, primary_concept)
    secondary_synonyms = get_synonyms(vocab, secondary_concept, max_synonyms=2)
    # Don't repeat primary in secondary
    if secondary_concept == primary_concept:
        secondary_synonyms = []

    # Architectural condition: prefer step_desc, but fall back to template_name
    # when step_desc yields a thin phrase (e.g. "Channel 6" → just "channel").
    arch_phrase = _extract_arch_phrase(step_desc)
    if len(arch_phrase.split()) < 2:
        arch_phrase = _extract_arch_phrase(template_name)

    # Determine boolean pattern
    if gap_type == "DIRECTION":
        boolean_pattern = "direction_conflict"
    elif gap.get("param_name"):
        boolean_pattern = "parameter_calibration"
    elif gap.get("what_is_missing_quality") == "low":
        boolean_pattern = "bridge_mechanism"
    else:
        boolean_pattern = "standard"

    # Build AST
    groups = []

    # Core: primary mechanism term + synonyms
    if len(set(primary_synonyms)) > 1:
        groups.append(OrGroup(sorted(primary_synonyms), priority="core"))
    else:
        groups.append(ExactPhrase(primary_concept, priority="core"))

    # Core: secondary concept (the specific measure)
    if secondary_concept != primary_concept and secondary_synonyms:
        groups.append(OrGroup(sorted(secondary_synonyms), priority="core"))

    # Supporting: architectural condition
    if arch_phrase:
        groups.append(ExactPhrase(arch_phrase, priority="supporting"))

    # Exclusions (optional)
    if total_n <= 50 and corpus_coverage != "sparse":
        groups.append(Exclusion("review"))

    ag = AndGroup(groups)
    serialized, was_truncated = ag.drop_to_limit(256)

    # Validate
    errors = ag.validate(serialized)
    if errors:
        # Re-derive from minimal core
        core_groups = [g for g in groups if getattr(g, "priority", None) == "core"]
        ag_min = AndGroup(core_groups[:2])
        serialized = ag_min.serialize()
        was_truncated = True

    return {
        "query": serialized,
        "pattern": boolean_pattern,
        "truncated": was_truncated,
    }


STOPWORDS = {"as", "a", "the", "of", "and", "in", "to", "for", "with", "from", "by", "on", "an"}


_TEMPLATE_ARTIFACTS = re.compile(
    r"(→|▶|•|\[[\w/]+\]|:\s*$|\bstep\s*\d+\b|\bcb/\w+\b|\bpp/\w+\b)",
    re.IGNORECASE,
)


def _extract_arch_phrase(text: str) -> str:
    """Extract a clean 4-word content phrase; strip template formatting first."""
    if not text:
        return ""
    # First non-arrow sentence/line only
    lines = [ln.strip() for ln in re.split(r"[;\n]", text) if ln.strip()]
    clean = lines[0] if lines else text
    # Truncate at first colon — content after colons is usually math, sub-labels,
    # or jargon that doesn't search well. The label before the colon is the searchable term.
    if ":" in clean:
        clean = clean.split(":", 1)[0]
    # Strip arrow/bracket formatting artifacts
    clean = _TEMPLATE_ARTIFACTS.sub(" ", clean)
    # Strip residual leading punctuation
    clean = re.sub(r"^[\s→▶•:]+", "", clean).strip()
    # Drop any token containing math/symbol fragments (slashes, parens, plus signs)
    words = [w for w in clean.split() if re.match(r"^[a-zA-Z][a-zA-Z\-]*$", w)]
    content_words = [w for w in words if w.lower() not in STOPWORDS][:4]
    return " ".join(content_words).lower() if content_words else ""


# Author name fragments to exclude from Boolean mechanism extraction
_AUTHOR_FRAGMENTS = {
    "holl", "hillier", "ellard", "foster", "lewy", "daw", "gottlieb",
    "oudeyer", "lopes", "bunzeck", "duzel", "gopnik", "grossman",
    "meilinger", "kuliga", "baranes",
}

# Discourse verbs that appear at the start of rebuttal/wim text but are not
# mechanism terms (e.g. "The claim would fail if...", "Hillier contested...")
_DISCOURSE_WORDS = {
    "claim", "claims", "claimed", "would", "fails", "fail", "argue", "argues", "argued",
    "contested", "challenged", "challenge", "contend", "contends", "suggests", "suggest",
    "proposed", "proposes", "assert", "asserts", "stated", "states", "notes", "noted",
    "shows", "found", "finding", "finding", "demonstrate", "demonstrates",
    "question", "questions", "doubt", "doubts", "refute", "refutes",
    "template", "panel", "debate", "account", "model", "theory", "effect",
    "could", "might", "should", "cannot", "likely", "unlikely",
    "entire", "framing", "primary", "primarily", "purely", "minimal", "rarely",
    "indoor", "outdoor", "subject", "subjects", "people", "person", "humans",
}


def _extract_mechanism_term(wim: str, step_desc: str, fallback: str) -> str:
    text = (wim or step_desc or "").lower()
    # Prefer domain-specific measurement tokens first (most reliable)
    for term in DOMAIN_SPECIFIC_MECHANISM:
        if re.search(r"\b" + re.escape(term) + r"\b", text):
            return term
    # Fall back to first non-stopword content word, skipping author names and
    # discourse words that appear at the opening of rebuttal-text fragments
    words = [
        w for w in re.findall(r"[a-z]+", text)
        if w not in STOPWORDS
        and w not in _AUTHOR_FRAGMENTS
        and w not in _DISCOURSE_WORDS
        and len(w) > 4
    ]
    if words:
        return words[0]
    return fallback


# ---------------------------------------------------------------------------
# Signals computation
# ---------------------------------------------------------------------------

def compute_ai_signals(query: str, truncated: bool, trimmed: bool) -> dict:
    low = query.lower()
    scc = count_structural_components(query)
    char_len = len(query)
    ends_q = query.strip().endswith("?")
    has_anchor = bool(any(re.search(r"\b" + re.escape(a) + r"\b", low) for a in ANCHOR_PHRASES))
    has_ev = bool(any(re.search(p, low) for p in EVIDENCE_OPENERS))
    has_pop = bool(POPULATION_REGEX.search(low))
    passes = char_len >= 60 and char_len <= 500 and ends_q and scc >= 3
    return {
        "char_length": char_len,
        "ends_with_question": ends_q,
        "has_theoretical_anchor": has_anchor,
        "has_evidence_type": has_ev,
        "has_population": has_pop,
        "structural_component_count": scc,
        "truncated": truncated,
        "trimmed_clause": trimmed,
        "passes_minimum": passes,
    }


def compute_bool_signals(query: str, truncated: bool) -> dict:
    has_phrase = bool(re.search(r'"[^"]+"', query))
    has_and = "AND" in query
    has_or = bool(re.search(r"\([^)]+\bOR\b[^)]+\)", query))
    is_bare = not has_phrase and not has_and
    char_len = len(query)
    over_limit = char_len > 256
    passes = has_phrase and has_and and not is_bare and not over_limit
    return {
        "has_exact_phrase": has_phrase,
        "has_and_operator": has_and,
        "has_or_group": has_or,
        "is_bare_word_list": is_bare,
        "char_length": char_len,
        "over_api_limit": over_limit,
        "truncated": truncated,
        "passes_minimum": passes,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_gap(gap: dict, vocab: dict) -> dict:
    ai = build_ai_citation(gap)
    bl = build_boolean(gap, vocab)

    ai_signals = compute_ai_signals(ai["query"], ai["truncated"], ai["trimmed_clause"])
    bool_signals = compute_bool_signals(bl["query"], bl["truncated"])

    pattern_map = {
        "C": "direction_fallback", "F": "direction_conflict",
        "E": "mechanism", "D": "mechanism",
        "B": "validation", "A": "boundary",
    }

    return {
        "template_id":                   gap.get("template_id", ""),
        "display_id":                    gap.get("display_id", ""),
        "step_number":                   gap.get("step_number"),
        "param_name":                    gap.get("param_name"),
        "primary_gap_type":              gap.get("primary_gap_type"),
        "voi_score":                     gap.get("voi_score"),
        "corpus_coverage":               gap.get("corpus_coverage"),
        "depth_tier":                    gap.get("depth_tier"),

        "ai_citation_query":             ai["query"],
        "ai_citation_pattern":           ai["pattern"],
        "ai_citation_composed_from":     ai["composed_from"],
        "ai_citation_generation_mode":   ai["generation_mode"],
        "ai_citation_semantic_confidence": ai["semantic_confidence"],
        "ai_citation_truncated":         ai["truncated"],
        "ai_citation_trimmed_clause":    ai["trimmed_clause"],
        "direction_account_b_source":    ai["direction_account_b_source"],
        "direction_fallback":            ai.get("direction_fallback", False),
        "ai_citation_signals":           ai_signals,

        "boolean_query":                 bl["query"],
        "boolean_pattern":               bl["pattern"],
        "boolean_truncated":             bl["truncated"],
        "boolean_signals":               bool_signals,

        "query_rationale":               _rationale(gap, ai["pattern"], bl["truncated"]),
        "manual_test_result":            None,
        "manual_test_date":              None,
    }


def _rationale(gap: dict, pattern: str, bool_truncated: bool) -> str:
    gtype = gap.get("primary_gap_type", "?")
    did = gap.get("display_id", "?")
    step = gap.get("step_number", "param")
    fws = gap.get("t1_frameworks", [])
    note = ""
    if bool_truncated:
        note = " Boolean truncated to fit 256-char API limit."
    return (
        f"{gtype} gap in {did} step {step} (frameworks: {','.join(fws)}). "
        f"Pattern {pattern} selected per gap→pattern mapping.{note}"
    )


def main():
    parser = argparse.ArgumentParser(description="Phase 3 Query Generator")
    parser.add_argument("--gaps", default="gap_report.json")
    parser.add_argument("--output", default="query_pairs.json")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--vocab", default=None)
    parser.add_argument("--min-quality", default="low", choices=["low", "medium", "high"])
    args = parser.parse_args()

    # Load gaps
    with open(args.gaps) as f:
        gap_data = json.load(f)

    schema_ver = gap_data.get("metadata", {}).get("schema_version", "")
    if not schema_ver.startswith(COMPATIBLE_GAP_SCHEMA_PREFIX):
        sys.exit(f"ERROR: incompatible gap_report schema '{schema_ver}' (expected 3.x.x)")

    gaps = gap_data["gaps"]

    # Quality filter
    QUALITY_RANK = {"low": 0, "medium": 1, "high": 2}
    min_q = QUALITY_RANK[args.min_quality]
    gaps = [g for g in gaps if QUALITY_RANK.get(g.get("what_is_missing_quality", "low"), 0) >= min_q]

    # Selection
    if not args.all:
        gaps = gaps[: args.top_n]

    # Vocabulary
    vocab_path = args.vocab or str(
        Path(__file__).parent.parent.parent / "Article_Eater/contracts/vocab/cross_field_vocabulary.yaml"
    )
    vocab, vocab_hash = load_vocabulary(vocab_path)

    # Generate
    query_pairs = []
    pattern_dist: dict[str, int] = {}
    fallback_count = 0

    for gap in gaps:
        pair = process_gap(gap, vocab)
        query_pairs.append(pair)
        pat = pair["ai_citation_pattern"]
        pattern_dist[pat] = pattern_dist.get(pat, 0) + 1
        if pair["ai_citation_composed_from"] == "template_name_fallback":
            fallback_count += 1

    ai_pass = sum(1 for p in query_pairs if p["ai_citation_signals"]["passes_minimum"])
    bool_pass = sum(1 for p in query_pairs if p["boolean_signals"]["passes_minimum"])
    n = len(query_pairs)

    output = {
        "metadata": {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_gap_report": args.gaps,
            "source_schema_version": schema_ver,
            "gaps_processed": n,
            "ai_citation_pass_rate": round(ai_pass / n, 3) if n else 0,
            "boolean_pass_rate": round(bool_pass / n, 3) if n else 0,
            "fallback_composition_count": fallback_count,
            "pattern_distribution": pattern_dist,
            "vocabulary_source": vocab_path,
            "vocabulary_hash": vocab_hash,
        },
        "query_pairs": query_pairs,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Verification-time vocabulary_hash assertion (SC-8 reinforcement):
    # The hash stored in metadata MUST equal the hash recomputed from the same
    # vocab state at write time. If these diverge, vocabulary state mutated
    # between generation and write (e.g. lazy synonym expansion). Fail loudly.
    with open(args.output) as f:
        readback = json.load(f)
    recomputed_hash = _hash_vocab(vocab)
    stored_hash = readback["metadata"]["vocabulary_hash"]
    assert stored_hash == recomputed_hash, (
        f"vocabulary_hash mismatch at verification: "
        f"stored={stored_hash[:24]}... recomputed={recomputed_hash[:24]}..."
    )

    print(f"Wrote {n} query pairs → {args.output}")
    print(f"AI Citation pass rate: {ai_pass}/{n} ({100*ai_pass//n if n else 0}%)")
    print(f"Boolean pass rate:     {bool_pass}/{n} ({100*bool_pass//n if n else 0}%)")
    print(f"Pattern distribution:  {pattern_dist}")
    print(f"Fallback queries:      {fallback_count}")
    print(f"Vocabulary hash:       {vocab_hash[:32]}…  (verification ok)")


if __name__ == "__main__":
    main()
