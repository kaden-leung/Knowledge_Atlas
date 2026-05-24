"""Heartbeat-based reclaim of stuck workers.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §9 watchdog
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P7, P24)

The watchdog tick:
  * Identifies worker_heartbeats rows whose last_heartbeat_at exceeds
    heartbeat_timeout_seconds (Phase 1 liveness-only; P25 progress-marker
    detection lands in Phase 2).
  * For each stale worker holding a claim:
      - Increments artefact_registry.current_fencing_token (P24) — invalidating
        any pending writes the dead worker might still attempt.
      - Resets the queue row to 'queued' (or 'quarantine' if attempt_count
        crosses the threshold), clearing lease_owner and claimed_at.
      - Increments attempt_count.
      - Adds a completion_queue row if the claim moves to 'quarantine'.
  * Deletes the worker_heartbeats row (the worker is presumed gone).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from overseer.artefact_registry import increment_fencing_token
from overseer.db import transaction
from overseer.ids import utc_now_iso
from overseer.rebuild_queue import MAX_ATTEMPTS_BEFORE_QUARANTINE


@dataclass(frozen=True)
class ReclaimedClaim:
    queue_id: str
    artefact_id: str
    worker_id: str
    new_state: str
    new_attempt_count: int
    new_fencing_token: int


def tick(
    conn: sqlite3.Connection,
    *,
    max_attempts: int = MAX_ATTEMPTS_BEFORE_QUARANTINE,
) -> list[ReclaimedClaim]:
    """Run one watchdog pass. Returns a list of reclaimed claims."""
    reclaimed: list[ReclaimedClaim] = []
    with transaction(conn):
        # SQLite stores heartbeat_timeout_seconds per worker row. A worker is
        # stale iff now - last_heartbeat_at > heartbeat_timeout_seconds.
        rows = conn.execute(
            """
            SELECT worker_id, current_claim, heartbeat_timeout_seconds,
                   (julianday('now') - julianday(last_heartbeat_at)) * 86400.0 AS age
            FROM worker_heartbeats
            """,
        ).fetchall()
        stale = [r for r in rows if r["age"] is not None and r["age"] > r["heartbeat_timeout_seconds"]]
        for r in stale:
            worker_id = r["worker_id"]
            current_claim = r["current_claim"]
            if current_claim:
                claim_row = conn.execute(
                    "SELECT artefact_id, attempt_count FROM rebuild_queue WHERE queue_id = ?",
                    (current_claim,),
                ).fetchone()
                if claim_row is not None:
                    aid = claim_row["artefact_id"]
                    new_attempts = claim_row["attempt_count"] + 1
                    new_state = "quarantine" if new_attempts >= max_attempts else "queued"
                    new_token = increment_fencing_token(conn, aid)
                    conn.execute(
                        """
                        UPDATE rebuild_queue SET
                            state = ?, attempt_count = ?, lease_owner = NULL,
                            claimed_at = NULL, input_fingerprint_at_claim = NULL,
                            last_error = 'watchdog_reclaimed_after_heartbeat_timeout',
                            last_seen_at = ?
                        WHERE queue_id = ?
                        """,
                        (new_state, new_attempts, utc_now_iso(), current_claim),
                    )
                    if new_state == "quarantine":
                        from overseer.completion_queue import enqueue as cq_enqueue
                        cq_enqueue(
                            conn,
                            artefact_id=aid,
                            reason="rebuild_queue_quarantine_after_watchdog_reclaim",
                            severity="high",
                            next_action="human_review_required",
                        )
                    reclaimed.append(ReclaimedClaim(
                        queue_id=current_claim,
                        artefact_id=aid,
                        worker_id=worker_id,
                        new_state=new_state,
                        new_attempt_count=new_attempts,
                        new_fencing_token=new_token,
                    ))
            conn.execute(
                "DELETE FROM worker_heartbeats WHERE worker_id = ?", (worker_id,)
            )
    return reclaimed
