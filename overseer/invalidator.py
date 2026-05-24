"""Invalidation propagation: when a source artefact's semantic_hash changes,
mark dependents stale and enqueue rebuilds.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §13 #8 #9
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (P27)

Key rule: only semantic_hash changes propagate. A raw-only change (same
semantic_hash, new raw_hash) records cosmetic change in content_hashes
history but does NOT enqueue rebuilds.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from overseer.artefact_registry import mark_stale
from overseer.completion_queue import enqueue as cq_enqueue
from overseer.dependency_edges import children_of
from overseer.rebuild_queue import enqueue as rq_enqueue

CASCADE_BOUND = 100  # Per impl spec §14 OIQ #3 recommendation.


@dataclass(frozen=True)
class InvalidationReport:
    source_artefact_id: str
    semantic_changed: bool
    dependents_invalidated: list[str]
    queue_ids: list[str]
    cascade_alert_raised: bool


def invalidate_on_source_change(
    conn: sqlite3.Connection,
    *,
    source_artefact_id: str,
    semantic_changed: bool,
    reason: str = "upstream_source_changed",
    severity: str = "medium",
    cascade_bound: int = CASCADE_BOUND,
) -> InvalidationReport:
    """Propagate invalidation from a source artefact to its dependents.

    If semantic_changed is False (raw-only change): no-op.
    If True: mark every dependent artefact stale and enqueue rebuilds.

    If the dependent count exceeds cascade_bound, batches enqueue but raises a
    'cascade_alert' completion_queue item per synthesis P8.
    """
    if not semantic_changed:
        return InvalidationReport(
            source_artefact_id=source_artefact_id,
            semantic_changed=False,
            dependents_invalidated=[],
            queue_ids=[],
            cascade_alert_raised=False,
        )

    dependents = children_of(conn, source_artefact_id)
    cascade_alert_raised = False
    if len(dependents) > cascade_bound:
        cq_enqueue(
            conn,
            reason=f"cascade_threshold_exceeded:source={source_artefact_id}:count={len(dependents)}",
            severity="high",
            artefact_id=source_artefact_id,
            next_action="batch_rebuild_review",
        )
        cascade_alert_raised = True

    queue_ids: list[str] = []
    for dep_id in dependents:
        mark_stale(conn, dep_id)
        qid = rq_enqueue(conn, artefact_id=dep_id, reason=reason, severity=severity)
        queue_ids.append(qid)

    return InvalidationReport(
        source_artefact_id=source_artefact_id,
        semantic_changed=True,
        dependents_invalidated=dependents,
        queue_ids=queue_ids,
        cascade_alert_raised=cascade_alert_raised,
    )
