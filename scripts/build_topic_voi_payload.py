#!/usr/bin/env python3
"""Build per-topic VOI profiles for the Knowledge Atlas.

This is not a formal expected-value-of-information engine. It is a
contract-backed provisional profile builder that turns existing corpus signals
into auditable target ratings and article-finder queries.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import quote_plus


REPO_ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_DIR = REPO_ROOT / "data" / "ka_payloads"
DEFAULT_OUTPUT = PAYLOAD_DIR / "topic_voi.json"
CONTRACT_ID = "TOPIC_VOI_PROFILE_CONTRACT_2026-05-19"
METHOD_STATUS = "provisional_profile"
SCORE_SEMANTICS = "heuristic_routing_only_not_expected_value"
FORMULA_VERSION = "topic_voi_profile_2026_05_19_panel_hardened_v2"
PUBLIC_PANEL_DISCLAIMER = "AI-simulated expert review only; not reviewed by the named human panel."
PUBLIC_WARNING = (
    "These ratings are provisional routing judgments. They are not formal expected-value calculations "
    "and must not be read as settled expert consensus."
)
DECISION_CONTEXT_ABSENT = True

STUDENT_TARGETS = [
    "target_1_better_stimuli",
    "target_2_better_measures",
    "target_4_deconfounding",
    "target_8_replication_priority",
]

TARGET_DEFINITIONS: dict[str, dict[str, str]] = {
    "target_1_better_stimuli": {
        "label": "Better stimuli",
        "question": "Would better or more ecological stimuli teach us more about this topic?",
        "kind": "methodological_upgrade",
    },
    "target_2_better_measures": {
        "label": "Construct and measurement quality",
        "question": "Would sharper construct definition, operationalization, reliability, validity, or invariance checks materially improve the evidence?",
        "kind": "methodological_upgrade",
    },
    "target_3_better_design": {
        "label": "Causal or severe design",
        "question": "Would a stronger causal, comparative, longitudinal, or meta-analytic design change the claim?",
        "kind": "methodological_upgrade",
    },
    "target_4_deconfounding": {
        "label": "Deconfounding",
        "question": "Would separating confounded independent or dependent variables change the interpretation?",
        "kind": "methodological_upgrade",
    },
    "target_5_mechanism_weak_links": {
        "label": "Mechanism-link uncertainty",
        "question": "Would direct measurement of a weak mechanism or PNU link improve the web of belief?",
        "kind": "mechanism",
    },
    "target_6_boundary_conditions": {
        "label": "Boundary conditions",
        "question": "Would testing scope, population, setting, dose, or timing boundaries change the claim?",
        "kind": "scope",
    },
    "target_7_theory_discrimination": {
        "label": "Theory discrimination",
        "question": "Would this topic support a severe test between competing theories or frameworks?",
        "kind": "theory",
    },
    "target_8_replication_priority": {
        "label": "Replication priority",
        "question": "Would replication or meta-analysis reduce uncertainty about important claims?",
        "kind": "coverage_gap",
    },
    "target_9_design_translation": {
        "label": "Design translation",
        "question": "Would this topic benefit from translation into design-relevant conditions or guidance?",
        "kind": "practice_translation",
    },
    "target_10_weird_extension": {
        "label": "Cross-cultural and population scope",
        "question": "Would population, culture, language, recruitment, or measurement-invariance evidence change the claim's scope?",
        "kind": "coverage_gap",
    },
}

ARTICLE_TYPE_REVIEW_TERMS = ("review", "meta", "systematic")
WEIRD_EXTENSION_TERMS = (
    "non-weird",
    "non weird",
    "cross-cultural",
    "cross cultural",
    "culture",
    "cultural",
    "community sample",
    "older adults",
    "elderly",
    "children",
    "adolescent",
    "clinical",
    "non-oecd",
)
STIMULUS_TERMS = (
    "vr",
    "virtual reality",
    "immersive",
    "field",
    "ecological",
    "real-world",
    "real world",
    "in situ",
    "photograph",
    "video",
    "stimuli",
    "stimulus",
)
CONFOUND_TERMS = ("confound", "control", "controlled", "separate", "dissociation", "disentangle")
THEORY_CONTEST_TERMS = (" vs ", "versus", "competing", "distinguish", "discriminate", "rival")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_-]+", value or "")


def compact(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def clamp(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, round(float(value), 2)))


def rating(score: float, *, na: bool = False) -> str:
    if na:
        return "na"
    if score >= 0.7:
        return "high"
    if score >= 0.42:
        return "medium"
    return "low"


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    hay = text.lower()
    return any(term in hay for term in terms)


def _paper_text(article: dict[str, Any], detail: dict[str, Any]) -> str:
    science = detail.get("science_summary") or {}
    pnu = detail.get("pnu") or {}
    bits = [
        article.get("title"),
        article.get("abstract"),
        article.get("main_conclusion"),
        science.get("core_finding"),
        science.get("methods_and_design"),
        science.get("limitations"),
        science.get("gap_and_door"),
        pnu.get("short_summary"),
    ]
    return " ".join(str(bit or "") for bit in bits)


def _article_type_counts(articles: list[dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for article in articles:
        atype = str(article.get("article_type") or "unknown").lower()
        if any(term in atype for term in ARTICLE_TYPE_REVIEW_TERMS):
            counts["review_like"] += 1
        elif "empirical" in atype or "research" in atype or "experiment" in atype:
            counts["empirical"] += 1
        elif "replication" in atype:
            counts["replication"] += 1
        else:
            counts[atype or "unknown"] += 1
    return counts


def _instrument_signals(details: list[dict[str, Any]], articles: list[dict[str, Any]]) -> dict[str, Any]:
    instrument_types: Counter = Counter()
    sensor_count = 0
    measurement_count = 0
    instrument_count = 0
    for detail in details:
        op = detail.get("operationalization") or {}
        sensor_count += int(op.get("sensor_count") or 0)
        measurement_count += int(op.get("measurement_count") or 0)
        instrument_count += int(op.get("instrument_count") or 0)
        for row in op.get("instrument_inventory") or []:
            instrument_types[str(row.get("type") or "unknown")] += 1
        for row in op.get("measurement_inventory") or []:
            instrument_types[str(row.get("instrument_type") or "unknown")] += 1
    article_instruments = Counter()
    for article in articles:
        for name in article.get("instruments") or []:
            article_instruments[str(name)] += 1
    return {
        "sensor_count": sensor_count,
        "measurement_count": measurement_count,
        "instrument_count": instrument_count,
        "instrument_type_counts": dict(instrument_types.most_common(8)),
        "article_instruments": dict(article_instruments.most_common(8)),
    }


def _sample_signals(articles: list[dict[str, Any]], texts: list[str]) -> dict[str, Any]:
    sample_ns = []
    for article in articles:
        value = article.get("sample_n") or article.get("subject_count_total")
        try:
            if value is not None and float(value) > 0:
                sample_ns.append(float(value))
        except Exception:
            pass
    joined = " ".join(texts).lower()
    return {
        "known_sample_count": len(sample_ns),
        "median_sample_n": int(median(sample_ns)) if sample_ns else None,
        "has_weird_extension_terms": _contains_any(joined, WEIRD_EXTENSION_TERMS),
        "has_student_terms": any(term in joined for term in ("student", "undergraduate", "university")),
    }


def _pnu_signals(details: list[dict[str, Any]], texts: list[str]) -> dict[str, Any]:
    pnu_count = 0
    weak_count = 0
    for detail in details:
        pnu = detail.get("pnu") or {}
        if pnu.get("short_summary") or pnu.get("long_summary"):
            pnu_count += 1
        blob = " ".join(str(pnu.get(k) or "") for k in ("status", "short_status", "long_status", "short_summary", "long_summary")).lower()
        if any(term in blob for term in ("cannot yet explain", "weak", "stub", "not_applicable", "not applicable", "unclear")):
            weak_count += 1
    joined = " ".join(texts).lower()
    return {
        "pnu_count": pnu_count,
        "weak_or_incomplete_pnu_count": weak_count,
        "mentions_mechanism_gap": any(term in joined for term in ("mechanism", "pathway", "underlying", "neural", "autonomic")),
    }


def _topic_question_hits(topic: dict[str, Any], questions: list[dict[str, Any]], gaps: list[dict[str, Any]]) -> dict[str, list[str]]:
    hay_terms = [topic.get("name") or "", topic.get("id") or ""]
    hay_terms.extend(topic.get("shared_theories") or [])
    hay_terms.extend(topic.get("shared_constructs") or [])
    topic_terms = [term.lower() for phrase in hay_terms for term in words(phrase) if len(term) > 4]
    topic_terms = list(dict.fromkeys(topic_terms))[:12]
    hits: dict[str, list[str]] = {"questions": [], "gaps": []}
    for row in questions:
        blob = " ".join(str(row.get(k) or "") for k in ("question_text", "topic", "subtopic", "description"))
        lower = blob.lower()
        if any(term in lower for term in topic_terms):
            hits["questions"].append(compact(blob, 180))
    for row in gaps:
        blob = " ".join(str(row.get(k) or "") for k in ("title", "description", "whyMatters"))
        lower = blob.lower()
        if any(term in lower for term in topic_terms):
            hits["gaps"].append(compact(blob, 180))
    return {"questions": hits["questions"][:3], "gaps": hits["gaps"][:3]}


def _citation_context(articles: list[dict[str, Any]], details: list[dict[str, Any]]) -> dict[str, Any]:
    related = 0
    supporting = 0
    contradicting = 0
    for article in articles:
        related += len(article.get("related_papers") or [])
    for detail in details:
        arg = detail.get("argumentation") or {}
        supporting += len(arg.get("supporting_papers") or [])
        contradicting += len(arg.get("challenging_papers") or []) + len(arg.get("contradicting_papers") or [])
    total = related + supporting + contradicting
    return {
        "related_paper_count": related,
        "supporting_paper_count": supporting,
        "contradicting_paper_count": contradicting,
        "citation_edge_proxy_count": total,
        "citation_neighborhood_coverage": "present" if total else "not_extracted_or_empty",
    }


def _topic_graph_links(topic: dict[str, Any], membership_rows: list[dict[str, Any]], articles: list[dict[str, Any]]) -> dict[str, Any]:
    canonical_topic_ids: list[str] = []
    primary_topic_ids: list[str] = []
    iv_roots: list[str] = []
    dv_focuses: list[str] = []
    confidences: list[float] = []
    for row in membership_rows:
        for topic_id in row.get("topic_ids") or []:
            value = str(topic_id)
            if value and value not in canonical_topic_ids:
                canonical_topic_ids.append(value)
        primary = row.get("primary_topic_id")
        if primary and str(primary) not in primary_topic_ids:
            primary_topic_ids.append(str(primary))
        iv = row.get("iv_root") or row.get("iv_roots")
        if isinstance(iv, list):
            iv_roots.extend(str(item) for item in iv if item)
        elif iv:
            iv_roots.append(str(iv))
        dv = row.get("dv_focus") or row.get("dv_focuses")
        if isinstance(dv, list):
            dv_focuses.extend(str(item) for item in dv if item)
        elif dv:
            dv_focuses.append(str(dv))
        try:
            if row.get("confidence") is not None:
                confidences.append(float(row.get("confidence")))
        except Exception:
            pass
    article_ids = [str(row.get("paper_id")) for row in articles if row.get("paper_id")]
    return {
        "topic_id": topic.get("id"),
        "canonical_topic_ids": sorted(set(canonical_topic_ids)),
        "primary_topic_ids": sorted(set(primary_topic_ids)),
        "article_ids": article_ids,
        "iv_roots": sorted(set(iv_roots))[:20],
        "dv_focuses": sorted(set(dv_focuses))[:20],
        "membership_count": len(membership_rows),
        "membership_confidence_mean": round(sum(confidences) / len(confidences), 2) if confidences else None,
    }


def _coverage_confidence(
    article_count: int,
    details_count: int,
    membership_count: int,
    citation_context: dict[str, Any],
    doi_title_count: int,
    sample_extraction_count: int,
) -> dict[str, Any]:
    if article_count == 0:
        return {
            "rating": "low",
            "score": 0.0,
            "components": {
                "detail_coverage": 0.0,
                "membership_coverage": 0.0,
                "citation_coverage": 0.0,
                "doi_title_coverage": 0.0,
                "sample_extraction_coverage": 0.0,
            },
            "basis": "No articles are attached to this topic.",
        }
    detail_ratio = details_count / article_count
    membership_ratio = min(1.0, membership_count / article_count)
    citation_ratio = min(1.0, float(citation_context.get("citation_edge_proxy_count") or 0) / max(1, article_count))
    doi_title_ratio = doi_title_count / article_count
    sample_ratio = sample_extraction_count / article_count
    score = clamp(
        detail_ratio * 0.25
        + membership_ratio * 0.25
        + citation_ratio * 0.20
        + doi_title_ratio * 0.15
        + sample_ratio * 0.15
    )
    components = {
        "detail_coverage": clamp(detail_ratio),
        "membership_coverage": clamp(membership_ratio),
        "citation_coverage": clamp(citation_ratio),
        "doi_title_coverage": clamp(doi_title_ratio),
        "sample_extraction_coverage": clamp(sample_ratio),
    }
    return {
        "rating": rating(score),
        "score": score,
        "components": components,
        "basis": (
            f"{details_count}/{article_count} topic papers have article-detail records; "
            f"{membership_count} membership rows; {citation_context.get('citation_edge_proxy_count') or 0} citation-neighborhood proxies."
        ),
    }


def _query_terms(topic: dict[str, Any], target_id: str) -> list[str]:
    base = [topic.get("name") or topic.get("id") or "Knowledge Atlas topic"]
    base.extend((topic.get("shared_theories") or [])[:2])
    base.extend((topic.get("shared_constructs") or [])[:2])
    target_terms = {
        "target_1_better_stimuli": ["ecological stimuli", "virtual reality", "field experiment"],
        "target_2_better_measures": ["validated measure", "instrument reliability", "psychometrics"],
        "target_3_better_design": ["longitudinal", "randomized", "causal design"],
        "target_4_deconfounding": ["confound", "dissociation", "control condition"],
        "target_5_mechanism_weak_links": ["mechanism", "mediator", "neural pathway"],
        "target_6_boundary_conditions": ["moderator", "boundary condition", "dose response"],
        "target_7_theory_discrimination": ["competing theories", "crucial experiment", "theory test"],
        "target_8_replication_priority": ["replication", "meta-analysis", "registered report"],
        "target_9_design_translation": ["design guideline", "built environment intervention", "field study"],
        "target_10_weird_extension": ["cross-cultural", "non-WEIRD", "community sample"],
    }
    base.extend(target_terms[target_id])
    cleaned = []
    for term in base:
        text = compact(term, 80)
        if text and text.lower() not in {x.lower() for x in cleaned}:
            cleaned.append(text)
    return cleaned[:8]


def build_article_finder_query(
    topic: dict[str, Any],
    target_id: str,
    known_papers: list[dict[str, str]],
) -> dict[str, Any]:
    target = TARGET_DEFINITIONS[target_id]
    terms = _query_terms(topic, target_id)
    topic_phrase = terms[0]
    require_terms = terms[-3:]
    anchor_terms = [term for term in terms[1:5] if len(term.split()) <= 5] or [topic_phrase]
    broad_query = " OR ".join(f'"{term}"' for term in anchor_terms[:4])
    narrow_query = f"({broad_query}) AND (" + " OR ".join(f'"{term}"' for term in require_terms) + ")"
    boolean_query = narrow_query
    natural = (
        f"Find studies that could confirm or lower the priority of {target['label'].lower()} for "
        f"{topic_phrase}. Prefer papers that test the opportunity directly and are not already in the Atlas corpus."
    )
    internal_query = " ".join([topic_phrase, target["label"], *require_terms])
    known_work_terms = [
        row.get("title") or row.get("paper_id") or row.get("doi") or ""
        for row in known_papers[:12]
        if row.get("title") or row.get("paper_id") or row.get("doi")
    ]
    return {
        "natural_language_query": natural,
        "broad_query": broad_query,
        "narrow_query": narrow_query,
        "boolean_query": boolean_query,
        "known_work_terms": known_work_terms,
        "query_test": {
            "why_this_query_tests_opportunity": f"It searches for direct evidence bearing on whether {target['label'].lower()} remains an open topic-level opportunity.",
            "would_confirm_open": "Recent direct tests remain sparse, indirect, contradictory, or limited to the same population/design pattern.",
            "would_close_or_lower_priority": "Recent direct tests already address the measurement, mechanism, scope, replication, or design issue with adequate extraction provenance.",
        },
        "structured_query": {
            "topic_id": topic.get("id"),
            "target_id": target_id,
            "include_terms": terms,
            "require_terms": require_terms,
            "exclude_known_papers": known_papers[:80],
            "external_exclusion_terms": known_work_terms,
            "freshness_after_year": 2020,
            "candidate_sources": ["KA corpus search", "Google Scholar", "OpenAlex", "Semantic Scholar", "PubMed where applicable"],
        },
        "internal_search_url": "ka_search.html?q=" + quote_plus(internal_query),
    }


def build_target_vector(
    topic: dict[str, Any],
    articles: list[dict[str, Any]],
    details: list[dict[str, Any]],
    membership_rows: list[dict[str, Any]],
    question_hits: dict[str, list[str]],
) -> dict[str, Any]:
    article_count = len(articles)
    texts = [_paper_text(article, detail) for article, detail in zip(articles, details)]
    joined = " ".join(texts).lower()
    types = _article_type_counts(articles)
    instruments = _instrument_signals(details, articles)
    samples = _sample_signals(articles, texts)
    pnus = _pnu_signals(details, texts)
    known_papers = [str(pid) for pid in topic.get("paper_ids") or [] if str(pid)]
    theory_count = len(topic.get("shared_theories") or [])
    construct_count = len(topic.get("shared_constructs") or [])
    contradiction_count = int(topic.get("contradictions") or 0)
    replication_count = int(topic.get("replications") or 0)
    mean_credence = float(topic.get("mean_credence") or 0.0)
    maturity = str(topic.get("maturity") or "").lower()
    question_text = " ".join((question_hits.get("questions") or []) + (question_hits.get("gaps") or [])).lower()

    review_ratio = types["review_like"] / article_count if article_count else 0.0
    empirical_ratio = types["empirical"] / article_count if article_count else 0.0
    sensor_count = int(instruments["sensor_count"])
    measurement_count = int(instruments["measurement_count"])
    instrument_count = int(instruments["instrument_count"])
    has_stimulus_terms = _contains_any(joined, STIMULUS_TERMS)
    has_confound_terms = _contains_any(joined + " " + question_text, CONFOUND_TERMS)
    has_theory_contest = _contains_any((" " + topic.get("name", "") + " " + question_text).lower(), THEORY_CONTEST_TERMS)
    has_design_implications = any(
        (detail.get("science_summary") or {}).get("design_implications")
        for detail in details
    )
    has_construct_validity_terms = any(
        term in joined
        for term in ("construct validity", "reliability", "validated", "measurement invariance", "psychometric")
    )
    has_population_extraction = samples["has_weird_extension_terms"] or samples["has_student_terms"] or samples["known_sample_count"] > 0
    has_direct_mechanism_evidence = pnus["pnu_count"] and pnus["mentions_mechanism_gap"] and not pnus["weak_or_incomplete_pnu_count"]

    def c(name: str, raw_value: float | int | bool, weight: float) -> dict[str, Any]:
        raw = 1.0 if raw_value is True else 0.0 if raw_value is False else float(raw_value or 0)
        raw = max(0.0, min(1.0, raw))
        return {"name": name, "raw_value": round(raw, 2), "weight": weight, "contribution": clamp(raw * weight)}

    specs: dict[str, dict[str, Any]] = {
        "target_1_better_stimuli": {
            "components": [
                c("thin_topic_corpus", article_count < 6, 0.24),
                c("ecological_stimulus_gap", not has_stimulus_terms, 0.24),
                c("emerging_topic", "emerging" in maturity, 0.16),
                c("small_bundle_bonus", min(1.0, max(0, 8 - article_count) / 8), 0.12),
            ],
            "missing": [] if has_stimulus_terms else ["stimulus_ecology_not_directly_extracted"],
            "positive": ["stimulus terms visible"] if has_stimulus_terms else [],
            "negative": ["ecological/field/VR stimulus terms sparse"] if not has_stimulus_terms else [],
            "signal_strength": "indirect_keyword",
        },
        "target_2_better_measures": {
            "components": [
                c("measurement_inventory_sparse", measurement_count < max(2, article_count // 2), 0.24),
                c("instrument_inventory_sparse", instrument_count < max(3, article_count), 0.18),
                c("construct_validity_not_visible", not has_construct_validity_terms, 0.20),
                c("mono_method_risk", "self_report_scale" in instruments["instrument_type_counts"] and sensor_count == 0, 0.12),
            ],
            "missing": [
                "construct_definition_not_extracted",
                "operationalization_match_not_extracted",
                "reliability_validity_invariance_not_extracted",
            ] if not has_construct_validity_terms else [],
            "positive": ["measurement or instrument inventory present"] if measurement_count or instrument_count else [],
            "negative": ["construct-validity evidence not visible"] if not has_construct_validity_terms else [],
            "signal_strength": "indirect_keyword" if has_construct_validity_terms else "missing",
        },
        "target_3_better_design": {
            "components": [
                c("empirical_design_mix_weak", 1 - empirical_ratio, 0.22),
                c("review_heavy_topic", review_ratio > 0.25, 0.16),
                c("thin_primary_base", article_count < 5, 0.14),
                c("contradiction_present", contradiction_count > 0, 0.16),
            ],
            "missing": [] if empirical_ratio else ["direct_design_type_extraction_sparse"],
            "positive": [f"article type mix {dict(types)}"],
            "negative": ["no contradiction signal"] if not contradiction_count else [],
            "signal_strength": "topic_metadata",
        },
        "target_4_deconfounding": {
            "components": [
                c("confound_terms_visible", has_confound_terms, 0.26),
                c("contradiction_present", contradiction_count > 0, 0.18),
                c("multiple_theories", theory_count >= 2, 0.12),
                c("multiple_constructs", construct_count >= 2, 0.10),
            ],
            "missing": [] if has_confound_terms else ["iv_dv_confound_structure_not_extracted"],
            "positive": ["confound/control terms visible"] if has_confound_terms else [],
            "negative": ["no direct confound signal visible"] if not has_confound_terms else [],
            "signal_strength": "indirect_keyword" if has_confound_terms else "topic_metadata",
        },
        "target_5_mechanism_weak_links": {
            "components": [
                c("weak_or_incomplete_pnu", pnus["weak_or_incomplete_pnu_count"] > 0, 0.24),
                c("mechanism_gap_terms", pnus["mentions_mechanism_gap"], 0.16),
                c("pnu_coverage_gap", article_count > 0 and pnus["pnu_count"] < article_count, 0.14),
                c("theory_link_available", theory_count > 0, 0.08),
            ],
            "missing": [
                "level_of_analysis_map_not_extracted",
                "causal_link_observable_mediators_not_extracted",
            ] if not has_direct_mechanism_evidence else [],
            "positive": [f"{pnus['pnu_count']} PNU records visible"] if pnus["pnu_count"] else [],
            "negative": ["PNU summaries alone are not direct mechanism evidence"],
            "signal_strength": "indirect_keyword" if pnus["pnu_count"] else "missing",
        },
        "target_6_boundary_conditions": {
            "components": [
                c("sample_extraction_sparse", samples["known_sample_count"] < max(1, article_count // 2), 0.22),
                c("small_sample_visible", bool(samples["median_sample_n"] and samples["median_sample_n"] < 50), 0.14),
                c("scope_terms_sparse", not samples["has_weird_extension_terms"], 0.12),
                c("thin_topic_corpus", article_count < 8, 0.08),
            ],
            "missing": [] if samples["known_sample_count"] else ["population_scope_extraction_sparse"],
            "positive": [f"median sample N {samples['median_sample_n']}"] if samples["median_sample_n"] else [],
            "negative": ["population/scope terms sparse"] if not samples["has_weird_extension_terms"] else [],
            "signal_strength": "topic_metadata",
        },
        "target_7_theory_discrimination": {
            "components": [
                c("multiple_theories", theory_count >= 2, 0.20),
                c("theory_contest_terms", has_theory_contest, 0.18),
                c("contradiction_present", contradiction_count > 0, 0.16),
                c("theory_language_visible", "framework" in joined or "theory" in joined, 0.08),
            ],
            "missing": [] if has_theory_contest else ["rival_theory_test_not_extracted"],
            "positive": [f"{theory_count} linked theories"] if theory_count else [],
            "negative": ["no direct rival-theory test signal"] if not has_theory_contest else [],
            "signal_strength": "topic_metadata",
        },
        "target_8_replication_priority": {
            "components": [
                c("no_replication_recorded", article_count > 0 and replication_count == 0, 0.20),
                c("important_claim_credence", mean_credence >= 0.65, 0.14),
                c("thin_topic_corpus", article_count < 6, 0.10),
                c("contradiction_present", contradiction_count > 0, 0.14),
            ],
            "missing": [] if replication_count else ["independent_replication_status_not_extracted"],
            "positive": [f"{replication_count} replication records"] if replication_count else [],
            "negative": ["no independent replication record visible"] if article_count and not replication_count else [],
            "signal_strength": "topic_metadata",
        },
        "target_9_design_translation": {
            "components": [
                c("design_implication_text", has_design_implications, 0.20),
                c("measurement_tractability", bool(sensor_count or measurement_count), 0.10),
                c("built_environment_terms", any(term in joined for term in ("building", "architecture", "design", "workspace", "classroom")), 0.12),
                c("evidence_base_minimum", article_count >= 3, 0.08),
            ],
            "missing": [] if has_design_implications else ["actionable_design_translation_not_extracted"],
            "positive": ["design implication text present"] if has_design_implications else [],
            "negative": ["translation claim not directly extracted"] if not has_design_implications else [],
            "signal_strength": "direct_extracted" if has_design_implications else "topic_metadata",
        },
        "target_10_weird_extension": {
            "components": [
                c("cross_cultural_terms_absent", not samples["has_weird_extension_terms"], 0.16),
                c("student_terms_present", samples["has_student_terms"], 0.10),
                c("population_sample_extracted", samples["known_sample_count"] > 0, 0.06),
                c("topic_has_enough_papers_to_test_scope", article_count >= 3, 0.06),
            ],
            "missing": [
                "population_country_region_language_not_extracted",
                "recruitment_context_not_extracted",
                "measurement_invariance_not_extracted",
            ] if not has_population_extraction or not samples["has_weird_extension_terms"] else [],
            "positive": ["cross-cultural or population terms visible"] if samples["has_weird_extension_terms"] else [],
            "negative": ["cross-cultural scope cannot be inferred from missing keywords"],
            "signal_strength": "indirect_keyword" if samples["has_weird_extension_terms"] else "missing",
        },
    }

    raw_scores = {
        target_id: clamp(sum(row["contribution"] for row in spec["components"]))
        for target_id, spec in specs.items()
    }

    basis_by_target = {
        "target_1_better_stimuli": f"Stimulus opportunity is based on {article_count} papers, maturity '{maturity or 'unknown'}', and whether ecological/VR/field stimulus terms are already visible.",
        "target_2_better_measures": f"Measure opportunity is based on {measurement_count} measurement records, {instrument_count} instrument records, and {sensor_count} sensor records.",
        "target_3_better_design": f"Design opportunity is based on article-type mix: {dict(types)}.",
        "target_4_deconfounding": f"Deconfounding opportunity is based on confound/control terms, {contradiction_count} contradictions, {theory_count} theories, and {construct_count} constructs.",
        "target_5_mechanism_weak_links": f"Mechanism opportunity is based on {pnus['pnu_count']} PNU records and {pnus['weak_or_incomplete_pnu_count']} weak or incomplete PNU signals.",
        "target_6_boundary_conditions": f"Boundary opportunity is based on {samples['known_sample_count']} known sample-size records, median N {samples['median_sample_n']}, and population/scope terms.",
        "target_7_theory_discrimination": f"Theory-discrimination opportunity is based on {theory_count} linked theories, theory-contest terms, and contradictions.",
        "target_8_replication_priority": f"Replication opportunity is based on {replication_count} recorded replications, mean credence {mean_credence:.2f}, and topic size {article_count}.",
        "target_9_design_translation": f"Design-translation opportunity is based on design-implication text, measurement tractability, and built-environment terms.",
        "target_10_weird_extension": f"WEIRD-extension opportunity is based on population terms, student-sample terms, and sample-size extraction coverage.",
    }

    common_signals = {
        "article_count": article_count,
        "article_type_counts": dict(types),
        "theory_count": theory_count,
        "construct_count": construct_count,
        "contradiction_count": contradiction_count,
        "replication_count": replication_count,
        "question_hits": question_hits,
        "membership_count": len(membership_rows),
    }

    def target_confidence(target_id: str, spec: dict[str, Any]) -> dict[str, Any]:
        base_by_strength = {
            "direct_extracted": 0.74,
            "indirect_keyword": 0.52,
            "topic_metadata": 0.44,
            "missing": 0.24,
        }
        base = base_by_strength.get(spec["signal_strength"], 0.3)
        penalty = min(0.28, 0.07 * len(spec["missing"]))
        membership_bonus = 0.06 if membership_rows else 0.0
        confidence = clamp(base + membership_bonus - penalty)
        return {
            "rating": rating(confidence),
            "score": confidence,
            "basis": f"{target_id} uses {spec['signal_strength']} signals with {len(spec['missing'])} required signal gaps.",
        }

    vector = {}
    for target_id, score in raw_scores.items():
        spec = specs[target_id]
        target_specific_signals = {
            **common_signals,
            "instrument_signals": instruments if target_id == "target_2_better_measures" else {},
            "sample_signals": samples if target_id in {"target_6_boundary_conditions", "target_10_weird_extension"} else {},
            "pnu_signals": pnus if target_id == "target_5_mechanism_weak_links" else {},
        }
        known_papers = [
            {
                "paper_id": str(article.get("paper_id") or ""),
                "title": compact(article.get("title") or "", 120),
                "doi": str(article.get("doi") or ""),
            }
            for article in articles
            if article.get("paper_id")
        ]
        query = build_article_finder_query(topic, target_id, known_papers)
        confidence = target_confidence(target_id, spec)
        vector[target_id] = {
            "target_id": target_id,
            "label": TARGET_DEFINITIONS[target_id]["label"],
            "rating": rating(score),
            "score": score,
            "routing_score": score,
            "score_semantics": SCORE_SEMANTICS,
            "score_formula_version": FORMULA_VERSION,
            "score_components": spec["components"],
            "basis": basis_by_target[target_id],
            "method_status": METHOD_STATUS,
            "decision_context_absent": DECISION_CONTEXT_ABSENT,
            "target_confidence": confidence,
            "target_coverage_confidence": confidence,
            "signal_strength": spec["signal_strength"],
            "positive_signals": spec["positive"],
            "negative_signals": spec["negative"],
            "missing_required_signals": spec["missing"],
            "missing_evidence_flags": spec["missing"],
            "value_context": "Scientific routing and design-relevance triage; no utility model has been specified.",
            "stakeholder_scope": "KA researchers, students, and article-finder workers using topic pages to decide what to inspect next.",
            "possible_value_conflict": "A topic may be useful to designers while still weak as causal evidence; usefulness must not be confused with truth.",
            "evidence_signals": target_specific_signals,
            "article_finder_query": query,
            "internal_search_url": query["internal_search_url"],
        }
    return vector


def build_payload(payload_dir: Path = PAYLOAD_DIR) -> dict[str, Any]:
    topics_payload = load_json(payload_dir / "topics.json", {"topics": []})
    articles_payload = load_json(payload_dir / "articles.json", {"articles": []})
    details_payload = load_json(payload_dir / "article_details.json", {"details": {}})
    memberships_payload = load_json(payload_dir / "topic_memberships.json", [])
    questions_payload = load_json(payload_dir / "question_bank.json", {"questions": []})
    gaps_payload = load_json(payload_dir / "gaps.json", {"gaps": []})

    topics = topics_payload.get("topics") or []
    articles_by_id = {str(row.get("paper_id")): row for row in (articles_payload.get("articles") or []) if row.get("paper_id")}
    details_by_id = details_payload.get("details") or {}
    memberships_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    memberships_by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
    membership_source = memberships_payload if isinstance(memberships_payload, list) else memberships_payload.get("memberships", [])
    for row in memberships_payload if isinstance(memberships_payload, list) else memberships_payload.get("memberships", []):
        if row.get("paper_id"):
            memberships_by_paper[str(row.get("paper_id"))].append(row)
        for topic_id in row.get("topic_ids") or []:
            memberships_by_topic[str(topic_id)].append(row)

    output_topics = []
    for topic in topics:
        paper_ids = [str(pid) for pid in topic.get("paper_ids") or [] if str(pid)]
        if not paper_ids:
            paper_ids = [str(row.get("paper_id")) for row in memberships_by_topic.get(str(topic.get("id")), []) if row.get("paper_id")]
        articles = [articles_by_id[pid] for pid in paper_ids if pid in articles_by_id]
        details = [details_by_id.get(pid, {}) for pid in paper_ids if pid in articles_by_id]
        details_present_count = sum(1 for row in details if row)
        topic_membership_rows: list[dict[str, Any]] = list(memberships_by_topic.get(str(topic.get("id")), []))
        for pid in paper_ids:
            topic_membership_rows.extend(memberships_by_paper.get(pid, []))
        deduped_memberships = {}
        for row in topic_membership_rows:
            key = (str(row.get("paper_id") or ""), tuple(str(item) for item in row.get("topic_ids") or []))
            deduped_memberships[key] = row
        topic_membership_rows = list(deduped_memberships.values())
        citation_context = _citation_context(articles, details)
        topic_graph_links = _topic_graph_links(topic, topic_membership_rows, articles)
        doi_title_count = sum(1 for article in articles if article.get("title") or article.get("doi"))
        sample_extraction_count = sum(
            1
            for article in articles
            if article.get("sample_n") or article.get("subject_count_total")
        )
        question_hits = _topic_question_hits(topic, questions_payload.get("questions") or [], gaps_payload.get("gaps") or [])
        vector = build_target_vector(topic, articles, details, topic_membership_rows, question_hits)
        ranked = sorted(vector.values(), key=lambda row: row["score"], reverse=True)
        output_topics.append(
            {
                "topic_id": topic.get("id"),
                "topic_name": topic.get("name"),
                "category": topic.get("cat"),
                "article_count": len(articles),
                "paper_ids": paper_ids,
                "method_status": METHOD_STATUS,
                "score_semantics": SCORE_SEMANTICS,
                "decision_context_absent": DECISION_CONTEXT_ABSENT,
                "panel_disclaimer": PUBLIC_PANEL_DISCLAIMER,
                "public_warning": PUBLIC_WARNING,
                "coverage_confidence": _coverage_confidence(
                    len(articles),
                    details_present_count,
                    len(topic_membership_rows),
                    citation_context,
                    doi_title_count,
                    sample_extraction_count,
                ),
                "topic_graph_links": topic_graph_links,
                "citation_context": citation_context,
                "target_vector": vector,
                "top_targets": [
                    {
                        "target_id": row["target_id"],
                        "label": row["label"],
                        "rating": row["rating"],
                        "score": row["score"],
                        "routing_score": row["routing_score"],
                        "score_semantics": row["score_semantics"],
                        "target_confidence": row["target_confidence"],
                        "basis": row["basis"],
                        "internal_search_url": row["internal_search_url"],
                    }
                    for row in ranked[:4]
                ],
                "student_projection": [vector[target_id] for target_id in STUDENT_TARGETS],
                "researcher_projection": ranked,
            }
        )

    return {
        "contract_id": CONTRACT_ID,
        "method_status": METHOD_STATUS,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "source_payloads": {
            "topics": "data/ka_payloads/topics.json",
            "articles": "data/ka_payloads/articles.json",
            "article_details": "data/ka_payloads/article_details.json",
            "topic_memberships": "data/ka_payloads/topic_memberships.json",
            "question_bank": "data/ka_payloads/question_bank.json",
            "gaps": "data/ka_payloads/gaps.json",
        },
        "panel_status": {
            "real_human_panel_completed": False,
            "implementation_basis": "Codex AI-simulated expert panel synthesis; not a real human panel",
            "real_panel_prompt": "docs/VOI_REAL_PANEL_PROMPT_2026-05-19.md",
            "implementation_synthesis": "docs/VOI_PANEL_IMPLEMENTATION_SYNTHESIS_2026-05-19.md",
        },
        "panel_disclaimer": PUBLIC_PANEL_DISCLAIMER,
        "public_warning": PUBLIC_WARNING,
        "score_semantics": SCORE_SEMANTICS,
        "score_formula_version": FORMULA_VERSION,
        "decision_context_absent": DECISION_CONTEXT_ABSENT,
        "corpus_snapshot": {
            "topic_count": len(topics),
            "article_count": len(articles_by_id),
            "detail_count": len(details_by_id),
            "membership_count": len(membership_source),
            "search_index_present": (payload_dir / "search_index.json").exists(),
            "citation_edge_proxy_count": sum((row.get("citation_context") or {}).get("citation_edge_proxy_count") or 0 for row in output_topics),
        },
        "target_definitions": TARGET_DEFINITIONS,
        "student_default_targets": STUDENT_TARGETS,
        "topics": output_topics,
        "summary": {
            "topic_count": len(output_topics),
            "target_count": len(TARGET_DEFINITIONS),
            "high_target_count": sum(
                1
                for topic in output_topics
                for row in topic["target_vector"].values()
                if row["rating"] == "high"
            ),
            "medium_target_count": sum(
                1
                for topic in output_topics
                for row in topic["target_vector"].values()
                if row["rating"] == "medium"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-dir", default=str(PAYLOAD_DIR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = build_payload(Path(args.payload_dir))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {output} with {payload['summary']['topic_count']} topic VOI profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
