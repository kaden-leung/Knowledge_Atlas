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
    if (payload.get("panel_status") or {}).get("real_human_panel_completed") is not False:
        errors.append("payload: real_human_panel_completed must be false until the real panel is run")

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
            if not str(query.get("internal_search_url") or "").startswith("ka_search.html?q="):
                errors.append(f"{target_label}: internal_search_url must point to KA search")
            structured = query.get("structured_query")
            if not isinstance(structured, dict):
                errors.append(f"{target_label}: structured_query must be an object")
            else:
                for field in ("topic_id", "target_id", "include_terms", "require_terms", "exclude_known_papers", "freshness_after_year", "candidate_sources"):
                    if field not in structured:
                        errors.append(f"{target_label}: structured_query.{field} is required")
                if structured.get("target_id") != target_id:
                    errors.append(f"{target_label}: structured_query.target_id must match target")

        student_projection = topic.get("student_projection")
        if not isinstance(student_projection, list):
            errors.append(f"{label}: student_projection must be a list")
        else:
            found = {row.get("target_id") for row in student_projection if isinstance(row, dict)}
            if found != STUDENT_TARGETS:
                errors.append(f"{label}: student_projection must contain targets 1, 2, 4, and 8")
        researcher_projection = topic.get("researcher_projection")
        if not isinstance(researcher_projection, list) or len(researcher_projection) != 10:
            errors.append(f"{label}: researcher_projection must contain all ten targets")
        if "composite_score" in topic or "final_voi_score" in topic:
            errors.append(f"{label}: must not expose a single composite VOI authority score")

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
