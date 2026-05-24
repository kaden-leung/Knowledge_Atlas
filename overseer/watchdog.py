"""Heartbeat-based reclaim of stuck workers (P7) and P25 soft-stuck routing.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §9 watchdog
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P7, P24, P25)
    docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md §8

The watchdog tick has two responsibilities:

  1. **Liveness reclaim (P7, Phase 1):** workers whose last_heartbeat_at
     exceeds heartbeat_timeout_seconds are treated as dead. For each stale
     worker holding a claim:
       - Increment artefact_registry.current_fencing_token (P24) so any
         pending writes from the dead worker are rejected at write time.
       - Reset the queue row to 'queued' (or 'quarantine' if attempt_count
         crosses the threshold) and clear lease_owner / claimed_at.
       - Add a completion_queue row when the row moves to 'quarantine'.
       - Delete the worker_heartbeats row.

  2. **Soft-stuck flagging (P25, Phase 2):** workers whose heartbeat is
     fresh but whose progress_marker has been unchanged for
     SOFT_STUCK_INTERVAL_MULTIPLIER * heartbeat_interval_seconds are flagged
     soft-stuck. A completion_queue row with severity='medium' is raised;
     the worker is NOT killed — the work may still be making slow progress.
     A second flag for the same worker+marker is rate-limited (idempotent
     via completion_queue.enqueue's artefact_id+reason de-dup).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from overseer.artefact_registry import increment_fencing_token
from overseer.db import transaction
from overseer.ids import utc_now_iso
from overseer.rebuild_queue import MAX_ATTEMPTS_BEFORE_QUARANTINE


SOFT_STUCK_INTERVAL_MULTIPLIER = 5  # P25 default: N=5 unchanged intervals.


@dataclass(frozen=True)
class ReclaimedClaim:
    queue_id: str
    artefact_id: str
    worker_id: str
    new_state: str
    new_attempt_count: int
    new_fencing_token: int


@dataclass(frozen=True)
class SoftStuckFlag:
    worker_id: str
    current_claim: str | None
    progress_marker: str
    completion_queue_id: str


def tick(
    conn: sqlite3.Connection,
    *,
    max_attempts: int = MAX_ATTEMPTS_BEFORE_QUARANTINE,
    soft_stuck_multiplier: int = SOFT_STUCK_INTERVAL_MULTIPLIER,
) -> list[ReclaimedClaim]:
    """Run one watchdog pass. Returns a list of reclaimed claims (P7)."""
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


def soft_stuck_tick(
    conn: sqlite3.Connection,
    *,
    soft_stuck_multiplier: int = SOFT_STUCK_INTERVAL_MULTIPLIER,
) -> list[SoftStuckFlag]:
    """Detect soft-stuck workers (P25): heartbeat is fresh but progress_marker
    has been unchanged for soft_stuck_multiplier * heartbeat_interval_seconds.

    Raises a 'medium' completion_queue row per stuck worker; does NOT kill the
    worker (work may still be progressing slowly). enqueue() is idempotent on
    (artefact_id, reason), so re-running the tick doesn't proliferate rows.
    """
    from overseer.completion_queue import enqueue as cq_enqueue

    flags: list[SoftStuckFlag] = []
    rows = conn.execute(
        """
        SELECT worker_id, current_claim, progress_marker,
               heartbeat_interval_seconds, heartbeat_timeout_seconds,
               (julianday('now') - julianday(last_heartbeat_at)) * 86400.0 AS hb_age,
               (julianday('now') - julianday(progress_marker_unchanged_since)) * 86400.0 AS marker_age
        FROM worker_heartbeats
        WHERE progress_marker IS NOT NULL
          AND progress_marker_unchanged_since IS NOT NULL
        """,
    ).fetchall()
    for r in rows:
        # Heartbeat must be fresh (otherwise the liveness reclaim handles it).
        hb_age = r["hb_age"] or 0
        if hb_age > r["heartbeat_timeout_seconds"]:
            continue
        threshold = soft_stuck_multiplier * r["heartbeat_interval_seconds"]
        marker_age = r["marker_age"] or 0
        if marker_age <= threshold:
            continue
        # Soft-stuck: marker has been unchanged for >= N intervals.
        artefact_id = None
        if r["current_claim"]:
            claim_row = conn.execute(
                "SELECT artefact_id FROM rebuild_queue WHERE queue_id = ?",
                (r["current_claim"],),
            ).fetchone()
            if claim_row is not None:
                artefact_id = claim_row["artefact_id"]
        cq_id = cq_enqueue(
            conn,
            reason=f"soft_stuck_progress_marker:{r['progress_marker']}",
            severity="medium",
            artefact_id=artefact_id,
            next_action="review_worker_progress",
        )
        flags.append(SoftStuckFlag(
            worker_id=r["worker_id"],
            current_claim=r["current_claim"],
            progress_marker=r["progress_marker"],
            completion_queue_id=cq_id,
        ))
    return flags
