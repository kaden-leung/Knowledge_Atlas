#!/usr/bin/env python3
"""Build a deterministic corpus-level substitution admit index.

This script runs the substitution skill over in-corpus article detail records by
paper_id. It does not call an LLM. The output is a compact payload for dashboards
and downstream checks; detailed per-DV evidence remains available through the
admit-mode API.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import ka_substitution_skill as skill

DEFAULT_OUTPUT = REPO_ROOT / "data" / "ka_payloads" / "substitution_admit_index.json"


def summarize_result(paper_id: str, result: dict[str, Any]) -> dict[str, Any]:
    rows = result.get("per_dv_results") or []
    verdict_counts = Counter(row.get("admit_verdict") or "unknown" for row in rows)
    refusal_counts = Counter(row.get("refusal_reason") or "" for row in rows if row.get("refusal_reason"))
    top_candidates: list[str] = []
    excluded_codes: list[str] = []
    for row in rows:
        for candidate in row.get("substitution_candidates") or []:
            code = candidate.get("measure_short_code")
            if code and code not in top_candidates:
                top_candidates.append(code)
        for measure in row.get("excluded_measures") or []:
            code = measure.get("measure_short_code")
            if code and code not in excluded_codes:
                excluded_codes.append(code)

    return {
        "paper_id": paper_id,
        "paper_level_verdict": result.get("paper_level_verdict"),
        "paper_level_confidence": result.get("paper_level_confidence"),
        "paper_lookup": result.get("paper_lookup") or {},
        "dv_count": len(rows),
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "refusal_counts": dict(sorted(refusal_counts.items())),
        "top_substitution_candidates": top_candidates[:5],
        "top_excluded_measures": excluded_codes[:5],
    }


def build_index(limit: int | None = None) -> dict[str, Any]:
    skill.ensure_substitution_graph_db()
    details = skill.load_article_details()
    paper_ids = sorted(details)
    if limit is not None:
        paper_ids = paper_ids[:limit]

    rows = []
    aggregate_verdicts: Counter[str] = Counter()
    aggregate_lookup_status: Counter[str] = Counter()
    total_dvs = 0
    for paper_id in paper_ids:
        result = skill.admit_mode({"paper_id": paper_id, "generate_prose": False})
        summary = summarize_result(paper_id, result)
        rows.append(summary)
        aggregate_verdicts[summary["paper_level_verdict"] or "unknown"] += 1
        aggregate_lookup_status[(summary["paper_lookup"] or {}).get("status") or "unknown"] += 1
        total_dvs += int(summary["dv_count"] or 0)

    return {
        "schema_version": "ka_substitution_admit_index_v1",
        "source": {
            "article_details": "data/ka_payloads/article_details.json",
            "substitution_graph": "data/substitution_graph.db",
            "llm_used": False,
        },
        "summary": {
            "paper_count": len(rows),
            "dv_count": total_dvs,
            "paper_level_verdicts": dict(sorted(aggregate_verdicts.items())),
            "paper_lookup_status": dict(sorted(aggregate_lookup_status.items())),
        },
        "papers": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    payload = build_index(limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        "substitution admit index:",
        payload["summary"]["paper_count"],
        "papers,",
        payload["summary"]["dv_count"],
        "DVs ->",
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
