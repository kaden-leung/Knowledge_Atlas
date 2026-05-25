"""Article Finder ↔ Knowledge Atlas reconciler (async tick).

Source authority:
    docs/DEPENDENCY_OVERSEER_PHASE_2_SPEC_2026-05-23.md §3 §10
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (B11, P14, OR3)

The reconciler pairs AF-side state with KA-side state via cross_db_sync_events.
It is asynchronous: AF writes its half (no overseer involvement), and a
periodic tick() reads AF and ensures matching overseer state exists.

For each AF paper matching `accepted_filter`:
  1. Compute a KA paper_id (AF.canonical_paper_id if present, else AF:<af_paper_id>).
  2. Look up the most recent cross_db_sync_events row for that KA paper.
  3. If none: register an article_finder_candidate artefact in KA and insert
     a 'pending' event with the AF signature.
  4. If present and signature matches: try to upgrade 'pending' → 'matched'
     when a paired KA article_epistemic_record exists.
  5. If present and signature differs: flip to 'unresolved' and raise a
     blocking completion_queue item ('af_signature_drift_unresolved').
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import uuid

from overseer.article_finder_connector import (
    ArticleFinderPaper,
    connect_readonly,
    iter_papers,
)
from overseer.artefact_registry import get_by_entity, register
from overseer.completion_queue import enqueue as cq_enqueue
from overseer.db import transaction
from overseer.ids import event_id, utc_now_iso


@dataclass(frozen=True)
class ReconcilerReport:
    af_papers_seen: int
    inserted_pending: int
    upgraded_to_matched: int
    flagged_unresolved: int
    skipped_already_matched: int


def _ka_paper_id_for(af_paper: ArticleFinderPaper) -> str:
    """Resolve the KA-side paper_id for an AF paper."""
    if af_paper.canonical_paper_id:
        return af_paper.canonical_paper_id
    return f"AF:{af_paper.af_paper_id}"


def _lifecycle_payload_hash(ka_paper_id: str) -> str:
    """Stable identifier for the KA-side identity in cross_db_sync_events."""
    return f"paper:{ka_paper_id}"


def tick(
    conn: sqlite3.Connection,
    *,
    af_conn: sqlite3.Connection | None = None,
    accepted_filter: str | None = "processed_partial",
    limit: int | None = None,
) -> ReconcilerReport:
    """Run one reconciler tick.

    accepted_filter: AF.papers.status value that identifies the "accepted by
    Atlas" subset. Live AF DB inspection 2026-05-23 shows status distribution:
    'candidate' (16196), 'pending_scorer' (40), 'rejected' (18),
    'processed_partial' (3). The 'processed_partial' status is the closest
    proxy for accepted; callers may pass None to scan everything.

    limit: cap on AF rows processed per tick (None = no cap).
    """
    close_af = False
    if af_conn is None:
        af_conn = connect_readonly()
        close_af = True

    inserted_pending = 0
    upgraded_to_matched = 0
    flagged_unresolved = 0
    skipped_already_matched = 0
    af_papers_seen = 0
    tick_run_id = f"tick:{uuid.uuid4().hex}"

    def _log_event(action: str, af_paper: ArticleFinderPaper,
                   ka_paper_id: str, sync_event_id: str | None = None,
                   reason: str | None = None) -> None:
        try:
            conn.execute(
                """
                INSERT INTO reconciler_event_log (
                    event_id, tick_run_id, occurred_at, af_paper_id,
                    af_signature, af_status, ka_paper_id, action,
                    sync_event_id, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"rev:{uuid.uuid4().hex}", tick_run_id, utc_now_iso(),
                    af_paper.af_paper_id, af_paper.signature, af_paper.af_status,
                    ka_paper_id, action, sync_event_id, reason,
                ),
            )
        except sqlite3.OperationalError:
            # observability table missing on older DBs; skip silently.
            pass

    try:
        for af_paper in iter_papers(
            af_conn, af_status_filter=accepted_filter, limit=limit,
        ):
            af_papers_seen += 1
            ka_paper_id = _ka_paper_id_for(af_paper)
            payload_hash = _lifecycle_payload_hash(ka_paper_id)

            existing = conn.execute(
                """
                SELECT event_id, status, article_finder_payload_hash
                FROM cross_db_sync_events
                WHERE event_kind = 'accept_candidate'
                  AND lifecycle_payload_hash = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (payload_hash,),
            ).fetchone()

            if existing is None:
                new_sync_event_id = event_id()
                with transaction(conn):
                    register(
                        conn, kind="article_finder_candidate",
                        entity_type="paper", entity_id=ka_paper_id,
                        field_path=None,
                        schema_version="article_finder_candidate.v1",
                    )
                    conn.execute(
                        """
                        INSERT INTO cross_db_sync_events (
                            event_id, event_kind, lifecycle_payload_hash,
                            article_finder_payload_hash, status, created_at,
                            resolved_at
                        ) VALUES (?, 'accept_candidate', ?, ?, 'pending', ?, NULL)
                        """,
                        (new_sync_event_id, payload_hash, af_paper.signature,
                         utc_now_iso()),
                    )
                _log_event("inserted_pending", af_paper, ka_paper_id,
                           sync_event_id=new_sync_event_id)
                inserted_pending += 1
                continue

            prior_sig = existing["article_finder_payload_hash"]
            if prior_sig != af_paper.signature:
                with transaction(conn):
                    conn.execute(
                        """
                        UPDATE cross_db_sync_events SET
                            status = 'unresolved',
                            article_finder_payload_hash = ?,
                            resolved_at = NULL
                        WHERE event_id = ?
                        """,
                        (af_paper.signature, existing["event_id"]),
                    )
                    cq_enqueue(
                        conn,
                        reason="af_signature_drift_unresolved",
                        severity="blocking",
                        artefact_id=None,
                        paper_id=ka_paper_id,
                        next_action="manual_reconcile_af_vs_ka_signature",
                    )
                _log_event("flagged_unresolved", af_paper, ka_paper_id,
                           sync_event_id=existing["event_id"],
                           reason="af_signature_drift")
                flagged_unresolved += 1
                continue

            if existing["status"] == "matched":
                _log_event("skipped_already_matched", af_paper, ka_paper_id,
                           sync_event_id=existing["event_id"])
                skipped_already_matched += 1
                continue

            if existing["status"] == "pending":
                ka_record = get_by_entity(
                    conn, entity_type="paper", entity_id=ka_paper_id,
                    field_path=None,
                    schema_version="article_epistemic_layer.v1",
                )
                if ka_record is not None:
                    conn.execute(
                        """
                        UPDATE cross_db_sync_events SET
                            status = 'matched', resolved_at = ?
                        WHERE event_id = ?
                        """,
                        (utc_now_iso(), existing["event_id"]),
                    )
                    _log_event("upgraded_to_matched", af_paper, ka_paper_id,
                               sync_event_id=existing["event_id"])
                    upgraded_to_matched += 1
                else:
                    _log_event("noop", af_paper, ka_paper_id,
                               sync_event_id=existing["event_id"],
                               reason="pending_no_ka_record_yet")
                continue
    finally:
        if close_af:
            af_conn.close()

    return ReconcilerReport(
        af_papers_seen=af_papers_seen,
        inserted_pending=inserted_pending,
        upgraded_to_matched=upgraded_to_matched,
        flagged_unresolved=flagged_unresolved,
        skipped_already_matched=skipped_already_matched,
    )
