"""Completion queue: human-review and repair items.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §3.6 §11
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (B6, §5 repair loop)

Lifecycle: open -> in_review -> resolved | waived.
Severity: low, medium, high, blocking. Blocking items prevent promotion.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from overseer.ids import completion_queue_id, utc_now_iso

ALLOWED_SEVERITIES = ("low", "medium", "high", "blocking")
ALLOWED_STATUSES = ("open", "in_review", "resolved", "waived")


@dataclass(frozen=True)
class CompletionItem:
    queue_id: str
    artefact_id: str | None
    paper_id: str | None
    component_type: str | None
    reason: str
    severity: str
    first_seen_at: str
    last_seen_at: str
    attempt_count: int
    next_action: str | None
    status: str
    assigned_to: str | None
    resolved_at: str | None


def _row(r: sqlite3.Row | tuple) -> CompletionItem:
    if isinstance(r, sqlite3.Row):
        return CompletionItem(
            queue_id=r["queue_id"], artefact_id=r["artefact_id"],
            paper_id=r["paper_id"], component_type=r["component_type"],
            reason=r["reason"], severity=r["severity"],
            first_seen_at=r["first_seen_at"], last_seen_at=r["last_seen_at"],
            attempt_count=r["attempt_count"], next_action=r["next_action"],
            status=r["status"], assigned_to=r["assigned_to"],
            resolved_at=r["resolved_at"],
        )
    return CompletionItem(*r)


def enqueue(
    conn: sqlite3.Connection,
    *,
    reason: str,
    severity: str = "medium",
    artefact_id: str | None = None,
    paper_id: str | None = None,
    component_type: str | None = None,
    next_action: str | None = None,
) -> str:
    """Insert a completion-queue item. Returns the queue_id.

    If an open item with the same (artefact_id, reason) already exists, the
    existing item is refreshed (last_seen_at, attempt_count++) and its
    queue_id returned. This makes enqueue safe to call from repair loops
    without proliferating duplicate rows.
    """
    if severity not in ALLOWED_SEVERITIES:
        raise ValueError(f"severity '{severity}' not in {ALLOWED_SEVERITIES}")
    existing = None
    if artefact_id is not None:
        existing = conn.execute(
            """
            SELECT queue_id, attempt_count FROM completion_queue
            WHERE artefact_id = ? AND reason = ? AND status IN ('open','in_review')
            LIMIT 1
            """,
            (artefact_id, reason),
        ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE completion_queue SET
                last_seen_at = ?, attempt_count = attempt_count + 1
            WHERE queue_id = ?
            """,
            (utc_now_iso(), existing[0]),
        )
        return existing[0]
    qid = completion_queue_id()
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO completion_queue (
            queue_id, artefact_id, paper_id, component_type, reason, severity,
            first_seen_at, last_seen_at, attempt_count, next_action, status,
            assigned_to, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 'open', NULL, NULL)
        """,
        (qid, artefact_id, paper_id, component_type, reason, severity, now, now,
         next_action),
    )
    return qid


def mark_in_review(
    conn: sqlite3.Connection, *, queue_id: str, assigned_to: str
) -> None:
    conn.execute(
        """
        UPDATE completion_queue SET status = 'in_review', assigned_to = ?,
            last_seen_at = ?
        WHERE queue_id = ? AND status = 'open'
        """,
        (assigned_to, utc_now_iso(), queue_id),
    )


def resolve(conn: sqlite3.Connection, *, queue_id: str) -> None:
    conn.execute(
        """
        UPDATE completion_queue SET status = 'resolved', resolved_at = ?,
            last_seen_at = ?
        WHERE queue_id = ? AND status IN ('open','in_review')
        """,
        (utc_now_iso(), utc_now_iso(), queue_id),
    )


def waive(
    conn: sqlite3.Connection,
    *,
    queue_id: str,
    assigned_to: str,
) -> None:
    conn.execute(
        """
        UPDATE completion_queue SET status = 'waived', assigned_to = ?,
            resolved_at = ?, last_seen_at = ?
        WHERE queue_id = ?
        """,
        (assigned_to, utc_now_iso(), utc_now_iso(), queue_id),
    )


def list_open(
    conn: sqlite3.Connection,
    *,
    min_severity: str = "low",
) -> list[CompletionItem]:
    """Return open and in-review items with severity >= min_severity."""
    rank = {"low": 0, "medium": 1, "high": 2, "blocking": 3}
    if min_severity not in rank:
        raise ValueError(f"min_severity '{min_severity}' not in {list(rank)}")
    min_rank = rank[min_severity]
    rows = conn.execute(
        """
        SELECT * FROM completion_queue
        WHERE status IN ('open','in_review')
        ORDER BY first_seen_at
        """,
    ).fetchall()
    return [_row(r) for r in rows if rank[r["severity"]] >= min_rank]


def has_blocking_open(conn: sqlite3.Connection) -> bool:
    n = conn.execute(
        """
        SELECT COUNT(*) FROM completion_queue
        WHERE status IN ('open','in_review') AND severity = 'blocking'
        """,
    ).fetchone()[0]
    return n > 0
