"""CRUD for artefact_registry, the typed registry of overseer-tracked artefacts.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §8 (builder write path)
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P1, P2, P3, P4, P5, P24)

Fencing-token discipline (P24):
  * Every claim increments artefact_registry.current_fencing_token.
  * Writes to the artefact carry the worker's claim token.
  * The DB rejects writes whose token is less than the row's
    current_fencing_token. Implemented here via the WHERE clause on
    update_with_hashes; FencingTokenMismatch is raised on rowcount == 0.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from overseer.ids import artefact_id as derive_artefact_id, utc_now_iso


class FencingTokenMismatch(Exception):
    """Raised when a write carries a stale fencing token (P24)."""


@dataclass(frozen=True)
class Artefact:
    artefact_id: str
    kind: str
    entity_type: str
    entity_id: str
    field_path: str | None
    schema_version: str
    latest_build_run_id: str | None
    raw_hash: str | None
    semantic_hash: str | None
    current_fencing_token: int
    freshness_status: str | None
    created_at: str
    tombstoned_at: str | None
    active: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row | tuple) -> "Artefact":
        if isinstance(row, sqlite3.Row):
            return cls(
                artefact_id=row["artefact_id"],
                kind=row["kind"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                field_path=row["field_path"],
                schema_version=row["schema_version"],
                latest_build_run_id=row["latest_build_run_id"],
                raw_hash=row["raw_hash"],
                semantic_hash=row["semantic_hash"],
                current_fencing_token=row["current_fencing_token"],
                freshness_status=row["freshness_status"],
                created_at=row["created_at"],
                tombstoned_at=row["tombstoned_at"],
                active=bool(row["active"]),
            )
        # Positional fallback (in case row_factory wasn't set).
        return cls(*row[:13], active=bool(row[13]))


def register(
    conn: sqlite3.Connection,
    *,
    kind: str,
    entity_type: str,
    entity_id: str,
    field_path: str | None,
    schema_version: str,
    freshness_status: str = "unknown",
) -> Artefact:
    """Insert an artefact row if no active row exists for the natural key.

    Returns the active Artefact (the new one or the existing one).
    """
    aid = derive_artefact_id(kind, entity_id, field_path, schema_version)
    existing = get_by_entity(conn, entity_type, entity_id, field_path, schema_version)
    if existing is not None:
        return existing

    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO artefact_registry (
            artefact_id, kind, entity_type, entity_id, field_path,
            schema_version, latest_build_run_id, raw_hash, semantic_hash,
            current_fencing_token, freshness_status, created_at,
            tombstoned_at, active
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 0, ?, ?, NULL, 1)
        """,
        (aid, kind, entity_type, entity_id, field_path, schema_version,
         freshness_status, now),
    )
    return get(conn, aid)


def get(conn: sqlite3.Connection, artefact_id: str) -> Artefact | None:
    row = conn.execute(
        "SELECT * FROM artefact_registry WHERE artefact_id = ?", (artefact_id,)
    ).fetchone()
    return Artefact.from_row(row) if row else None


def get_by_entity(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    field_path: str | None,
    schema_version: str,
) -> Artefact | None:
    """Return the active artefact row matching the natural key, or None."""
    if field_path is None:
        row = conn.execute(
            """
            SELECT * FROM artefact_registry
            WHERE entity_type = ? AND entity_id = ? AND field_path IS NULL
              AND schema_version = ? AND active = 1
            """,
            (entity_type, entity_id, schema_version),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT * FROM artefact_registry
            WHERE entity_type = ? AND entity_id = ? AND field_path = ?
              AND schema_version = ? AND active = 1
            """,
            (entity_type, entity_id, field_path, schema_version),
        ).fetchone()
    return Artefact.from_row(row) if row else None


def update_with_hashes(
    conn: sqlite3.Connection,
    *,
    artefact_id: str,
    raw_hash: str,
    semantic_hash: str,
    build_run_id: str,
    fencing_token: int,
    freshness_status: str = "fresh",
) -> None:
    """Update raw_hash, semantic_hash, and latest_build_run_id.

    Validates fencing_token against the row's current_fencing_token (P24).
    Raises FencingTokenMismatch if the worker's token does not match the row's
    current token — meaning the watchdog has reclaimed this artefact since the
    worker claimed it.
    """
    cur = conn.execute(
        """
        UPDATE artefact_registry SET
            raw_hash = ?, semantic_hash = ?, latest_build_run_id = ?,
            freshness_status = ?
        WHERE artefact_id = ? AND current_fencing_token = ?
        """,
        (raw_hash, semantic_hash, build_run_id, freshness_status,
         artefact_id, fencing_token),
    )
    if cur.rowcount == 0:
        # Either the artefact does not exist, or the fencing token is stale.
        current = conn.execute(
            "SELECT current_fencing_token FROM artefact_registry WHERE artefact_id = ?",
            (artefact_id,),
        ).fetchone()
        if current is None:
            raise FencingTokenMismatch(
                f"artefact {artefact_id} does not exist"
            )
        raise FencingTokenMismatch(
            f"artefact {artefact_id}: write rejected, worker token "
            f"{fencing_token} does not match current token {current[0]}"
        )


def increment_fencing_token(conn: sqlite3.Connection, artefact_id: str) -> int:
    """Atomically bump current_fencing_token and return the new value.

    Called by rebuild_queue.claim_one() on claim and by watchdog.tick() on
    reclaim. The returned value becomes the claim's fencing_token.
    """
    cur = conn.execute(
        """
        UPDATE artefact_registry
        SET current_fencing_token = current_fencing_token + 1
        WHERE artefact_id = ?
        """,
        (artefact_id,),
    )
    if cur.rowcount == 0:
        raise FencingTokenMismatch(f"artefact {artefact_id} does not exist")
    row = conn.execute(
        "SELECT current_fencing_token FROM artefact_registry WHERE artefact_id = ?",
        (artefact_id,),
    ).fetchone()
    return int(row[0])


def mark_stale(conn: sqlite3.Connection, artefact_id: str) -> None:
    conn.execute(
        "UPDATE artefact_registry SET freshness_status = 'stale' WHERE artefact_id = ?",
        (artefact_id,),
    )


def mark_fresh(conn: sqlite3.Connection, artefact_id: str) -> None:
    conn.execute(
        "UPDATE artefact_registry SET freshness_status = 'fresh' WHERE artefact_id = ?",
        (artefact_id,),
    )


def tombstone(conn: sqlite3.Connection, artefact_id: str) -> None:
    """Mark an artefact tombstoned (active=0); preserves the row for audit."""
    conn.execute(
        """
        UPDATE artefact_registry
        SET active = 0, tombstoned_at = ?
        WHERE artefact_id = ?
        """,
        (utc_now_iso(), artefact_id),
    )


def list_by_kind(
    conn: sqlite3.Connection,
    kind: str,
    *,
    active_only: bool = True,
) -> list[Artefact]:
    if active_only:
        rows = conn.execute(
            "SELECT * FROM artefact_registry WHERE kind = ? AND active = 1 ORDER BY artefact_id",
            (kind,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM artefact_registry WHERE kind = ? ORDER BY artefact_id",
            (kind,),
        ).fetchall()
    return [Artefact.from_row(r) for r in rows]
