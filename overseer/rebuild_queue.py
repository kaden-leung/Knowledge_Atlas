"""The rebuild queue: claim/heartbeat/complete/fail with fencing tokens.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §9
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P7, P24)

Lease semantics:
  * A claim holds while the owning worker's last_heartbeat_at is younger than
    heartbeat_timeout_seconds (P7).
  * Every claim increments the artefact's current_fencing_token (P24); writes
    carrying a stale token are rejected at write time (see artefact_registry
    .update_with_hashes).
  * The watchdog (see overseer.watchdog) reclaims claims whose heartbeat
    stream has gone silent.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from overseer.artefact_registry import increment_fencing_token
from overseer.db import transaction
from overseer.ids import queue_id as new_queue_id, utc_now_iso

MAX_ATTEMPTS_BEFORE_QUARANTINE = 5
ALLOWED_SEVERITIES = ("low", "medium", "high", "blocking")
_SEVERITY_RANK_SQL = (
    "CASE severity "
    "WHEN 'blocking' THEN 0 "
    "WHEN 'high' THEN 1 "
    "WHEN 'medium' THEN 2 "
    "WHEN 'low' THEN 3 "
    "ELSE 4 END"
)


@dataclass(frozen=True)
class Claim:
    queue_id: str
    artefact_id: str
    fencing_token: int
    severity: str
    reason: str | None
    attempt_count: int


def enqueue(
    conn: sqlite3.Connection,
    *,
    artefact_id: str,
    reason: str | None,
    severity: str = "medium",
) -> str:
    """Enqueue a rebuild request. Returns the queue_id.

    If an active (queued/claimed/building) item already exists for this
    artefact, returns the existing queue_id (idempotent enqueue).
    """
    if severity not in ALLOWED_SEVERITIES:
        raise ValueError(f"severity '{severity}' not in {ALLOWED_SEVERITIES}")
    existing = conn.execute(
        """
        SELECT queue_id FROM rebuild_queue
        WHERE artefact_id = ? AND state IN ('queued','claimed','building')
        LIMIT 1
        """,
        (artefact_id,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE rebuild_queue SET last_seen_at = ? WHERE queue_id = ?",
            (utc_now_iso(), existing[0]),
        )
        return existing[0]
    qid = new_queue_id()
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO rebuild_queue (
            queue_id, artefact_id, reason, severity, first_seen_at, last_seen_at,
            attempt_count, state, lease_owner, fencing_token, claimed_at,
            input_fingerprint_at_claim, last_error
        ) VALUES (?, ?, ?, ?, ?, ?, 0, 'queued', NULL, 0, NULL, NULL, NULL)
        """,
        (qid, artefact_id, reason, severity, now, now),
    )
    return qid


def claim_one(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    heartbeat_interval_seconds: int = 30,
    heartbeat_timeout_seconds: int = 300,
    input_fingerprint: str | None = None,
) -> Claim | None:
    """Atomically claim the highest-priority queued item for this worker.

    Increments artefact_registry.current_fencing_token; records the new token
    on the queue row. Upserts worker_heartbeats. Returns None if the queue
    has nothing claimable.
    """
    with transaction(conn):
        row = conn.execute(
            f"""
            SELECT queue_id, artefact_id, severity, reason, attempt_count
            FROM rebuild_queue
            WHERE state = 'queued'
            ORDER BY {_SEVERITY_RANK_SQL}, first_seen_at
            LIMIT 1
            """,
        ).fetchone()
        if row is None:
            return None
        qid, aid, severity, reason, attempts = row
        new_token = increment_fencing_token(conn, aid)
        now = utc_now_iso()
        conn.execute(
            """
            UPDATE rebuild_queue SET
                state = 'claimed', lease_owner = ?, fencing_token = ?,
                claimed_at = ?, input_fingerprint_at_claim = ?, last_seen_at = ?
            WHERE queue_id = ? AND state = 'queued'
            """,
            (worker_id, new_token, now, input_fingerprint, now, qid),
        )
        conn.execute(
            """
            INSERT INTO worker_heartbeats (
                worker_id, last_heartbeat_at, current_claim,
                heartbeat_interval_seconds, heartbeat_timeout_seconds,
                progress_marker, progress_marker_unchanged_since
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
            ON CONFLICT(worker_id) DO UPDATE SET
                last_heartbeat_at = excluded.last_heartbeat_at,
                current_claim = excluded.current_claim,
                heartbeat_interval_seconds = excluded.heartbeat_interval_seconds,
                heartbeat_timeout_seconds = excluded.heartbeat_timeout_seconds
            """,
            (worker_id, now, qid, heartbeat_interval_seconds, heartbeat_timeout_seconds),
        )
        return Claim(
            queue_id=qid, artefact_id=aid, fencing_token=new_token,
            severity=severity, reason=reason, attempt_count=attempts,
        )


def heartbeat(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    progress_marker: str | None = None,
) -> None:
    """Update last_heartbeat_at; optionally record progress_marker (P25 scaffold).

    If progress_marker equals the previous value, progress_marker_unchanged_since
    is left as-is. If it changes (or is set for the first time), the column
    updates to now(). Phase 1 ships this columnar bookkeeping; Phase 2 acts on
    the unchanged-marker signal for soft-stuck routing.
    """
    now = utc_now_iso()
    if progress_marker is None:
        conn.execute(
            "UPDATE worker_heartbeats SET last_heartbeat_at = ? WHERE worker_id = ?",
            (now, worker_id),
        )
        return
    row = conn.execute(
        "SELECT progress_marker FROM worker_heartbeats WHERE worker_id = ?",
        (worker_id,),
    ).fetchone()
    prior = row[0] if row else None
    if prior == progress_marker:
        conn.execute(
            "UPDATE worker_heartbeats SET last_heartbeat_at = ? WHERE worker_id = ?",
            (now, worker_id),
        )
    else:
        conn.execute(
            """
            UPDATE worker_heartbeats SET
                last_heartbeat_at = ?, progress_marker = ?,
                progress_marker_unchanged_since = ?
            WHERE worker_id = ?
            """,
            (now, progress_marker, now, worker_id),
        )


def complete(conn: sqlite3.Connection, claim: Claim, *, worker_id: str) -> None:
    """Mark the claim done and clear worker's current_claim."""
    with transaction(conn):
        conn.execute(
            "UPDATE rebuild_queue SET state = 'done', last_seen_at = ? WHERE queue_id = ?",
            (utc_now_iso(), claim.queue_id),
        )
        conn.execute(
            "UPDATE worker_heartbeats SET current_claim = NULL WHERE worker_id = ?",
            (worker_id,),
        )


def fail(
    conn: sqlite3.Connection,
    claim: Claim,
    *,
    worker_id: str,
    error: str,
    max_attempts: int = MAX_ATTEMPTS_BEFORE_QUARANTINE,
) -> str:
    """Mark the claim failed. Returns the new state ('queued' or 'quarantine')."""
    new_attempts = claim.attempt_count + 1
    new_state = "quarantine" if new_attempts >= max_attempts else "queued"
    with transaction(conn):
        conn.execute(
            """
            UPDATE rebuild_queue SET
                state = ?, attempt_count = ?, last_error = ?,
                lease_owner = NULL, claimed_at = NULL,
                input_fingerprint_at_claim = NULL, last_seen_at = ?
            WHERE queue_id = ?
            """,
            (new_state, new_attempts, error, utc_now_iso(), claim.queue_id),
        )
        conn.execute(
            "UPDATE worker_heartbeats SET current_claim = NULL WHERE worker_id = ?",
            (worker_id,),
        )
    return new_state


def queue_depth(conn: sqlite3.Connection) -> dict[str, int]:
    """Return queue depth by state."""
    rows = conn.execute(
        "SELECT state, COUNT(*) FROM rebuild_queue GROUP BY state"
    ).fetchall()
    return {state: n for state, n in rows}


def oldest_queued_age_seconds(conn: sqlite3.Connection) -> int | None:
    """Return the age (seconds) of the oldest queued item, or None if empty."""
    row = conn.execute(
        """
        SELECT (julianday('now') - julianday(first_seen_at)) * 86400.0
        FROM rebuild_queue
        WHERE state = 'queued'
        ORDER BY first_seen_at ASC
        LIMIT 1
        """,
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])
