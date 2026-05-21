#!/usr/bin/env python3
"""Verify topic VOI payload compliance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAYLOAD = REPO_ROOT / "data" / "ka_payloads" / "topic_voi.json"
TOPICS_PAYLOAD = REPO_ROOT / "data" / "ka_payloads" / "topics.json"
REQUIRED_CONTRACT = "TOPIC_VOI_PROFILE_CONTRACT_2026-05-19"
REQUIRED_METHOD_STATUS = "provisional_profile"
REQUIRED_SCORE_SEMANTICS = "heuristic_routing_only_not_expected_value"
REQUIRED_TARGETS = {
    "target_1_better_stimuli",
    "target_2_better_measures",
    "target_3_better_design",
    "target_4_deconfounding",
    "target_5_mechanism_weak_links",
    "target_6_boundary_conditions",
    "target_7_theory_discrimination",
    "target_8_replication_priority",
    "target_9_design_translation",
    "target_10_weird_extension",
}
STUDENT_TARGETS = {
    "target_1_better_stimuli",
    "target_2_better_measures",
    "target_4_deconfounding",
    "target_8_replication_priority",
}
ALLOWED_RATINGS = {"high", "medium", "low", "na"}
ALLOWED_STUDENT_FIT = {"good", "possible", "hard"}


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _label(topic: dict[str, Any], index: int) -> str:
    return str(topic.get("topic_id") or topic.get("topic_name") or f"topic[{index}]")


def validate_payload(path: Path = DEFAULT_PAYLOAD, topics_path: Path = TOPICS_PAYLOAD) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"payload missing: {path}"]
    payload = _load(path)
    source_topics = _load(topics_path).get("topics") or []
    source_topic_ids = {str(row.get("id")) for row in source_topics if row.get("id")}

    if payload.get("contract_id") != REQUIRED_CONTRACT:
        errors.append(f"payload: contract_id must be {REQUIRED_CONTRACT}")
    if payload.get("method_status") != REQUIRED_METHOD_STATUS:
        errors.append(f"payload: method_status must be {REQUIRED_METHOD_STATUS}")
    if not payload.get("computed_at"):
        errors.append("payload: computed_at is required")
    panel_status = payload.get("panel_status") or {}
    if panel_status.get("real_human_panel_completed") is not False:
        errors.append("payload: real_human_panel_completed must remain false unless actual human respondents are logged")
    if panel_status.get("source_grounded_simulated_panel_completed") is not True:
        errors.append("payload: source_grounded_simulated_panel_completed must be true")
    if "simulated" not in str(payload.get("panel_disclaimer") or "").lower():
        errors.append("payload: panel_disclaimer must state that current review is simulated")
    if payload.get("score_semantics") != REQUIRED_SCORE_SEMANTICS:
        errors.append(f"payload: score_semantics must be {REQUIRED_SCORE_SEMANTICS}")
    if payload.get("decision_context_absent") is not True:
        errors.append("payload: decision_context_absent must be true for provisional routing profiles")
    if not isinstance(payload.get("corpus_snapshot"), dict) or not payload.get("corpus_snapshot"):
        errors.append("payload: corpus_snapshot is required")

    target_definitions = payload.get("target_definitions")
    if not isinstance(target_definitions, dict):
        errors.append("payload: target_definitions must be an object")
    elif set(target_definitions) != REQUIRED_TARGETS:
        errors.append("payload: target_definitions must contain exactly the ten required VOI targets")

    topics = payload.get("topics")
    if not isinstance(topics, list) or not topics:
        return errors + ["payload: topics must be a non-empty list"]

    payload_topic_ids = {str(row.get("topic_id")) for row in topics if row.get("topic_id")}
    missing_topics = sorted(source_topic_ids - payload_topic_ids)
    extra_topics = sorted(payload_topic_ids - source_topic_ids)
    if missing_topics:
        errors.append(f"payload: missing topics from topics.json: {missing_topics[:8]}")
    if extra_topics:
        errors.append(f"payload: extra topic ids not in topics.json: {extra_topics[:8]}")

    for index, topic in enumerate(topics):
        label = _label(topic, index)
        if topic.get("method_status") != REQUIRED_METHOD_STATUS:
            errors.append(f"{label}: method_status must be {REQUIRED_METHOD_STATUS}")
        coverage = topic.get("coverage_confidence")
        if not isinstance(coverage, dict) or coverage.get("rating") not in ALLOWED_RATINGS or "basis" not in coverage:
            errors.append(f"{label}: coverage_confidence must have rating and basis")
        elif not isinstance(coverage.get("components"), dict):
            errors.append(f"{label}: coverage_confidence.components is required")
        if topic.get("score_semantics") != REQUIRED_SCORE_SEMANTICS:
            errors.append(f"{label}: score_semantics must be {REQUIRED_SCORE_SEMANTICS}")
        if topic.get("decision_context_absent") is not True:
            errors.append(f"{label}: decision_context_absent must be true")
        if not isinstance(topic.get("topic_graph_links"), dict):
            errors.append(f"{label}: topic_graph_links is required")
        if not isinstance(topic.get("citation_context"), dict):
            errors.append(f"{label}: citation_context is required")

        vector = topic.get("target_vector")
        if not isinstance(vector, dict):
            errors.append(f"{label}: target_vector must be an object")
            continue
        if set(vector) != REQUIRED_TARGETS:
            errors.append(f"{label}: target_vector must contain exactly ten targets")
            continue

        for target_id, row in vector.items():
            target_label = f"{label}:{target_id}"
            if row.get("rating") not in ALLOWED_RATINGS:
                errors.append(f"{target_label}: invalid rating {row.get('rating')!r}")
            try:
                score = float(row.get("score"))
                if score < 0.0 or score > 1.0:
                    errors.append(f"{target_label}: score must be 0..1")
            except Exception:
                errors.append(f"{target_label}: score must be numeric")
            if row.get("score_semantics") != REQUIRED_SCORE_SEMANTICS:
                errors.append(f"{target_label}: score_semantics must be {REQUIRED_SCORE_SEMANTICS}")
            if row.get("decision_context_absent") is not True:
                errors.append(f"{target_label}: decision_context_absent must be true")
            if not isinstance(row.get("score_components"), list) or not row.get("score_components"):
                errors.append(f"{target_label}: score_components must be non-empty")
            if not row.get("score_formula_version"):
                errors.append(f"{target_label}: score_formula_version is required")
            if row.get("signal_strength") not in {"direct_extracted", "indirect_keyword", "topic_metadata", "missing"}:
                errors.append(f"{target_label}: signal_strength is invalid")
            for field in ("target_confidence", "target_coverage_confidence"):
                value = row.get(field)
                if not isinstance(value, dict) or value.get("rating") not in ALLOWED_RATINGS:
                    errors.append(f"{target_label}: {field} must have an allowed rating")
            for field in ("positive_signals", "negative_signals", "missing_required_signals", "missing_evidence_flags"):
                if not isinstance(row.get(field), list):
                    errors.append(f"{target_label}: {field} must be a list")
            if target_id == "target_2_better_measures" and not row.get("missing_required_signals") and not row.get("positive_signals") and row.get("signal_strength") != "direct_extracted":
                errors.append(f"{target_label}: construct/measurement target must expose construct-validity fields or direct evidence")
            if target_id == "target_5_mechanism_weak_links" and row.get("signal_strength") == "direct_extracted":
                errors.append(f"{target_label}: PNU summaries alone must not count as direct mechanism evidence")
            if target_id == "target_10_weird_extension" and not row.get("missing_required_signals") and not row.get("positive_signals") and row.get("signal_strength") != "direct_extracted":
                errors.append(f"{target_label}: population/culture target must expose extraction status or direct evidence")
            if not str(row.get("basis") or "").strip():
                errors.append(f"{target_label}: basis is required")
            if not isinstance(row.get("evidence_signals"), dict) or not row.get("evidence_signals"):
                errors.append(f"{target_label}: evidence_signals must be non-empty")
            query = row.get("article_finder_query")
            if not isinstance(query, dict):
                errors.append(f"{target_label}: article_finder_query is required")
                continue
            for field in ("natural_language_query", "boolean_query", "structured_query", "internal_search_url"):
                if field not in query or not query.get(field):
                    errors.append(f"{target_label}: article_finder_query.{field} is required")
            for field in ("broad_query", "narrow_query", "known_work_terms", "query_test"):
                if field not in query or query.get(field) in (None, ""):
                    errors.append(f"{target_label}: article_finder_query.{field} is required")
            if not str(query.get("internal_search_url") or "").startswith("ka_search.html?q="):
                errors.append(f"{target_label}: internal_search_url must point to KA search")
            if row.get("internal_search_url") != query.get("internal_search_url"):
                errors.append(f"{target_label}: internal_search_url must match query.internal_search_url")
            structured = query.get("structured_query")
            if not isinstance(structured, dict):
                errors.append(f"{target_label}: structured_query must be an object")
            else:
                for field in ("topic_id", "target_id", "include_terms", "require_terms", "exclude_known_papers", "external_exclusion_terms", "freshness_after_year", "candidate_sources"):
                    if field not in structured:
                        errors.append(f"{target_label}: structured_query.{field} is required")
                if structured.get("target_id") != target_id:
                    errors.append(f"{target_label}: structured_query.target_id must match target")
                if not structured.get("require_terms"):
                    errors.append(f"{target_label}: structured_query.require_terms must be non-empty")

        student_projection = topic.get("student_projection")
        if not isinstance(student_projection, list):
            errors.append(f"{label}: student_projection must be a list")
        else:
            found = {row.get("target_id") for row in student_projection if isinstance(row, dict)}
            if found != STUDENT_TARGETS:
                errors.append(f"{label}: student_projection must contain targets 1, 2, 4, and 8")
        student_choice = topic.get("student_choice_projection")
        if not isinstance(student_choice, dict):
            errors.append(f"{label}: student_choice_projection is required")
        else:
            if student_choice.get("fit_level") not in ALLOWED_STUDENT_FIT:
                errors.append(f"{label}: student_choice_projection.fit_level must be one of {sorted(ALLOWED_STUDENT_FIT)}")
            if student_choice.get("method_status") != REQUIRED_METHOD_STATUS:
                errors.append(f"{label}: student_choice_projection.method_status must be {REQUIRED_METHOD_STATUS}")
            if not str(student_choice.get("why_choose_this") or "").strip():
                errors.append(f"{label}: student_choice_projection.why_choose_this is required")
            if not isinstance(student_choice.get("best_project_moves"), list) or not student_choice.get("best_project_moves"):
                errors.append(f"{label}: student_choice_projection.best_project_moves must be non-empty")
            if not isinstance(student_choice.get("watch_out_for"), list) or not student_choice.get("watch_out_for"):
                errors.append(f"{label}: student_choice_projection.watch_out_for must be non-empty")
            query = student_choice.get("first_article_finder_query")
            if not isinstance(query, dict) or not str(query.get("internal_search_url") or "").startswith("ka_search.html?q="):
                errors.append(f"{label}: student_choice_projection.first_article_finder_query must point to KA search")
            source_ids = set(student_choice.get("source_target_ids") or [])
            if not source_ids.issubset(STUDENT_TARGETS) or not source_ids:
                errors.append(f"{label}: student_choice_projection.source_target_ids must come from student targets")
            if not str(student_choice.get("recommended_deliverable") or "").strip():
                errors.append(f"{label}: student_choice_projection.recommended_deliverable is required")
        researcher_projection = topic.get("researcher_projection")
        if not isinstance(researcher_projection, list) or len(researcher_projection) != 10:
            errors.append(f"{label}: researcher_projection must contain all ten targets")
        else:
            scores = [float(row.get("score") or 0.0) for row in researcher_projection if isinstance(row, dict)]
            if scores != sorted(scores, reverse=True):
                errors.append(f"{label}: researcher_projection must be sorted by descending score")
            top_ids = [row.get("target_id") for row in (topic.get("top_targets") or [])]
            ranked_ids = [row.get("target_id") for row in researcher_projection[: len(top_ids)]]
            if top_ids != ranked_ids:
                errors.append(f"{label}: top_targets must match the first researcher_projection entries")
        if "composite_score" in topic or "final_voi_score" in topic:
            errors.append(f"{label}: must not expose a single composite VOI authority score")

    for target_id in REQUIRED_TARGETS:
        ratings = [
            ((topic.get("target_vector") or {}).get(target_id) or {}).get("rating")
            for topic in topics
        ]
        high_ratio = ratings.count("high") / max(1, len(ratings))
        if high_ratio > 0.9:
            errors.append(f"payload:{target_id}: degenerate high rating distribution ({high_ratio:.2f})")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", nargs="?", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--topics", default=str(TOPICS_PAYLOAD))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    errors = validate_payload(Path(args.payload), Path(args.topics))
    if errors:
        print(f"FAIL topic VOI profile contract: {len(errors)} violation(s)")
        for error in errors:
            print(f"- {error}")
        return 1 if args.strict else 0
    print("PASS topic VOI profile contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
