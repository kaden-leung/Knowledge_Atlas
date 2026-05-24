"""Support-set capture for the dependency overseer.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §3.2 (table) §8 (builder use)
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (B3, B4)

Every computed value records the set of artefacts used to compute it.
Members carry the member's hash at capture time so that future recomputation
can detect drift.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from overseer.ids import support_set_id_for, utc_now_iso


def compute_support_set_hash(members: list[tuple[str, str]]) -> str:
    """SHA-256 over the sorted (artefact_id, hash) pairs."""
    sorted_pairs = sorted((str(a), str(h)) for a, h in members)
    canonical = json.dumps(
        sorted_pairs, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def capture(
    conn: sqlite3.Connection,
    members: list[tuple[str, str]],
) -> str:
    """Insert a support set (idempotent on support_set_id derived from members).

    members is a list of (member_artefact_id, member_hash_at_capture) pairs.
    Returns the support_set_id (deterministic).
    """
    ssid = support_set_id_for(members)
    sshash = compute_support_set_hash(members)
    now = utc_now_iso()

    members_json = json.dumps(
        sorted([{"artefact_id": a, "hash": h} for a, h in members],
               key=lambda d: (d["artefact_id"], d["hash"])),
        separators=(",", ":"),
        ensure_ascii=False,
    )

    cur = conn.execute(
        """
        INSERT OR IGNORE INTO support_sets (
            support_set_id, support_set_hash, members_json, created_at
        ) VALUES (?, ?, ?, ?)
        """,
        (ssid, sshash, members_json, now),
    )
    if cur.rowcount > 0:
        # First time we see this support set; insert members.
        for member_artefact_id, member_hash in members:
            conn.execute(
                """
                INSERT OR IGNORE INTO support_set_members (
                    support_set_id, member_artefact_id, member_hash_at_capture
                ) VALUES (?, ?, ?)
                """,
                (ssid, member_artefact_id, member_hash),
            )
    return ssid


def get_members(
    conn: sqlite3.Connection, support_set_id: str
) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT member_artefact_id, member_hash_at_capture
        FROM support_set_members
        WHERE support_set_id = ?
        ORDER BY member_artefact_id
        """,
        (support_set_id,),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def get_hash(conn: sqlite3.Connection, support_set_id: str) -> str | None:
    row = conn.execute(
        "SELECT support_set_hash FROM support_sets WHERE support_set_id = ?",
        (support_set_id,),
    ).fetchone()
    return row[0] if row else None
