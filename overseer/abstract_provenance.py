"""Abstract-source provenance enforcement.

Source authority:
    docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md §6
    docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md §10 (companion)

Allowed abstract sources are seeded in vocabulary_registry with kind
'abstract_source_label' during Phase 1 (see psychopy_seed.json). Phase 2
enforces that every abstract artefact's content carries an
'abstract_source' field whose value resolves in vocabulary_registry.
"""

from __future__ import annotations

import sqlite3

from overseer.vocabulary_registry import canonical_for, get


ABSTRACT_SOURCE_KIND = "abstract_source_label"


class UnknownAbstractSourceError(ValueError):
    pass


def is_allowed_source(conn: sqlite3.Connection, source_label: str) -> bool:
    """Return True iff source_label resolves in vocabulary_registry."""
    if not source_label:
        return False
    row = get(conn, ABSTRACT_SOURCE_KIND, source_label)
    if row is None:
        return False
    return row.review_status in ("canonical", "synonym")


def canonical_source(conn: sqlite3.Connection, source_label: str) -> str | None:
    """Return the canonical source label for a given value, or None.

    * If the label is itself canonical, returns it.
    * If it is a synonym, returns the canonical it points at.
    * If it is missing or a candidate, returns None.
    """
    return canonical_for(conn, ABSTRACT_SOURCE_KIND, source_label)


def require_allowed_source(conn: sqlite3.Connection, source_label: str) -> str:
    """Return the canonical source label or raise UnknownAbstractSourceError.

    Use this at the abstract-artefact write site: every abstract MUST have a
    resolvable abstract_source per P26 / companion contract §10.
    """
    canon = canonical_source(conn, source_label)
    if canon is None:
        raise UnknownAbstractSourceError(
            f"abstract_source {source_label!r} is not a canonical entry in "
            f"vocabulary_registry (kind={ABSTRACT_SOURCE_KIND}). Allowed sources "
            f"are seeded from contracts/schemas/dependency_overseer/psychopy_seed.json."
        )
    return canon


def list_allowed_sources(conn: sqlite3.Connection) -> list[str]:
    """Return canonical abstract source labels currently registered."""
    rows = conn.execute(
        """
        SELECT value FROM vocabulary_registry
        WHERE kind = ? AND review_status = 'canonical'
        ORDER BY value
        """,
        (ABSTRACT_SOURCE_KIND,),
    ).fetchall()
    return [r[0] for r in rows]
