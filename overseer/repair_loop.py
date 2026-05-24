"""Repair loop: route verification failures to rebuilds, completion items,
or quarantine; release-gate function.

Source authority:
    docs/DEPENDENCY_OVERSEER_IMPLEMENTATION_SPEC_2026-05-23.md §11
    docs/DEPENDENCY_OVERSEER_PANEL_SYNTHESIS_2026-05-23.md (§5 repair loop, B6)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from overseer.completion_queue import enqueue as cq_enqueue, has_blocking_open
from overseer.rebuild_queue import enqueue as rq_enqueue
from overseer.verifier_data import CheckResult, VerificationReport


@dataclass(frozen=True)
class RepairAction:
    kind: str  # 'enqueue_rebuild', 'enqueue_completion', 'noop'
    artefact_id: str | None
    reason: str
    severity: str


def route(check: CheckResult) -> list[RepairAction]:
    """Map verifier failure to repair action(s).

    No DB writes happen here. The caller (execute) applies the action.
    """
    actions: list[RepairAction] = []
    if check.passed:
        return actions

    for f in check.failures:
        if check.name == "semantic_hash_propagation":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=f.get("artefact_id"),
                reason="rebuild_queued_without_semantic_change",
                severity="medium",
            ))
        elif check.name in ("referential_integrity",):
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="orphan_dependency_edge",
                severity="high",
            ))
        elif check.name == "active_record_uniqueness":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="duplicate_active_records",
                severity="high",
            ))
        elif check.name == "hash_presence_on_fresh_artefacts":
            actions.append(RepairAction(
                kind="enqueue_rebuild",
                artefact_id=f.get("artefact_id"),
                reason="missing_hashes_on_fresh_artefact",
                severity="high",
            ))
        elif check.name == "kind_registration":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=f.get("artefact_id"),
                reason="unregistered_artefact_kind",
                severity="blocking",
            ))
        elif check.name == "queue_invariants_heartbeat_based":
            # The watchdog should handle this asynchronously. If the verifier
            # still sees the stale claim, raise a completion item.
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="watchdog_pending_reclaim",
                severity="medium",
            ))
        elif check.name == "fencing_token_monotonicity":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=f.get("artefact_id"),
                reason="fencing_token_monotonicity_violation",
                severity="blocking",
            ))
        elif check.name == "defeater_target_typing":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="defeater_missing_target_kind",
                severity="high",
            ))
        elif check.name == "claim_canonicalization":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="claim_id_ambiguous_canonical_text",
                severity="high",
            ))
        elif check.name == "vocabulary_canonicalization_integrity":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="vocabulary_synonym_chain_or_orphan",
                severity="medium",
            ))
        elif check.name == "belief_network_freshness":
            actions.append(RepairAction(
                kind="enqueue_rebuild",
                artefact_id=None,
                reason="belief_network_link_to_tombstoned_pnu",
                severity="medium",
            ))
        elif check.name == "answer_shape_rule_trace":
            actions.append(RepairAction(
                kind="enqueue_rebuild",
                artefact_id=None,
                reason="answer_shape_unknown_without_rule_trace",
                severity="medium",
            ))
        elif check.name == "normalization_rule_pinning":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="content_hashes_missing_normalization_rule",
                severity="high",
            ))
        elif check.name == "closed_enum_membership":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="closed_enum_drift",
                severity="blocking",
            ))
        elif check.name == "scaffold_tables_empty":
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=None,
                reason="phase_1_scaffold_table_populated_prematurely",
                severity="high",
            ))
        else:
            actions.append(RepairAction(
                kind="enqueue_completion",
                artefact_id=f.get("artefact_id"),
                reason=f"verifier_failure_{check.name}",
                severity="medium",
            ))
    return actions


def execute(conn: sqlite3.Connection, action: RepairAction) -> str | None:
    """Apply a repair action. Returns the created queue_id, or None for noop."""
    if action.kind == "enqueue_rebuild":
        if action.artefact_id is None:
            return None
        return rq_enqueue(
            conn, artefact_id=action.artefact_id,
            reason=action.reason, severity=action.severity,
        )
    if action.kind == "enqueue_completion":
        return cq_enqueue(
            conn, reason=action.reason, severity=action.severity,
            artefact_id=action.artefact_id,
        )
    return None


def route_and_execute(conn: sqlite3.Connection, report: VerificationReport) -> list[str]:
    """Route every failed check from the report; execute every action.

    Returns the list of created queue_ids (rebuild and completion combined).
    """
    queue_ids: list[str] = []
    for check in report.checks:
        for action in route(check):
            qid = execute(conn, action)
            if qid:
                queue_ids.append(qid)
    return queue_ids


def can_promote(
    conn: sqlite3.Connection,
    report: VerificationReport,
) -> tuple[bool, list[str]]:
    """Return (allowed, blocking_reasons).

    Blocks promotion if:
      * verifier report's overall_passed is False
      * any active artefact has freshness_status='stale'
      * any open/in-review completion_queue row with severity='blocking'
    """
    reasons: list[str] = []
    if not report.overall_passed:
        for c in report.checks:
            if not c.passed:
                reasons.append(f"verifier:{c.name}")
    stale_n = conn.execute(
        """
        SELECT COUNT(*) FROM artefact_registry
        WHERE active = 1 AND freshness_status = 'stale'
        """,
    ).fetchone()[0]
    if stale_n > 0:
        reasons.append(f"stale_required_artefacts:{stale_n}")
    if has_blocking_open(conn):
        reasons.append("completion_queue:blocking_open")
    return (not reasons, reasons)
