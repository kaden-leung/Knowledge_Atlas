"""Shared mutation path for both Phase 3 writers (db_loader, reference_harvester).

Every INSERT or UPDATE to `article_references` MUST go through
`insert_or_dedupe_reference()`. Direct `conn.execute("INSERT INTO article_references ...")`
calls are forbidden — verified by a linter test that AST-scans Phase 3 code.

See SCHEMA_CONTRACT.md §8 for the decision tree.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Wire up Article_Finder so we can reuse normalize_doi / normalize_title
_HERE = Path(__file__).resolve().parent
_COGS160 = _HERE.parents[2]
_AF_ROOT = _COGS160 / "Article_Finder"
if str(_AF_ROOT) not in sys.path:
    sys.path.insert(0, str(_AF_ROOT))

from core.ae_corpus_dedupe import (  # noqa: E402
    normalize_doi as _af_normalize_doi,
    normalize_title,
)


# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------

DISCOVERED_VIA_ENUM = frozenset({
    "review_pdf_extract",
    "serpapi_scholar",
    "scholarly_search",
    "paperscraper_search",
    "openalex_expansion",
    "crossref_search",
    "student_upload",
})

CREATED_BY_ENUM = frozenset({
    "db_loader",
    "reference_harvester",
    "abstract_collector",
    "abstract_triage",
    "pdf_acquirer",
    "manual_edit",
})

TITLE_JACCARD_THRESHOLD = 0.92


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """A candidate paper from either writer. All fields except title_raw + discovered_via are optional."""
    title_raw: str
    discovered_via: str                           # one of DISCOVERED_VIA_ENUM
    doi: str | None = None
    first_author_surname: str | None = None
    publication_year: int | None = None
    venue: str | None = None
    raw_citation: str | None = None
    snippet: str | None = None
    discovered_from_paper_id: str | None = None
    discovered_query: str | None = None
    voi_score: float | None = None


@dataclass
class DedupeOutcome:
    """Result of one insert_or_dedupe_reference call."""
    reference_id: str
    action: str                                    # 'inserted' | 'merged_doi' | 'merged_title' | 'enriched_doi' | 'corpus_duplicate'
    reason: str                                    # the lifecycle_transitions.reason value emitted


@dataclass
class CorpusEntry:
    """One row from pdf_identity_inventory_local.csv."""
    paper_id: str
    doi: str
    title_normalized: str


@dataclass
class CorpusSnapshot:
    """Read-only mirror of pdf_identity_inventory (header-only stub on this machine)."""
    by_doi: dict[str, CorpusEntry] = field(default_factory=dict)
    by_title: dict[str, CorpusEntry] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A valid DOI must have the registrant prefix (4+ digits), a slash, and at least
# 3 non-whitespace characters in the suffix. Strings like "10.1016/j" (truncated
# Elsevier prefix) have a single-char suffix and are treated as absent so they
# don't waste API calls or pollute the DOI unique index.
_VALID_DOI_RE = re.compile(r"^10\.\d{4,9}/\S{3,}")


def normalize_doi(value: str | None) -> str | None:
    """Wrap ae_corpus_dedupe.normalize_doi; return None for empty or malformed DOIs."""
    result = _af_normalize_doi(value)
    if not result:
        return None
    if not _VALID_DOI_RE.match(result):
        return None
    return result


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def title_jaccard(a: str, b: str) -> float:
    """Token-set Jaccard similarity. Returns 0.0 on empty input."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def merge_discovered_via(existing: str, incoming: str) -> str:
    """Sorted unique comma-joined merge of the two values."""
    tokens = set(t.strip() for t in existing.split(",") if t.strip())
    for t in incoming.split(","):
        t = t.strip()
        if t:
            tokens.add(t)
    return ", ".join(sorted(tokens))


def mint_reference_id(conn: sqlite3.Connection, now: datetime | None = None) -> str:
    """Generate the next reference_id for today's date prefix.

    Format: REF-YYYY-MM-DD-NNNNNN. Counter resets per UTC date.
    """
    today = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    prefix = f"REF-{today}-"
    # len(prefix) == 15; SQLite SUBSTR is 1-indexed so the counter starts at position 16
    assert len(prefix) == 15, f"Reference ID prefix length changed; update SUBSTR position. Got {len(prefix)}"
    row = conn.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTR(reference_id, 16) AS INTEGER)), 0) + 1 "
        "FROM article_references WHERE reference_id LIKE ?",
        (f"{prefix}%",),
    ).fetchone()
    next_n = row[0]
    return f"{prefix}{next_n:06d}"


def load_corpus_snapshot(csv_path: Path) -> CorpusSnapshot:
    """Load the existing-corpus dedupe snapshot from CSV. Header-only file returns empty snapshot."""
    snap = CorpusSnapshot()
    if not csv_path.exists():
        return snap
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            paper_id = (row.get("paper_id") or "").strip()
            doi = normalize_doi(row.get("doi")) or ""
            title_norm = normalize_title(row.get("title") or row.get("title_normalized") or "")
            if not paper_id:
                continue
            entry = CorpusEntry(paper_id=paper_id, doi=doi, title_normalized=title_norm)
            if doi:
                snap.by_doi[doi] = entry
            if title_norm:
                snap.by_title[title_norm] = entry
    return snap


# ---------------------------------------------------------------------------
# The single mutation path
# ---------------------------------------------------------------------------

def insert_or_dedupe_reference(
    candidate: Candidate,
    conn: sqlite3.Connection,
    *,
    run_id: str,
    created_by: str,
    corpus_snapshot: CorpusSnapshot | None = None,
    now: datetime | None = None,
) -> DedupeOutcome:
    """Implements SCHEMA_CONTRACT.md §8 decision tree.

    All mutations happen within the caller's open transaction. Caller commits.
    """
    # ---- Step 1: validate enums ----
    for token in candidate.discovered_via.split(","):
        token = token.strip()
        if token and token not in DISCOVERED_VIA_ENUM:
            raise ValueError(
                f"Unknown discovered_via token: {token!r}. "
                f"Allowed: {sorted(DISCOVERED_VIA_ENUM)}"
            )
    if created_by not in CREATED_BY_ENUM:
        raise ValueError(
            f"Unknown created_by: {created_by!r}. Allowed: {sorted(CREATED_BY_ENUM)}"
        )

    doi_norm = normalize_doi(candidate.doi)
    title_norm = normalize_title(candidate.title_raw)
    discovered_at = utc_now_iso()

    # ---- BRANCH A: DOI exact match within article_references ----
    if doi_norm:
        row = conn.execute(
            "SELECT reference_id, discovered_via, triage_stage FROM article_references WHERE doi = ?",
            (doi_norm,),
        ).fetchone()
        if row:
            ref_id, existing_via, existing_stage = row
            new_via = merge_discovered_via(existing_via, candidate.discovered_via)
            if new_via != existing_via:
                conn.execute(
                    "UPDATE article_references SET discovered_via = ?, updated_at = ? WHERE reference_id = ?",
                    (new_via, utc_now_iso(), ref_id),
                )
            reason = f"provenance_merge:{candidate.discovered_via}"
            _log_transition(conn, ref_id, run_id, existing_stage, existing_stage, reason, created_by)
            return DedupeOutcome(reference_id=ref_id, action="merged_doi", reason=reason)

    # ---- BRANCH B: Title fuzzy match against corpus snapshot ----
    if corpus_snapshot and title_norm:
        # Exact normalized-title hit first (fast path)
        corpus_hit = corpus_snapshot.by_title.get(title_norm)
        if corpus_hit is None:
            # Fall back to Jaccard scan
            for corpus_title, entry in corpus_snapshot.by_title.items():
                if title_jaccard(title_norm, corpus_title) >= TITLE_JACCARD_THRESHOLD:
                    corpus_hit = entry
                    break
        if corpus_hit is not None:
            new_id = mint_reference_id(conn, now)
            _insert_new_row(
                conn, new_id, candidate, doi_norm, title_norm, run_id, discovered_at,
                triage_stage="duplicate",
                triage_decision="DUPLICATE",
                triage_reason=f"matches_existing_corpus:{corpus_hit.paper_id}",
            )
            reason = f"corpus_match:{corpus_hit.paper_id}"
            _log_transition(conn, new_id, run_id, None, "duplicate", reason, created_by)
            return DedupeOutcome(reference_id=new_id, action="corpus_duplicate", reason=reason)

    # ---- Title-based intra-table lookup (used by branches C and D) ----
    intra_title_hit = None
    if title_norm:
        # Fast path: exact normalized title
        row = conn.execute(
            "SELECT reference_id, doi, discovered_via, triage_stage, title_normalized "
            "FROM article_references WHERE title_normalized = ?",
            (title_norm,),
        ).fetchone()
        if row:
            intra_title_hit = row
        else:
            # Slower path: Jaccard scan over title_normalized index
            for row in conn.execute(
                "SELECT reference_id, doi, discovered_via, triage_stage, title_normalized "
                "FROM article_references"
            ):
                if title_jaccard(title_norm, row[4]) >= TITLE_JACCARD_THRESHOLD:
                    intra_title_hit = row
                    break

    # ---- BRANCH C: Late DOI arrival on a DOI-null intra-table row ----
    if doi_norm and intra_title_hit is not None and intra_title_hit[1] is None:
        ref_id, _, existing_via, existing_stage, _ = intra_title_hit
        new_via = merge_discovered_via(existing_via, candidate.discovered_via)
        conn.execute(
            "UPDATE article_references SET doi = ?, discovered_via = ?, updated_at = ? WHERE reference_id = ?",
            (doi_norm, new_via, utc_now_iso(), ref_id),
        )
        reason = f"doi_enriched_via_{candidate.discovered_via}"
        _log_transition(conn, ref_id, run_id, existing_stage, existing_stage, reason, created_by)
        return DedupeOutcome(reference_id=ref_id, action="enriched_doi", reason=reason)

    # ---- BRANCH D: Title fuzzy match within article_references ----
    if intra_title_hit is not None:
        ref_id, _, existing_via, existing_stage, _ = intra_title_hit
        new_via = merge_discovered_via(existing_via, candidate.discovered_via)
        if new_via != existing_via:
            conn.execute(
                "UPDATE article_references SET discovered_via = ?, updated_at = ? WHERE reference_id = ?",
                (new_via, utc_now_iso(), ref_id),
            )
        reason = f"provenance_merge_via_title:{candidate.discovered_via}"
        _log_transition(conn, ref_id, run_id, existing_stage, existing_stage, reason, created_by)
        return DedupeOutcome(reference_id=ref_id, action="merged_title", reason=reason)

    # ---- BRANCH E: Fresh insert ----
    new_id = mint_reference_id(conn, now)
    _insert_new_row(
        conn, new_id, candidate, doi_norm, title_norm, run_id, discovered_at,
        triage_stage="metadata_only",
    )
    reason = f"initial_insert:{candidate.discovered_via}"
    _log_transition(conn, new_id, run_id, None, "metadata_only", reason, created_by)
    return DedupeOutcome(reference_id=new_id, action="inserted", reason=reason)


# ---------------------------------------------------------------------------
# Internal write helpers (the only places that touch article_references / lifecycle_transitions
# besides UPDATE branches above)
# ---------------------------------------------------------------------------

def _insert_new_row(
    conn: sqlite3.Connection,
    reference_id: str,
    candidate: Candidate,
    doi_norm: str | None,
    title_norm: str,
    run_id: str,
    discovered_at: str,
    *,
    triage_stage: str,
    triage_decision: str | None = None,
    triage_reason: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO article_references (
            reference_id, doi, title_raw, title_normalized,
            first_author_surname, publication_year, venue,
            raw_citation, snippet,
            discovered_via, discovered_from_paper_id, discovered_query,
            discovery_run_id, discovered_at,
            triage_stage, triage_decision, triage_reason,
            voi_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reference_id, doi_norm, candidate.title_raw, title_norm,
            candidate.first_author_surname, candidate.publication_year, candidate.venue,
            candidate.raw_citation, candidate.snippet,
            candidate.discovered_via, candidate.discovered_from_paper_id, candidate.discovered_query,
            run_id, discovered_at,
            triage_stage, triage_decision, triage_reason,
            candidate.voi_score,
        ),
    )


def _log_transition(
    conn: sqlite3.Connection,
    reference_id: str,
    run_id: str,
    from_stage: str | None,
    to_stage: str,
    reason: str,
    created_by: str,
) -> None:
    if created_by not in CREATED_BY_ENUM:
        raise ValueError(
            f"Unknown created_by: {created_by!r}. Allowed: {sorted(CREATED_BY_ENUM)}"
        )
    conn.execute(
        """
        INSERT INTO lifecycle_transitions
          (reference_id, run_id, from_stage, to_stage, reason, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (reference_id, run_id, from_stage, to_stage, reason, created_by),
    )
