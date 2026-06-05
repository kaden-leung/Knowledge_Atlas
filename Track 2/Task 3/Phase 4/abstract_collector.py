"""Phase 4 Sub-phase 4B — Abstract collector.

Walks the fallback chain S2 → CrossRef → PubMed → OpenAlex for each candidate
that survived Stage 1 metadata triage. Tags MISSING_ABSTRACT when every source
comes up empty. See ABSTRACT_COLLECTOR_CONTRACT.md.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

# macOS Python 3.x framework installs omit the system CA bundle; certifi ships
# its own. Setting SSL_CERT_FILE before any SSL context is created makes
# urllib (and everything that calls it, including paper_fetcher.py) use certifi.
try:
    import certifi as _certifi
    os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())
except ImportError:
    pass

_HERE = Path(__file__).resolve().parent
_TASK3 = _HERE.parent
if str(_TASK3) not in sys.path:
    sys.path.insert(0, str(_TASK3))

from workspace_paths import find_repository  # noqa: E402

# Wire up Article_Eater paper_fetcher directly (bypasses Article_Eater/src/core
# which has competing __init__.py that imports from `src.core.logging`).
# Also wire up Article_Finder for normalize_doi / normalize_title.
_AE = find_repository("Article_Eater", _HERE)
_AE_SERVICES = _AE / "src" / "services" if _AE else None
_AF = find_repository("Article_Finder", _HERE)
for p in (_AE_SERVICES, _AF):  # Article_Finder ends up first → wins `core` lookups
    if p is None:
        continue
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from core.ae_corpus_dedupe import normalize_doi as _af_normalize_doi, normalize_title  # noqa: E402
from paper_fetcher import (  # noqa: E402
    SemanticScholarClient,
    CrossRefClient,
    PubMedClient,
    FetchStatus,
    estimate_study_type,
)
from openalex_client import OpenAlexClient  # noqa: E402

# Valid abstract_source tokens (matches §4 of the contract)
VALID_SOURCES = frozenset({
    "semantic_scholar", "crossref", "pubmed", "openalex", "MISSING_ABSTRACT"
})


def normalize_doi(value: str | None) -> str | None:
    """Wrap ae_corpus_dedupe.normalize_doi; return None instead of empty string."""
    result = _af_normalize_doi(value)
    return result if result else None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AbstractResult:
    abstract: str | None              # None only when source == "MISSING_ABSTRACT"
    source: str                       # one of VALID_SOURCES
    doi_used: str | None
    title_used: str | None
    study_type: str | None


@dataclass
class CollectorReport:
    schema_version: str = "1.0.0"
    run_id: str = ""
    started_at: str = ""
    ended_at: str = ""
    candidates_processed: int = 0
    abstracts_found: int = 0
    missing_abstracts: int = 0
    source_breakdown: dict[str, int] = field(default_factory=dict)
    study_type_breakdown: dict[str, int] = field(default_factory=dict)
    doi_processed: int = 0
    doi_with_abstract: int = 0
    errors: list[dict] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return (self.abstracts_found / self.candidates_processed) if self.candidates_processed else 0.0

    @property
    def hit_rate_doi_only(self) -> float:
        return (self.doi_with_abstract / self.doi_processed) if self.doi_processed else 0.0

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "candidates_processed": self.candidates_processed,
            "abstracts_found": self.abstracts_found,
            "missing_abstracts": self.missing_abstracts,
            "hit_rate": round(self.hit_rate, 4),
            "hit_rate_doi_only": round(self.hit_rate_doi_only, 4),
            "source_breakdown": dict(self.source_breakdown),
            "study_type_breakdown": dict(self.study_type_breakdown),
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# Mock fixture loader
# ---------------------------------------------------------------------------

def _load_mock_fixture(fixtures_dir: Path, doi: str | None, title: str | None) -> AbstractResult:
    """Mock mode: read fixture JSON files. Match by DOI first, then title substring.

    Fixture file format: a list of {doi, title, abstract, source} dicts.
    File: `mock_abstracts.json` in the fixtures directory.
    Returns MISSING_ABSTRACT if no fixture matches.
    """
    path = fixtures_dir / "mock_abstracts.json"
    if not path.exists():
        return AbstractResult(None, "MISSING_ABSTRACT", doi, title, None)
    entries: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    norm_doi = normalize_doi(doi)
    norm_title = normalize_title(title) if title else ""
    for e in entries:
        e_doi = normalize_doi(e.get("doi"))
        e_title = normalize_title(e.get("title") or "")
        if (norm_doi and e_doi and norm_doi == e_doi) or (norm_title and e_title and norm_title == e_title):
            abstract = e.get("abstract")
            source = e.get("source") or "semantic_scholar"
            study = estimate_study_type(abstract, title or "")
            return AbstractResult(abstract, source, doi, title, study)
    return AbstractResult(None, "MISSING_ABSTRACT", doi, title, None)


# ---------------------------------------------------------------------------
# Core fallback chain
# ---------------------------------------------------------------------------

def collect_abstract(
    *,
    doi: str | None,
    title: str | None,
    year: int | None,
    s2_client: Any | None = None,
    crossref_client: Any | None = None,
    pubmed_client: Any | None = None,
    openalex_client: Any | None = None,
    mock: bool = False,
    mock_fixtures_dir: Path | None = None,
) -> AbstractResult:
    """Try S2 → CrossRef → PubMed → OpenAlex. First non-empty abstract wins.

    `mock=True` reads fixture JSON instead of issuing network calls; injected
    clients (`s2_client`, etc.) take precedence over default instantiation for tests.
    """
    if mock:
        fixtures = mock_fixtures_dir or (_HERE / "fixtures")
        return _load_mock_fixture(fixtures, doi, title)

    # Lazy-instantiate real clients if not injected
    s2 = s2_client if s2_client is not None else SemanticScholarClient()
    crossref = crossref_client if crossref_client is not None else CrossRefClient()
    pubmed = pubmed_client if pubmed_client is not None else PubMedClient()
    openalex = openalex_client if openalex_client is not None else OpenAlexClient()

    doi_norm = normalize_doi(doi)
    abstract: str | None = None
    source: str = "MISSING_ABSTRACT"
    title_used: str | None = None

    def _abstract_plausible(abstract_text: str, title_text: str | None) -> bool:
        """Sanity check: does the abstract share at least 1 significant word with the title?

        When an API returns the wrong paper's abstract (as happened with Djebbara 2019 /
        S2 DOI lookup), the abstract will share essentially no vocabulary with the title.
        This is a necessary-but-not-sufficient check — it catches gross mismatches only.
        """
        if not abstract_text or not title_text:
            return True  # can't check; accept
        title_words = {w.lower().strip(".,;:") for w in title_text.split() if len(w) >= 5}
        if not title_words:
            return True  # title too short to validate; accept
        abstract_words = abstract_text.lower()
        return any(w in abstract_words for w in title_words)

    # Step 1: S2 by DOI — plausibility check guards against wrong-paper returns
    if doi_norm:
        try:
            r = s2.fetch_by_doi(doi_norm)
            if r.status == FetchStatus.SUCCESS and r.metadata and r.metadata.abstract:
                candidate = r.metadata.abstract
                if _abstract_plausible(candidate, title):
                    abstract, source = candidate, "semantic_scholar"
                # If plausibility fails, fall through — API returned wrong paper for this DOI
        except Exception:
            pass

    # Step 2: S2 by title — title search already matches on title; no plausibility check needed
    if abstract is None and title:
        try:
            hits = s2.search(title, max_results=1)
            if hits and hits[0].abstract:
                abstract, source = hits[0].abstract, "semantic_scholar"
                title_used = title
        except Exception:
            pass

    # Step 3: CrossRef by DOI
    if abstract is None and doi_norm:
        try:
            r = crossref.fetch(doi_norm)
            if r.status == FetchStatus.SUCCESS and r.metadata and r.metadata.abstract:
                abstract, source = r.metadata.abstract, "crossref"
        except Exception:
            pass

    # Step 4: PubMed by DOI (best-effort)
    if abstract is None and doi_norm:
        try:
            r = pubmed.fetch(doi_norm)
            if r.status == FetchStatus.SUCCESS and r.metadata and r.metadata.abstract:
                abstract, source = r.metadata.abstract, "pubmed"
        except Exception:
            pass

    # Step 5: PubMed by title+year
    if abstract is None and title and year:
        try:
            hits = pubmed.search(f"{title}[Title] {year}[PDAT]", max_results=1)
            if hits and hits[0].abstract:
                abstract, source = hits[0].abstract, "pubmed"
                title_used = title
        except Exception:
            pass

    # Step 6: OpenAlex by DOI
    if abstract is None and doi_norm:
        try:
            a = openalex.fetch_abstract_by_doi(doi_norm)
            if a:
                abstract, source = a, "openalex"
        except Exception:
            pass

    # Step 7: OpenAlex by title+year
    if abstract is None and title:
        try:
            a = openalex.fetch_abstract_by_title_year(title, year)
            if a:
                abstract, source = a, "openalex"
                title_used = title
        except Exception:
            pass

    study_type = estimate_study_type(abstract, title or "") if (abstract or title) else None
    return AbstractResult(
        abstract=abstract,
        source=source,
        doi_used=doi_norm,
        title_used=title_used,
        study_type=study_type,
    )


# ---------------------------------------------------------------------------
# DB orchestration
# ---------------------------------------------------------------------------

def run_collection(
    *,
    db_path: Path,
    run_id: str,
    max_candidates: int | None = None,
    mock: bool = False,
    mock_fixtures_dir: Path | None = None,
    dry_run: bool = False,
    clients: dict[str, Any] | None = None,
) -> CollectorReport:
    """Walk every `triage_stage='abstract_pending'` row through the fallback chain."""
    clients = clients or {}
    report = CollectorReport(run_id=run_id, started_at=utc_now_iso())

    # Pick the connection. dry_run → in-memory copy; else real file.
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
            "SELECT reference_id, doi, title_raw, publication_year "
            "FROM article_references WHERE triage_stage = 'abstract_pending' "
            "ORDER BY reference_id"
        ).fetchall()
        if max_candidates is not None:
            candidates = candidates[:max_candidates]

        total = len(candidates)
        for i, row in enumerate(candidates, start=1):
            report.candidates_processed += 1
            had_doi = bool(row["doi"])
            if had_doi:
                report.doi_processed += 1

            try:
                result = collect_abstract(
                    doi=row["doi"],
                    title=row["title_raw"],
                    year=row["publication_year"],
                    s2_client=clients.get("s2"),
                    crossref_client=clients.get("crossref"),
                    pubmed_client=clients.get("pubmed"),
                    openalex_client=clients.get("openalex"),
                    mock=mock,
                    mock_fixtures_dir=mock_fixtures_dir,
                )
            except Exception as exc:
                report.errors.append({
                    "reference_id": row["reference_id"],
                    "stage": "collect_abstract",
                    "error": str(exc),
                })
                continue

            if result.abstract:
                report.abstracts_found += 1
                if had_doi:
                    report.doi_with_abstract += 1
            else:
                report.missing_abstracts += 1

            report.source_breakdown[result.source] = report.source_breakdown.get(result.source, 0) + 1
            study_key = result.study_type or "(none)"
            report.study_type_breakdown[study_key] = report.study_type_breakdown.get(study_key, 0) + 1

            # Per-row atomic commit (UPDATE + INSERT lifecycle_transitions) so progress is
            # durable. If the process is killed mid-run, already-collected abstracts survive
            # and the next run resumes from where we left off (idempotency guard in WHERE clause).
            try:
                with conn:
                    _write_back(conn, row["reference_id"], result, run_id)
            except Exception as exc:
                report.errors.append({
                    "reference_id": row["reference_id"],
                    "stage": "write_back",
                    "error": str(exc),
                })
                continue

            # Per-row progress log so a slow run is visible from outside
            print(
                f"[{i}/{total}] {row['reference_id']} → {result.source} "
                f"(found={report.abstracts_found} missing={report.missing_abstracts})",
                file=sys.stderr, flush=True,
            )
    finally:
        conn.close()

    report.ended_at = utc_now_iso()
    return report


def _write_back(conn: sqlite3.Connection, reference_id: str, result: AbstractResult, run_id: str) -> None:
    """Update the row + log a transition in one transaction."""
    now = utc_now_iso()
    if result.abstract:
        conn.execute(
            """
            UPDATE article_references
               SET abstract_text = ?, abstract_source = ?,
                   triage_stage = 'abstract_collected', updated_at = ?
             WHERE reference_id = ? AND triage_stage = 'abstract_pending'
            """,
            (result.abstract, result.source, now, reference_id),
        )
        to_stage = "abstract_collected"
        reason = f"abstract_source:{result.source}"
    else:
        conn.execute(
            """
            UPDATE article_references
               SET abstract_text = NULL, abstract_source = 'MISSING_ABSTRACT',
                   triage_stage = 'abstract_missing',
                   triage_decision = 'MISSING_ABSTRACT',
                   triage_reason = 'no_abstract_from_any_source',
                   updated_at = ?
             WHERE reference_id = ? AND triage_stage = 'abstract_pending'
            """,
            (now, reference_id),
        )
        to_stage = "abstract_missing"
        reason = "abstract_source:MISSING_ABSTRACT"

    conn.execute(
        """
        INSERT INTO lifecycle_transitions
          (reference_id, run_id, from_stage, to_stage, reason, created_by)
        VALUES (?, ?, 'abstract_pending', ?, ?, 'abstract_collector')
        """,
        (reference_id, run_id, to_stage, reason),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Phase 4 Stage 2A abstract collector")
    parser.add_argument("--db", default=str(_HERE.parent / "task3_pipeline_lifecycle.db"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--mock-fixtures-dir", default=str(_HERE / "fixtures"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default=str(_HERE / "abstract_collection_report.json"))
    args = parser.parse_args(argv)

    run_id = args.run_id or f"RUN-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    report = run_collection(
        db_path=Path(args.db),
        run_id=run_id,
        max_candidates=args.max_candidates,
        mock=args.mock,
        mock_fixtures_dir=Path(args.mock_fixtures_dir) if args.mock_fixtures_dir else None,
        dry_run=args.dry_run,
    )

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(
        f"[abstract_collector] processed={report.candidates_processed} "
        f"found={report.abstracts_found} missing={report.missing_abstracts} "
        f"hit_rate={report.hit_rate:.1%} hit_rate_doi_only={report.hit_rate_doi_only:.1%}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
