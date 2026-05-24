"""CRUD for the open-vocabulary registry.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §3.4
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P26)

Open vocabularies (method/measure/instrument/construct/abstract-source labels)
accept new values on first sight with provenance. New values land as
'candidate'; the seed script populates 'canonical' entries from PsychoPy and
related libraries. A periodic normalization job (Phase 1 deterministic,
Phase 3 LLM-aided) links candidates to canonicals via review_status='synonym'
and canonical_value pointing at the canonical row.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from overseer.ids import utc_now_iso, vocab_value_id


@dataclass(frozen=True)
class VocabRow:
    value_id: str
    kind: str
    value: str
    canonical_value: str | None
    first_seen_in_paper: str | None
    first_observed_at: str
    first_observed_build_run_id: str | None
    review_status: str
    canonicalization_source: str | None
    seeded_from: str | None


def _row(r: sqlite3.Row | tuple) -> VocabRow:
    if isinstance(r, sqlite3.Row):
        return VocabRow(
            value_id=r["value_id"],
            kind=r["kind"],
            value=r["value"],
            canonical_value=r["canonical_value"],
            first_seen_in_paper=r["first_seen_in_paper"],
            first_observed_at=r["first_observed_at"],
            first_observed_build_run_id=r["first_observed_build_run_id"],
            review_status=r["review_status"],
            canonicalization_source=r["canonicalization_source"],
            seeded_from=r["seeded_from"],
        )
    return VocabRow(*r)


def get(conn: sqlite3.Connection, kind: str, value: str) -> VocabRow | None:
    row = conn.execute(
        "SELECT * FROM vocabulary_registry WHERE kind = ? AND value = ?",
        (kind, value),
    ).fetchone()
    return _row(row) if row else None


def add_candidate(
    conn: sqlite3.Connection,
    *,
    kind: str,
    value: str,
    first_seen_in_paper: str | None,
    first_observed_build_run_id: str | None,
) -> VocabRow:
    """Insert a new candidate row if not present. Returns the row (new or existing).

    Idempotent: if (kind, value) already exists, returns the existing row unchanged.
    """
    existing = get(conn, kind, value)
    if existing is not None:
        return existing
    vid = vocab_value_id(kind, value)
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO vocabulary_registry (
            value_id, kind, value, canonical_value, first_seen_in_paper,
            first_observed_at, first_observed_build_run_id, review_status,
            canonicalization_source, seeded_from
        ) VALUES (?, ?, ?, NULL, ?, ?, ?, 'candidate', NULL, NULL)
        """,
        (vid, kind, value, first_seen_in_paper, now, first_observed_build_run_id),
    )
    return get(conn, kind, value)


def list_canonicals(conn: sqlite3.Connection, kind: str) -> list[VocabRow]:
    rows = conn.execute(
        """
        SELECT * FROM vocabulary_registry
        WHERE kind = ? AND review_status = 'canonical'
        ORDER BY value
        """,
        (kind,),
    ).fetchall()
    return [_row(r) for r in rows]


def list_candidates(conn: sqlite3.Connection, kind: str) -> list[VocabRow]:
    rows = conn.execute(
        """
        SELECT * FROM vocabulary_registry
        WHERE kind = ? AND review_status = 'candidate'
        ORDER BY first_observed_at
        """,
        (kind,),
    ).fetchall()
    return [_row(r) for r in rows]


def canonical_for(conn: sqlite3.Connection, kind: str, value: str) -> str | None:
    """Resolve a value to its canonical form.

    * If the row is itself 'canonical', returns the value.
    * If the row is 'synonym', returns its canonical_value.
    * If the row is 'candidate' or 'rejected', returns None (no canonical yet).
    * If no row exists, returns None.

    Synonym chains of depth > 1 are forbidden (per the verifier check); this
    function does NOT recurse — it returns the immediate canonical_value.
    """
    row = get(conn, kind, value)
    if row is None:
        return None
    if row.review_status == "canonical":
        return row.value
    if row.review_status == "synonym":
        return row.canonical_value
    return None


def mark_as_synonym(
    conn: sqlite3.Connection,
    *,
    kind: str,
    value: str,
    canonical_value: str,
    canonicalization_source: str,
) -> None:
    """Promote a candidate to a synonym pointing at a canonical entry."""
    canon_row = get(conn, kind, canonical_value)
    if canon_row is None or canon_row.review_status != "canonical":
        raise ValueError(
            f"canonical_value '{canonical_value}' for kind '{kind}' is not "
            f"a canonical row in vocabulary_registry"
        )
    conn.execute(
        """
        UPDATE vocabulary_registry SET
            canonical_value = ?,
            review_status = 'synonym',
            canonicalization_source = ?
        WHERE kind = ? AND value = ?
        """,
        (canonical_value, canonicalization_source, kind, value),
    )
