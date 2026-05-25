"""Read-only connector for the Article Finder local database.

Source authority:
    docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md §2

Article Finder lives at /Users/davidusa/REPOS/Article_Finder_v3_2_3/. Its
canonical DB is data/article_finder.db. The overseer NEVER writes to AF.
AF code is unchanged by Phase 2 — only the overseer's reading-and-syncing
contract is new.

This module exposes:
  * resolve_af_db_path() — find the live AF DB
  * connect_readonly() — open with mode=ro
  * iter_papers() — read AF.papers rows
  * paper_signature() — canonical hash for AF-vs-KA matching
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

AF_DB_PATH_CANDIDATES = (
    Path.home() / "REPOS" / "Article_Finder_v3_2_3" / "data" / "article_finder.db",
)


class ArticleFinderNotFound(FileNotFoundError):
    pass


def resolve_af_db_path(explicit: str | Path | None = None) -> Path:
    """Resolve the live AF DB path. Raises ArticleFinderNotFound if missing."""
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.exists():
            raise ArticleFinderNotFound(f"AF DB not found at {p}")
        return p
    for cand in AF_DB_PATH_CANDIDATES:
        if cand.exists() and cand.stat().st_size > 0:
            return cand
    raise ArticleFinderNotFound(
        f"AF DB not found in any of: {[str(p) for p in AF_DB_PATH_CANDIDATES]}"
    )


def connect_readonly(path: str | Path | None = None) -> sqlite3.Connection:
    """Open the AF DB read-only. mode=ro plus URI scheme."""
    db_path = resolve_af_db_path(path)
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@dataclass(frozen=True)
class ArticleFinderPaper:
    af_paper_id: str        # AF's row id (typically integer or string)
    doi: str | None
    title: str | None
    canonical_paper_id: str | None  # AF's canonical_paper_id if present
    af_status: str | None   # AF's status field, if present
    signature: str          # SHA-256 of canonical (doi, canonical_paper_id, title)
    atlas_intake_decision: str | None = None  # Stage 4 decision; new in 2026-05-24
    ae_corpus_match_status: str | None = None  # Stage 10 result; new in 2026-05-24


def paper_signature(
    *,
    doi: str | None,
    canonical_paper_id: str | None,
    title: str | None,
) -> str:
    """Stable signature for AF↔KA matching.

    Canonicalization: each field stripped + lowercased + None→empty.
    Reconciler uses this to detect drift; minor formatting differences in
    DOI or title that change semantically are caught by the signature.
    """
    def norm(v: str | None) -> str:
        if v is None:
            return ""
        return v.strip().lower()
    payload = json.dumps(
        [norm(doi), norm(canonical_paper_id), norm(title)],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _columns_of(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def iter_papers(
    conn: sqlite3.Connection,
    *,
    af_status_filter: str | None = "accepted",
    atlas_intake_decision_filter: str | None = None,
    limit: int | None = None,
) -> Iterator[ArticleFinderPaper]:
    """Iterate AF.papers rows. Yields ArticleFinderPaper records.

    Filter parameters (AND-combined):
      * af_status_filter — match on AF.papers.status (legacy; default 'accepted'
        which was the Phase 2 semantic). Pass None to disable.
      * atlas_intake_decision_filter — match on AF.papers.atlas_intake_decision.
        Recommended production value: 'accept_candidate' (754 rows on live AF
        as of 2026-05-24). Pass None to disable. New in 2026-05-24.

    The function is defensive about AF schema variation: if AF.papers lacks
    a named column, the corresponding value is None and signature still
    computes from whatever fields are available.
    """
    cols = _columns_of(conn, "papers")
    select_cols = ["rowid"]
    for c in ("doi", "title", "canonical_paper_id", "status",
              "atlas_intake_decision", "ae_corpus_match_status"):
        if c in cols:
            select_cols.append(c)
    sql = f"SELECT {', '.join(select_cols)} FROM papers"
    where_parts: list[str] = []
    params: list = []
    if af_status_filter is not None and "status" in cols:
        where_parts.append("LOWER(status) = ?")
        params.append(af_status_filter.lower())
    if atlas_intake_decision_filter is not None and "atlas_intake_decision" in cols:
        where_parts.append("LOWER(atlas_intake_decision) = ?")
        params.append(atlas_intake_decision_filter.lower())
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql, params).fetchall()
    for r in rows:
        d = dict(r)
        doi = d.get("doi")
        title = d.get("title")
        canon = d.get("canonical_paper_id")
        status = d.get("status")
        sig = paper_signature(doi=doi, canonical_paper_id=canon, title=title)
        yield ArticleFinderPaper(
            af_paper_id=str(d.get("rowid")),
            doi=doi,
            title=title,
            canonical_paper_id=canon,
            af_status=status,
            signature=sig,
            atlas_intake_decision=d.get("atlas_intake_decision"),
            ae_corpus_match_status=d.get("ae_corpus_match_status"),
        )


def schema_version(conn: sqlite3.Connection) -> str | None:
    """Read AF's schema_version table, if present."""
    try:
        row = conn.execute(
            "SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
