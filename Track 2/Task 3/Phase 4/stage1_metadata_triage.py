"""Phase 4 Sub-phase 4A — Stage 1 metadata-only triage.

Cheap-and-cheap-only rules over (title, venue, DOI presence). Rejects the
30-50% of harvested rows that are obvious noise BEFORE any abstract is fetched.
See STAGE1_TRIAGE_CONTRACT.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
_COGS160 = _HERE.parents[2]

DEFAULT_THRESHOLD = 0.20
SIGNIFICANT_WORD_MIN_CHARS = 3
SIGNIFICANT_WORD_MIN_COUNT = 4

# Noise-regex rules (order matters; first fire wins)
_NOISE_RULES: list[tuple[str, Callable[[str], bool]]] = [
    ("noise:empty_title", lambda t: not t or not t.strip()),
    ("noise:jstor_footer", lambda t: t.strip().lower().startswith("this content downloaded from")),
    ("noise:jstor_terms", lambda t: "use subject to https://about.jstor.org/terms" in t.lower()),
    ("noise:pdf_cid_artifact", lambda t: "(cid:" in t.lower()),
    ("noise:url_only", lambda t: bool(re.fullmatch(r"https?://\S+", t.strip()))),
    # Catches "417, https://doi.org/10.3390/..." — citation number followed by DOI URL
    ("noise:doi_url_artifact",
     lambda t: bool(re.search(r"^[\d\s,]*https?://\s*(doi\.org|dx\.doi\.org)/", t.strip()))),
    # Catches "https:// doi.org/..." — malformed URL with space that bypasses url_only
    ("noise:malformed_url",
     lambda t: bool(re.match(r"https?://\s+\S", t.strip()))),
    ("noise:page_range_artifact", lambda t: bool(re.fullmatch(r"\d{1,3}\s*[-./]\s*\d{1,3}", t.strip()))),
]

# CNFA keyword set for the keyword fallback classifier.
# Bug fix 2026-06-01: added "architectural" and "sensorimotor" because the
# substring test `kw in title.lower()` fails for adjectival forms:
# "architecture" is NOT a substring of "architectural" — they differ at the
# 12th character ('e' vs 'a'). Djebbara 2019 ("Sensorimotor brain dynamics
# reflect architectural affordances") was a false negative because of this.
# Also added "perception", "environment", "human", "space", "room" to reduce
# false-negative rate for papers using common CNFA vocabulary without the
# field's technical terminology.
CNFA_KEYWORDS = {
    "architecture", "architectural", "spatial", "built environment",
    "building", "buildings",
    "cognition", "cognitive", "arousal", "restoration", "attention",
    "wayfinding", "threshold", "façade", "facade", "cortisol", "stress",
    "psychophysiolog", "neural", "fmri", "eeg", "eda", "circadian",
    "navigation", "place", "memory", "emotion", "affect",
    "predictive", "coding", "interoception", "embodied", "multisensory",
    "biophilic", "biophilia", "daylight", "lighting", "thermal",
    "sensorimotor", "affordance", "affordances",
    "perception", "environment", "occupant", "indoor",
    "wellbeing", "well-being", "health", "comfort",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def significant_word_count(title: str) -> int:
    """Count tokens with length >= SIGNIFICANT_WORD_MIN_CHARS after punctuation strip."""
    if not title:
        return 0
    cleaned = re.sub(r"[^\w\s-]", " ", title)
    return sum(1 for tok in cleaned.split() if len(tok) >= SIGNIFICANT_WORD_MIN_CHARS)


# ---------------------------------------------------------------------------
# Noise check
# ---------------------------------------------------------------------------

def check_noise(title: str | None, doi: str | None) -> tuple[str | None, str | None]:
    """Apply the noise-regex rules in order. Return (reason, None) if rejected else (None, None)."""
    t = title or ""
    # First-fire-wins over the rule list
    for reason, predicate in _NOISE_RULES:
        try:
            if predicate(t):
                return reason, None
        except Exception:
            continue
    # Short title rule depends on DOI presence
    if not doi and significant_word_count(t) < SIGNIFICANT_WORD_MIN_COUNT:
        return "noise:title_too_short_no_doi", None
    return None, None


# ---------------------------------------------------------------------------
# Classifier loading + fallback
# ---------------------------------------------------------------------------

def keyword_fallback_classify(title: str | None, venue: str | None) -> tuple[str, float]:
    """Count CNFA keyword hits across (title, venue); return ('PASS'|'REJECT', confidence)."""
    text = " ".join(filter(None, [title, venue])).lower()
    hits = sum(1 for kw in CNFA_KEYWORDS if kw in text)
    if hits >= 3:
        return "PASS", 0.50
    if hits >= 1:
        return "PASS", 0.25  # just above threshold; survives stage 1 but flagged
    return "REJECT", 0.0


def load_classifier() -> Callable[[str | None, str | None], tuple[str, float]]:
    """Return a `classify(title, venue) -> (decision, confidence)` function.

    Tries to load HierarchicalClassifier first; on any failure falls back to
    the keyword classifier (which always works).
    """
    af_path = _COGS160 / "Article_Finder"
    if str(af_path) not in sys.path:
        sys.path.insert(0, str(af_path))
    try:
        from triage.classifier import HierarchicalClassifier  # type: ignore
        # Look for centroids file
        centroids = af_path / "triage" / ".centroids.pkl"
        if not centroids.exists():
            raise FileNotFoundError("centroids not present")
        clf = HierarchicalClassifier(centroids_path=str(centroids))
        def _classify(title: str | None, venue: str | None) -> tuple[str, float]:
            result = clf.classify_paper(title=title or "", venue=venue, abstract=None)
            # HierarchicalClassifier returns dict-like with 'decision' and 'confidence' keys
            decision = result.get("decision", "REJECT") if isinstance(result, dict) else "REJECT"
            confidence = float(result.get("confidence", 0.0)) if isinstance(result, dict) else 0.0
            return decision, confidence
        return _classify
    except Exception:
        return keyword_fallback_classify


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Stage1Report:
    schema_version: str = "1.0.0"
    run_id: str = ""
    started_at: str = ""
    ended_at: str = ""
    classifier_mode: str = ""               # "hierarchical" | "keyword_fallback"
    candidates_processed: int = 0
    passed_to_stage2a: int = 0
    rejected_total: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)

    @property
    def rejection_rate(self) -> float:
        return self.rejected_total / self.candidates_processed if self.candidates_processed else 0.0

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "classifier_mode": self.classifier_mode,
            "candidates_processed": self.candidates_processed,
            "passed_to_stage2a": self.passed_to_stage2a,
            "rejected_total": self.rejected_total,
            "rejection_rate": round(self.rejection_rate, 4),
            "reject_reasons": dict(self.reject_reasons),
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_stage1_triage(
    *,
    db_path: Path,
    run_id: str,
    threshold: float = DEFAULT_THRESHOLD,
    max_candidates: int | None = None,
    classifier: Callable[[str | None, str | None], tuple[str, float]] | None = None,
    dry_run: bool = False,
) -> Stage1Report:
    """Walk every `triage_stage='metadata_only'` row through the Stage 1 funnel."""
    if classifier is None:
        classifier = load_classifier()
        classifier_mode = "keyword_fallback" if classifier is keyword_fallback_classify else "hierarchical"
    else:
        classifier_mode = "injected"

    report = Stage1Report(run_id=run_id, started_at=utc_now_iso(), classifier_mode=classifier_mode)

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
            "SELECT reference_id, title_raw, doi, venue FROM article_references "
            "WHERE triage_stage = 'metadata_only' ORDER BY reference_id"
        ).fetchall()
        if max_candidates is not None:
            candidates = candidates[:max_candidates]

        for row in candidates:
            report.candidates_processed += 1
            ref_id = row["reference_id"]
            title = row["title_raw"]
            doi = row["doi"]
            venue = row["venue"]

            # Step 1: noise check
            noise_reason, _ = check_noise(title, doi)
            if noise_reason:
                _reject(conn, ref_id, run_id, noise_reason, confidence=None)
                report.rejected_total += 1
                report.reject_reasons[noise_reason] = report.reject_reasons.get(noise_reason, 0) + 1
                continue

            # Step 2: classifier check
            try:
                decision, confidence = classifier(title, venue)
            except Exception as exc:
                report.errors.append({"reference_id": ref_id, "stage": "classifier", "error": str(exc)})
                continue

            if decision == "REJECT" or confidence < threshold:
                reason = f"classifier_below_threshold:{confidence:.2f}"
                _reject(conn, ref_id, run_id, reason, confidence=confidence)
                report.rejected_total += 1
                # Bucket into one entry per threshold tier for the report
                bucket = "classifier_below_threshold:0.00-0.19"
                report.reject_reasons[bucket] = report.reject_reasons.get(bucket, 0) + 1
                continue

            # Pass
            reason = f"stage1_passed:{confidence:.2f}"
            _pass(conn, ref_id, run_id, reason, confidence=confidence)
            report.passed_to_stage2a += 1

        conn.commit()
    finally:
        conn.close()

    report.ended_at = utc_now_iso()
    return report


def _reject(conn, reference_id: str, run_id: str, reason: str, confidence: float | None) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE article_references
           SET triage_stage = 'rejected_at_metadata',
               triage_decision = 'REJECT',
               triage_reason = ?,
               classifier_confidence = ?,
               updated_at = ?
         WHERE reference_id = ? AND triage_stage = 'metadata_only'
        """,
        (reason, confidence, now, reference_id),
    )
    conn.execute(
        """
        INSERT INTO lifecycle_transitions
          (reference_id, run_id, from_stage, to_stage, reason, created_by)
        VALUES (?, ?, 'metadata_only', 'rejected_at_metadata', ?, 'abstract_triage')
        """,
        (reference_id, run_id, reason),
    )


def _pass(conn, reference_id: str, run_id: str, reason: str, confidence: float) -> None:
    now = utc_now_iso()
    conn.execute(
        """
        UPDATE article_references
           SET triage_stage = 'abstract_pending',
               classifier_confidence = ?,
               triage_reason = ?,
               updated_at = ?
         WHERE reference_id = ? AND triage_stage = 'metadata_only'
        """,
        (confidence, reason, now, reference_id),
    )
    conn.execute(
        """
        INSERT INTO lifecycle_transitions
          (reference_id, run_id, from_stage, to_stage, reason, created_by)
        VALUES (?, ?, 'metadata_only', 'abstract_pending', ?, 'abstract_triage')
        """,
        (reference_id, run_id, reason),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4 Stage 1 metadata-only triage")
    parser.add_argument("--db", default=str(_HERE.parent / "task3_pipeline_lifecycle.db"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default=str(_HERE / "stage1_triage_report.json"))
    args = parser.parse_args(argv)

    run_id = args.run_id or f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    report = run_stage1_triage(
        db_path=Path(args.db),
        run_id=run_id,
        threshold=args.threshold,
        max_candidates=args.max_candidates,
        dry_run=args.dry_run,
    )

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(
        f"[stage1_triage] processed={report.candidates_processed} "
        f"passed={report.passed_to_stage2a} rejected={report.rejected_total} "
        f"rate={report.rejection_rate:.1%} mode={report.classifier_mode}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
