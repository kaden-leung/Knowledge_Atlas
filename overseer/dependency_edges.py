"""CRUD for dependency_edges between artefacts.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §3.2
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (B3, B4, P5)

edge_kind enum: supports, derived_from, depends_on, grounds.
"""

from __future__ import annotations

import hashlib
import sqlite3

from overseer.ids import utc_now_iso

ALLOWED_EDGE_KINDS = frozenset({"supports", "derived_from", "depends_on", "grounds"})


def _edge_hash(parent: str, child: str, edge_kind: str) -> str:
    h = hashlib.sha256(
        f"{parent}\x1f{child}\x1f{edge_kind}".encode("utf-8")
    ).hexdigest()
    return "sha256:" + h


def add_edge(
    conn: sqlite3.Connection,
    *,
    parent_artefact_id: str,
    child_artefact_id: str,
    edge_kind: str,
) -> None:
    """Insert an edge if not already present. Tombstoned edges are revived
    (active again) by clearing tombstoned_at; this keeps the row identity stable.
    """
    if edge_kind not in ALLOWED_EDGE_KINDS:
        raise ValueError(
            f"edge_kind '{edge_kind}' not in {sorted(ALLOWED_EDGE_KINDS)}"
        )
    now = utc_now_iso()
    eh = _edge_hash(parent_artefact_id, child_artefact_id, edge_kind)
    conn.execute(
        """
        INSERT INTO dependency_edges (
            parent_artefact_id, child_artefact_id, edge_kind, edge_hash,
            created_at, tombstoned_at
        ) VALUES (?, ?, ?, ?, ?, NULL)
        ON CONFLICT(parent_artefact_id, child_artefact_id, edge_kind) DO UPDATE
        SET tombstoned_at = NULL
        """,
        (parent_artefact_id, child_artefact_id, edge_kind, eh, now),
    )


def tombstone_edge(
    conn: sqlite3.Connection,
    *,
    parent_artefact_id: str,
    child_artefact_id: str,
    edge_kind: str,
) -> None:
    conn.execute(
        """
        UPDATE dependency_edges SET tombstoned_at = ?
        WHERE parent_artefact_id = ? AND child_artefact_id = ? AND edge_kind = ?
        """,
        (utc_now_iso(), parent_artefact_id, child_artefact_id, edge_kind),
    )


def parents_of(
    conn: sqlite3.Connection,
    child_artefact_id: str,
    edge_kind: str | None = None,
) -> list[str]:
    """List active parent artefact_ids for a given child."""
    if edge_kind is None:
        rows = conn.execute(
            """
            SELECT parent_artefact_id FROM dependency_edges
            WHERE child_artefact_id = ? AND tombstoned_at IS NULL
            """,
            (child_artefact_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT parent_artefact_id FROM dependency_edges
            WHERE child_artefact_id = ? AND edge_kind = ? AND tombstoned_at IS NULL
            """,
            (child_artefact_id, edge_kind),
        ).fetchall()
    return [r[0] for r in rows]


def children_of(
    conn: sqlite3.Connection,
    parent_artefact_id: str,
    edge_kind: str | None = None,
) -> list[str]:
    """List active child artefact_ids for a given parent."""
    if edge_kind is None:
        rows = conn.execute(
            """
            SELECT child_artefact_id FROM dependency_edges
            WHERE parent_artefact_id = ? AND tombstoned_at IS NULL
            """,
            (parent_artefact_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT child_artefact_id FROM dependency_edges
            WHERE parent_artefact_id = ? AND edge_kind = ? AND tombstoned_at IS NULL
            """,
            (parent_artefact_id, edge_kind),
        ).fetchall()
    return [r[0] for r in rows]
