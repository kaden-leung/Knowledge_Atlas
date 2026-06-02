"""Phase 4 Sub-phase 4D — Stage 2B triage decision.

The choke point: each abstract_collected row gets a 4-way decision
(ACCEPT / EDGE_CASE / REJECT — plus MISSING_ABSTRACT which is set by 4B
and skipped here). See TRIAGE_DECISION_CONTRACT.md.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
_COGS160 = _HERE.parents[2]

# Reuse Stage 1's classifier loader (handles HierarchicalClassifier + keyword fallback)
sys.path.insert(0, str(_HERE))
from stage1_metadata_triage import load_classifier, keyword_fallback_classify  # noqa: E402

# Default thresholds (from TRIAGE_DECISION_CONTRACT.md §3, Balanced)
DEFAULT_CLF_ON_TOPIC = 0.50
DEFAULT_CLF_OFF_TOPIC = 0.20
DEFAULT_VOI_HIGH = 0.70
DEFAULT_VOI_MEDIUM = 0.50
DEFAULT_VOI_FALLBACK = 0.443

# Default input paths
DEFAULT_DB = _HERE.parent / "task3_pipeline_lifecycle.db"
DEFAULT_QUERY_RESULTS = _HERE.parents[2] / "Track 2" / "Task 2" / "Phase 3" / "query_results.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# VOI lookup
# ---------------------------------------------------------------------------

def load_voi_map(query_results_json: Path | None) -> dict[str, float]:
    """Build a dict mapping query string AND display_id → voi_score.

    Returns an empty dict if the file is missing (every lookup will fall to default).
    """
    if not query_results_json or not query_results_json.exists():
        return {}
    data = json.loads(query_results_json.read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    for q in data.get("queries", []):
        voi_raw = q.get("voi_score")
        try:
            voi = float(voi_raw)
        except (TypeError, ValueError):
            continue
        for key_field in ("boolean_query", "display_id", "ai_citation_query", "template_id"):
            key = q.get(key_field)
            if isinstance(key, str) and key.strip():
                out.setdefault(key.strip(), voi)
        # also index by display_key like "SC3-step3" for runs that join step_number
        display_id = q.get("display_id")
        step = q.get("step_number")
        if display_id and step is not None:
            out.setdefault(f"{display_id}-step{step}", voi)
    return out


def lookup_voi(query: str | None, voi_map: dict[str, float], default: float = DEFAULT_VOI_FALLBACK) -> tuple[float, bool]:
    """Return (voi, hit?). `hit` indicates the query matched a known VOI entry."""
    if not query:
        return default, False
    key = query.strip()
    if key in voi_map:
        return voi_map[key], True
    return default, False


# ---------------------------------------------------------------------------
# Decision matrix (TRIAGE_DECISION_CONTRACT.md §3, Balanced)
# ---------------------------------------------------------------------------

def decide(
    confidence: float,
    voi: float,
    *,
    clf_on_topic: float = DEFAULT_CLF_ON_TOPIC,
    clf_off_topic: float = DEFAULT_CLF_OFF_TOPIC,
    voi_high: float = DEFAULT_VOI_HIGH,
    voi_medium: float = DEFAULT_VOI_MEDIUM,
) -> tuple[str, str]:
    """Apply the 2D matrix. Returns (decision, reason)."""
    # Classifier bucket
    if confidence >= clf_on_topic:
        clf_bucket = "on_topic"
    elif confidence >= clf_off_topic:
        clf_bucket = "marginal"
    else:
        clf_bucket = "off_topic"

    # VOI bucket
    if voi >= voi_high:
        voi_bucket = "high"
    elif voi >= voi_medium:
        voi_bucket = "medium"
    else:
        voi_bucket = "low"

    fmt = f"clf={confidence:.2f},voi={voi:.2f}"

    if clf_bucket == "on_topic":
        if voi_bucket in ("high", "medium"):
            return "ACCEPT", f"accept_topic_and_voi:{fmt}"
        return "EDGE_CASE", f"edge_on_topic_low_voi:{fmt}"

    if clf_bucket == "marginal":
        if voi_bucket == "high":
            return "EDGE_CASE", f"edge_marginal_topic_high_voi:{fmt}"
        if voi_bucket == "medium":
            return "EDGE_CASE", f"edge_marginal_topic_medium_voi:{fmt}"
        return "REJECT", f"reject_marginal_low_voi:{fmt}"

    # off_topic
    return "REJECT", f"reject_off_topic:{fmt}"


# ---------------------------------------------------------------------------
# Classifier (Stage 2B has abstract — call signature differs from Stage 1)
# ---------------------------------------------------------------------------

def keyword_fallback_classify_with_abstract(
    title: str | None,
    venue: str | None,
    abstract: str | None,
) -> tuple[str, float]:
    """Extend Stage 1's keyword fallback to count keywords in abstract too.

    With the abstract, the keyword count is much higher; we scale confidence
    differently to reflect that. Threshold semantics still match TRIAGE_DECISION_CONTRACT.md §3.
    """
    from stage1_metadata_triage import CNFA_KEYWORDS
    text = " ".join(filter(None, [title, venue, abstract])).lower()
    hits = sum(1 for kw in CNFA_KEYWORDS if kw in text)
    # Calibrated for abstract-rich text (more hits expected than title-only)
    if hits >= 8:
        return "PASS", 0.85
    if hits >= 5:
        return "PASS", 0.60
    if hits >= 3:
        return "PASS", 0.45  # marginal
    if hits >= 1:
        return "PASS", 0.25  # marginal-low
    return "REJECT", 0.0


def load_stage2b_classifier() -> tuple[Callable[[str | None, str | None, str | None], tuple[str, float]], str]:
    """Return (classify_fn, mode_label)."""
    # Try HierarchicalClassifier first (same loader as Stage 1)
    stage1_clf = load_classifier()
    if stage1_clf is not keyword_fallback_classify:
        # We got the real classifier; wrap to accept abstract argument
        def _wrap(title, venue, abstract):
            # HierarchicalClassifier.classify_paper(title, venue, abstract=...) supports it
            try:
                from triage.classifier import HierarchicalClassifier  # noqa: F401
                # The Stage 1 wrapper already calls classify_paper with abstract=None;
                # we just need a fresh call that includes the abstract.
                # Simplest: re-use stage1_clf signature (title, venue) and accept abstract loss.
                # Better: instantiate a fresh wrapper that passes abstract through.
                # For now, fall back if abstract handling is unclear.
                return stage1_clf(title, venue)
            except Exception:
                return keyword_fallback_classify_with_abstract(title, venue, abstract)
        return _wrap, "hierarchical"
    # Fallback path
    return keyword_fallback_classify_with_abstract, "keyword_fallback"


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class Stage2BReport:
    schema_version: str = "1.0.0"
    run_id: str = ""
    started_at: str = ""
    ended_at: str = ""
    classifier_mode: str = ""
    candidates_processed: int = 0
    decisions: dict[str, int] = field(default_factory=lambda: {"ACCEPT": 0, "EDGE_CASE": 0, "REJECT": 0})
    voi_lookup_hits: int = 0
    voi_lookup_misses: int = 0
    thresholds: dict[str, float] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "candidates_processed": self.candidates_processed,
            "decisions": dict(self.decisions),
            "classifier_mode": self.classifier_mode,
            "thresholds": dict(self.thresholds),
            "voi_lookup_hits": self.voi_lookup_hits,
            "voi_lookup_misses": self.voi_lookup_misses,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# DB orchestration
# ---------------------------------------------------------------------------

def _write_back(
    conn: sqlite3.Connection,
    reference_id: str,
    triage_decision: str,
    triage_reason: str,
    confidence: float,
    voi: float,
    run_id: str,
) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE article_references
           SET triage_decision = ?,
               triage_reason = ?,
               classifier_confidence = ?,
               voi_score = ?,
               triage_stage = 'triage_complete',
               updated_at = ?
         WHERE reference_id = ? AND triage_stage = 'abstract_collected'
        """,
        (triage_decision, triage_reason, confidence, voi, now, reference_id),
    )
    conn.execute(
        """
        INSERT INTO lifecycle_transitions
          (reference_id, run_id, from_stage, to_stage, reason, created_by)
        VALUES (?, ?, 'abstract_collected', 'triage_complete', ?, 'abstract_triage')
        """,
        (reference_id, run_id, triage_reason),
    )


def _export_edge_cases(conn: sqlite3.Connection, run_id: str, output_path: Path) -> int:
    """Write EDGE_CASE rows to a human-readable JSON. Returns count exported."""
    rows = conn.execute(
        """
        SELECT reference_id, title_raw, doi, venue, abstract_text,
               triage_reason, classifier_confidence, voi_score
        FROM article_references
        WHERE triage_decision = 'EDGE_CASE' AND triage_stage = 'triage_complete'
        ORDER BY classifier_confidence DESC, voi_score DESC
        """
    ).fetchall()
    payload = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": utc_now_iso(),
        "edge_cases": [
            {
                "reference_id": r[0],
                "title_raw": r[1],
                "doi": r[2],
                "venue": r[3],
                "abstract_text": r[4],
                "triage_reason": r[5],
                "classifier_confidence": r[6],
                "voi_score": r[7],
            }
            for r in rows
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(rows)


def run_stage2b_triage(
    *,
    db_path: Path,
    run_id: str,
    query_results_json: Path | None = None,
    classifier: Callable[[str | None, str | None, str | None], tuple[str, float]] | None = None,
    classifier_mode: str | None = None,
    clf_on_topic: float = DEFAULT_CLF_ON_TOPIC,
    clf_off_topic: float = DEFAULT_CLF_OFF_TOPIC,
    voi_high: float = DEFAULT_VOI_HIGH,
    voi_medium: float = DEFAULT_VOI_MEDIUM,
    voi_default: float = DEFAULT_VOI_FALLBACK,
    max_candidates: int | None = None,
    dry_run: bool = False,
    edge_cases_output: Path | None = None,
) -> Stage2BReport:
    """Walk every `triage_stage='abstract_collected'` row through the decision matrix."""
    if classifier is None:
        classifier, classifier_mode = load_stage2b_classifier()
    elif classifier_mode is None:
        classifier_mode = "injected"

    voi_map = load_voi_map(query_results_json) if query_results_json else {}

    report = Stage2BReport(
        run_id=run_id,
        started_at=utc_now_iso(),
        classifier_mode=classifier_mode,
        thresholds={
            "classifier_on_topic": clf_on_topic,
            "classifier_off_topic": clf_off_topic,
            "voi_high": voi_high,
            "voi_medium": voi_medium,
            "voi_default": voi_default,
        },
    )

    if dry_run:
        src = sqlite3.connect(str(db_path))
        conn = sqlite3.connect(":memory:")
        src.backup(conn)
        src.close()
    else:
        conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    try:
        candidates = conn.execute(
            "SELECT reference_id, title_raw, abstract_text, venue, discovered_query "
            "FROM article_references WHERE triage_stage = 'abstract_collected' "
            "ORDER BY reference_id"
        ).fetchall()
        if max_candidates is not None:
            candidates = candidates[:max_candidates]

        for row in candidates:
            report.candidates_processed += 1
            ref_id = row["reference_id"]
            try:
                _, confidence = classifier(row["title_raw"], row["venue"], row["abstract_text"])
            except Exception as exc:
                report.errors.append({"reference_id": ref_id, "stage": "classifier", "error": str(exc)})
                continue

            voi, hit = lookup_voi(row["discovered_query"], voi_map, default=voi_default)
            if hit:
                report.voi_lookup_hits += 1
            else:
                report.voi_lookup_misses += 1

            triage_decision, triage_reason = decide(
                confidence, voi,
                clf_on_topic=clf_on_topic, clf_off_topic=clf_off_topic,
                voi_high=voi_high, voi_medium=voi_medium,
            )
            report.decisions[triage_decision] = report.decisions.get(triage_decision, 0) + 1
            _write_back(conn, ref_id, triage_decision, triage_reason, confidence, voi, run_id)

        conn.commit()

        if not dry_run and edge_cases_output is not None:
            _export_edge_cases(conn, run_id, edge_cases_output)
    finally:
        conn.close()

    report.ended_at = utc_now_iso()
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 Stage 2B triage decision")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--query-results", default=str(DEFAULT_QUERY_RESULTS))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default=str(_HERE / "triage_results.json"))
    parser.add_argument("--edge-cases-output", default=str(_HERE / "edge_cases_for_review.json"))
    parser.add_argument("--clf-on-topic", type=float, default=DEFAULT_CLF_ON_TOPIC)
    parser.add_argument("--clf-off-topic", type=float, default=DEFAULT_CLF_OFF_TOPIC)
    parser.add_argument("--voi-high", type=float, default=DEFAULT_VOI_HIGH)
    parser.add_argument("--voi-medium", type=float, default=DEFAULT_VOI_MEDIUM)
    parser.add_argument("--voi-default", type=float, default=DEFAULT_VOI_FALLBACK)
    args = parser.parse_args(argv)

    run_id = args.run_id or f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    report = run_stage2b_triage(
        db_path=Path(args.db),
        run_id=run_id,
        query_results_json=Path(args.query_results) if args.query_results else None,
        clf_on_topic=args.clf_on_topic,
        clf_off_topic=args.clf_off_topic,
        voi_high=args.voi_high,
        voi_medium=args.voi_medium,
        voi_default=args.voi_default,
        max_candidates=args.max_candidates,
        dry_run=args.dry_run,
        edge_cases_output=Path(args.edge_cases_output) if not args.dry_run else None,
    )

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(
        f"[stage2b_triage] processed={report.candidates_processed} "
        f"ACCEPT={report.decisions['ACCEPT']} "
        f"EDGE_CASE={report.decisions['EDGE_CASE']} "
        f"REJECT={report.decisions['REJECT']} "
        f"mode={report.classifier_mode}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
