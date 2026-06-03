"""Unified abstract triage CLI — Stage 1 + Stage 2A + Stage 2B.

Runs the full three-stage triage pipeline against the article_references table:
  Stage 1: Metadata-only screen (noise + keyword classifier)
  Stage 2A: Abstract collection via 4-source fallback chain
  Stage 2B: Classifier × VOI triage decision (ACCEPT / EDGE_CASE / REJECT)

Usage:
    python3 abstract_triage.py                    # full run (all three stages)
    python3 abstract_triage.py --stage 1          # Stage 1 only
    python3 abstract_triage.py --stage 2a         # Stage 2A only
    python3 abstract_triage.py --stage 2b         # Stage 2B only
    python3 abstract_triage.py --dry-run          # plan only, no DB writes
    python3 abstract_triage.py --mock             # Stage 2A uses mock fixtures

The --papers argument is accepted for compatibility with the course spec CLI:
    python3 abstract_triage.py --papers papers_with_abstracts.json
(No-op: triage reads/writes the DB directly rather than JSON files.)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TASK3 = _HERE.parent

# Import stage modules
sys.path.insert(0, str(_HERE))
from stage1_metadata_triage import run_stage1_triage
from abstract_collector import run_collection
from stage2b_triage_decision import run_stage2b_triage

DEFAULT_DB = _TASK3 / "task3_pipeline_lifecycle.db"
# Vendored Task 2 query artifact, local to Task 3 (see inputs/QUERY_PROVENANCE.md).
DEFAULT_QUERY_RESULTS = _TASK3 / "inputs" / "query_results.json"
DEFAULT_FIXTURES = _HERE / "fixtures"


def utc_run_id() -> str:
    return f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Three-stage abstract triage pipeline (Stage 1 + 2A + 2B)"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--stage", choices=["1", "2a", "2b"], default=None,
                        help="Run only a specific stage (default: all three)")
    parser.add_argument("--query-results", default=str(DEFAULT_QUERY_RESULTS),
                        help="Path to query_results.json (for Stage 2B VOI lookup)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mock", action="store_true",
                        help="Stage 2A reads fixture abstracts instead of live APIs")
    parser.add_argument("--mock-fixtures-dir", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--voi-medium", type=float, default=0.40)
    parser.add_argument("--threshold", type=float, default=0.20,
                        help="Stage 1 classifier confidence threshold")
    parser.add_argument("--max-candidates", type=int, default=None)
    # Compatibility alias: --papers is accepted but unused (triage reads from DB)
    parser.add_argument("--papers", default=None,
                        help="(Compatibility arg — triage reads from DB, not JSON)")
    parser.add_argument("--output", default=str(_HERE / "triage_results.json"))
    args = parser.parse_args(argv)

    run_id = args.run_id or utc_run_id()
    db_path = Path(args.db)
    run_stages = {args.stage} if args.stage else {"1", "2a", "2b"}

    results: dict = {"run_id": run_id, "stages": {}}

    # ---------- Stage 1 ----------
    if "1" in run_stages:
        print("[abstract_triage] Stage 1: metadata-only screen...", file=sys.stderr)
        s1_report = run_stage1_triage(
            db_path=db_path, run_id=run_id,
            threshold=args.threshold, max_candidates=args.max_candidates,
            dry_run=args.dry_run,
        )
        results["stages"]["stage1"] = {
            "candidates_processed": s1_report.candidates_processed,
            "passed": s1_report.passed_to_stage2a,
            "rejected": s1_report.rejected_total,
            "rejection_rate": s1_report.rejection_rate,
            "classifier_mode": s1_report.classifier_mode,
        }
        print(
            f"[abstract_triage] Stage 1 done: "
            f"{s1_report.passed_to_stage2a} passed / {s1_report.rejected_total} rejected",
            file=sys.stderr,
        )

    # ---------- Stage 2A ----------
    if "2a" in run_stages:
        print("[abstract_triage] Stage 2A: abstract collection...", file=sys.stderr)
        s2a_report = run_collection(
            db_path=db_path, run_id=run_id,
            max_candidates=args.max_candidates,
            mock=args.mock,
            mock_fixtures_dir=Path(args.mock_fixtures_dir) if args.mock else None,
            dry_run=args.dry_run,
        )
        results["stages"]["stage2a"] = {
            "candidates_processed": s2a_report.candidates_processed,
            "abstracts_found": s2a_report.abstracts_found,
            "missing_abstract": s2a_report.missing_abstracts,
            "hit_rate": s2a_report.hit_rate,
            "hit_rate_doi_only": s2a_report.hit_rate_doi_only,
            "by_source": s2a_report.source_breakdown,
        }
        print(
            f"[abstract_triage] Stage 2A done: "
            f"{s2a_report.abstracts_found} found / {s2a_report.missing_abstracts} missing "
            f"(hit rate {s2a_report.hit_rate:.1%}, DOI-only {s2a_report.hit_rate_doi_only:.1%})",
            file=sys.stderr,
        )

    # ---------- Stage 2B ----------
    if "2b" in run_stages:
        print("[abstract_triage] Stage 2B: triage decision...", file=sys.stderr)
        qr_path = Path(args.query_results) if args.query_results else None
        edge_output = _HERE / "edge_cases_for_review.json"
        s2b_report = run_stage2b_triage(
            db_path=db_path, run_id=run_id,
            query_results_json=qr_path,
            voi_medium=args.voi_medium,
            max_candidates=args.max_candidates,
            dry_run=args.dry_run,
            edge_cases_output=edge_output if not args.dry_run else None,
        )
        results["stages"]["stage2b"] = {
            "candidates_processed": s2b_report.candidates_processed,
            "decisions": s2b_report.decisions,
            "classifier_mode": s2b_report.classifier_mode,
        }
        print(
            f"[abstract_triage] Stage 2B done: "
            f"ACCEPT={s2b_report.decisions.get('ACCEPT',0)} "
            f"EDGE={s2b_report.decisions.get('EDGE_CASE',0)} "
            f"REJECT={s2b_report.decisions.get('REJECT',0)}",
            file=sys.stderr,
        )

    # Write combined results
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"[abstract_triage] Results written to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
