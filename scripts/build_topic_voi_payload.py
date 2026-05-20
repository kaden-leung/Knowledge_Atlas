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
        "label": "Better measures",
        "question": "Would better measures or instruments materially improve the evidence?",
        "kind": "methodological_upgrade",
    },
    "target_3_better_design": {
        "label": "Better design",
        "question": "Would a stronger causal, comparative, longitudinal, or meta-analytic design change the claim?",
        "kind": "methodological_upgrade",
    },
    "target_4_deconfounding": {
        "label": "Deconfounding",
        "question": "Would separating confounded independent or dependent variables change the interpretation?",
        "kind": "methodological_upgrade",
    },
    "target_5_mechanism_weak_links": {
        "label": "Mechanism weak links",
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
        "label": "WEIRD extension",
        "question": "Would non-WEIRD or cross-cultural samples change the claim's scope?",
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
    return max(0.0, min(1.0, round(float(value), 3)))


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


def _coverage_confidence(article_count: int, details_count: int, membership_count: int) -> dict[str, Any]:
    if article_count == 0:
        return {"rating": "low", "score": 0.0, "basis": "No articles are attached to this topic."}
    detail_ratio = details_count / article_count
    membership_bonus = 0.1 if membership_count else 0.0
    score = clamp(min(1.0, detail_ratio * 0.8 + membership_bonus))
    return {
        "rating": rating(score),
        "score": score,
        "basis": f"{details_count}/{article_count} topic papers have article-detail records; membership rows available: {membership_count}.",
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


def build_article_finder_query(topic: dict[str, Any], target_id: str, known_papers: list[str]) -> dict[str, Any]:
    target = TARGET_DEFINITIONS[target_id]
    terms = _query_terms(topic, target_id)
    topic_phrase = terms[0]
    require_terms = terms[-3:]
    boolean_parts = [f'"{topic_phrase}"']
    boolean_parts.extend(f'"{term}"' for term in require_terms)
    boolean_query = " AND ".join(boolean_parts)
    natural = f"Find recent studies on {topic_phrase} that address {target['label'].lower()} for this topic. Prioritize reviews, replications, severe tests, and papers not already in the Knowledge Atlas corpus."
    internal_query = " ".join([topic_phrase, target["label"], *require_terms])
    return {
        "natural_language_query": natural,
        "boolean_query": boolean_query,
        "structured_query": {
            "topic_id": topic.get("id"),
            "target_id": target_id,
            "include_terms": terms,
            "require_terms": require_terms,
            "exclude_known_papers": known_papers[:80],
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

    raw_scores = {
        "target_1_better_stimuli": clamp(
            (0.35 if article_count < 6 else 0.12)
            + (0.25 if not has_stimulus_terms else 0.08)
            + (0.20 if "emerging" in maturity else 0.08)
            + min(0.2, max(0, 8 - article_count) * 0.025)
        ),
        "target_2_better_measures": clamp(
            (0.35 if sensor_count == 0 else 0.08)
            + (0.25 if measurement_count < max(2, article_count // 2) else 0.1)
            + (0.18 if instrument_count < max(3, article_count) else 0.05)
            + (0.12 if "self_report_scale" in instruments["instrument_type_counts"] else 0.0)
        ),
        "target_3_better_design": clamp(
            (0.28 if empirical_ratio < 0.65 else 0.08)
            + (0.2 if review_ratio > 0.25 else 0.0)
            + (0.18 if article_count < 5 else 0.05)
            + (0.16 if contradiction_count else 0.0)
        ),
        "target_4_deconfounding": clamp(
            (0.35 if has_confound_terms else 0.12)
            + (0.22 if contradiction_count else 0.0)
            + (0.16 if theory_count >= 2 else 0.0)
            + (0.12 if construct_count >= 2 else 0.0)
        ),
        "target_5_mechanism_weak_links": clamp(
            (0.32 if pnus["weak_or_incomplete_pnu_count"] else 0.12)
            + (0.22 if pnus["mentions_mechanism_gap"] else 0.05)
            + (0.18 if pnus["pnu_count"] < article_count else 0.0)
            + (0.12 if theory_count else 0.0)
        ),
        "target_6_boundary_conditions": clamp(
            (0.28 if samples["known_sample_count"] < max(1, article_count // 2) else 0.08)
            + (0.18 if samples["median_sample_n"] and samples["median_sample_n"] < 50 else 0.0)
            + (0.16 if not samples["has_weird_extension_terms"] else 0.04)
            + (0.12 if article_count < 8 else 0.04)
        ),
        "target_7_theory_discrimination": clamp(
            (0.34 if theory_count >= 2 else 0.08)
            + (0.24 if has_theory_contest else 0.0)
            + (0.18 if contradiction_count else 0.0)
            + (0.08 if "framework" in joined or "theory" in joined else 0.0)
        ),
        "target_8_replication_priority": clamp(
            (0.36 if article_count > 0 and replication_count == 0 else 0.08)
            + (0.22 if mean_credence >= 0.65 else 0.08)
            + (0.16 if article_count < 6 else 0.06)
            + (0.12 if contradiction_count else 0.0)
        ),
        "target_9_design_translation": clamp(
            (0.28 if has_design_implications else 0.12)
            + (0.18 if sensor_count or measurement_count else 0.0)
            + (0.16 if any(term in joined for term in ("building", "architecture", "design", "workspace", "classroom")) else 0.05)
            + (0.12 if article_count >= 3 else 0.04)
        ),
        "target_10_weird_extension": clamp(
            (0.36 if not samples["has_weird_extension_terms"] else 0.08)
            + (0.16 if samples["has_student_terms"] else 0.04)
            + (0.12 if samples["known_sample_count"] else 0.0)
            + (0.10 if article_count >= 3 else 0.05)
        ),
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

    shared_signals = {
        "article_count": article_count,
        "article_type_counts": dict(types),
        "instrument_signals": instruments,
        "sample_signals": samples,
        "pnu_signals": pnus,
        "theory_count": theory_count,
        "construct_count": construct_count,
        "contradiction_count": contradiction_count,
        "replication_count": replication_count,
        "question_hits": question_hits,
        "membership_count": len(membership_rows),
    }

    vector = {}
    for target_id, score in raw_scores.items():
        query = build_article_finder_query(topic, target_id, known_papers)
        vector[target_id] = {
            "target_id": target_id,
            "label": TARGET_DEFINITIONS[target_id]["label"],
            "rating": rating(score),
            "score": score,
            "basis": basis_by_target[target_id],
            "method_status": METHOD_STATUS,
            "evidence_signals": shared_signals,
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
    for row in memberships_payload if isinstance(memberships_payload, list) else memberships_payload.get("memberships", []):
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
        question_hits = _topic_question_hits(topic, questions_payload.get("questions") or [], gaps_payload.get("gaps") or [])
        vector = build_target_vector(topic, articles, details, memberships_by_topic.get(str(topic.get("id")), []), question_hits)
        ranked = sorted(vector.values(), key=lambda row: row["score"], reverse=True)
        output_topics.append(
            {
                "topic_id": topic.get("id"),
                "topic_name": topic.get("name"),
                "category": topic.get("cat"),
                "article_count": len(articles),
                "paper_ids": paper_ids,
                "method_status": METHOD_STATUS,
                "coverage_confidence": _coverage_confidence(len(articles), details_present_count, len(memberships_by_topic.get(str(topic.get("id")), []))),
                "target_vector": vector,
                "top_targets": [
                    {
                        "target_id": row["target_id"],
                        "label": row["label"],
                        "rating": row["rating"],
                        "score": row["score"],
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
            "implementation_basis": "Codex synthesis from CW-simulated panel and published expert positions",
            "real_panel_prompt": "docs/VOI_REAL_PANEL_PROMPT_2026-05-19.md",
            "implementation_synthesis": "docs/VOI_PANEL_IMPLEMENTATION_SYNTHESIS_2026-05-19.md",
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
