"""Completion-queue tests: missing primary claim, count reconciliation,
queue dedupe across re-runs.

Authority: docs/ARTICLE_DETAIL_EPISTEMIC_LAYER_SPEC_2026-05-23.md §8, §11, §12.
"""

from __future__ import annotations

import sqlite3

from scripts import build_article_epistemic_layer as builder
from tests._article_epistemic_fixtures import (
    complete_record,
    partial_record_missing_primary_claim,
    record_with_attack_count_no_defeaters,
    record_with_stale_pnu,
)


def _build_and_persist(aepl_db_path, paper_id, rec):
    """Run the full builder persistence path against a fresh DB."""
    started_at = builder.utc_now()
    conn = sqlite3.connect(aepl_db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    build_run_id = builder.make_build_run_id(started_at, conn)
    try:
        with conn:
            builder.write_build_run_row(conn, build_run_id, started_at)
            paper_record = builder.build_record_for_paper(paper_id, rec, build_run_id)
            builder.persist_record(conn, paper_record, build_run_id)
            builder.finalize_build_run_row(
                conn, build_run_id,
                finished_at=builder.utc_now(),
                input_snapshot_hash="sha256:test",
                record_count=1, success_count=1, failure_count=0,
                repair_count=len(paper_record["repair_items"]),
                status="completed",
                report={},
            )
    finally:
        conn.close()
    return build_run_id, paper_record


def test_missing_primary_claim_writes_blocking_queue_entry(aepl_db_path):
    rec = partial_record_missing_primary_claim("TEST-NO-PRIMARY")
    _build_and_persist(aepl_db_path, "TEST-NO-PRIMARY", rec)
    conn = sqlite3.connect(aepl_db_path)
    try:
        rows = conn.execute(
            "SELECT component_type, reason, severity, status, attempt_count "
            "FROM article_epistemic_completion_queue WHERE paper_id = ?",
            ("TEST-NO-PRIMARY",),
        ).fetchall()
    finally:
        conn.close()
    assert any(
        r[0] == "primary_claim" and r[1] == "primary_claim_not_extracted"
        and r[2] == "blocking" and r[3] == "open"
        for r in rows
    ), f"Expected blocking primary_claim_not_extracted queue entry; got {rows}"


def test_attack_count_without_defeaters_emits_warning_queue_entry():
    rec = record_with_attack_count_no_defeaters("P1")
    out = builder.build_record_for_paper("P1", rec, "aepl-20260523-000001")
    reasons = {(r["component_type"], r["reason"], r["severity"])
               for r in out["repair_items"]}
    assert ("defeaters", "attack_count_without_mapped_rows", "warning") in reasons


def test_attack_count_without_defeaters_persists_to_queue(aepl_db_path):
    rec = record_with_attack_count_no_defeaters("TEST-ATTACK-NOFIX")
    _build_and_persist(aepl_db_path, "TEST-ATTACK-NOFIX", rec)
    conn = sqlite3.connect(aepl_db_path)
    try:
        rows = conn.execute(
            "SELECT component_type, reason, severity, status, attempt_count "
            "FROM article_epistemic_completion_queue WHERE paper_id = ?",
            ("TEST-ATTACK-NOFIX",),
        ).fetchall()
    finally:
        conn.close()
    assert any(
        r[0] == "defeaters" and r[1] == "attack_count_without_mapped_rows"
        and r[2] == "warning" and r[3] == "open"
        for r in rows
    ), f"Expected defeaters/attack_count queue entry; got {rows}"


def test_queue_dedupes_via_upsert_on_rebuild(aepl_db_path):
    """Re-running the builder must increment attempt_count, not insert a duplicate."""
    rec = partial_record_missing_primary_claim("TEST-DEDUPE")
    _build_and_persist(aepl_db_path, "TEST-DEDUPE", rec)
    _build_and_persist(aepl_db_path, "TEST-DEDUPE", rec)
    _build_and_persist(aepl_db_path, "TEST-DEDUPE", rec)
    conn = sqlite3.connect(aepl_db_path)
    try:
        rows = conn.execute(
            "SELECT component_type, reason, attempt_count FROM "
            "article_epistemic_completion_queue WHERE paper_id = ? "
            "AND status IN ('open','in_progress')",
            ("TEST-DEDUPE",),
        ).fetchall()
    finally:
        conn.close()
    # All three rebuilds collapse into a single open row whose attempt_count == 3.
    primary_rows = [r for r in rows if r[1] == "primary_claim_not_extracted"]
    assert len(primary_rows) == 1
    assert primary_rows[0][2] == 3


def test_queue_severity_updates_on_redetection(aepl_db_path):
    """Re-detection updates severity in BOTH directions (Mayo / panel finding).
    Seed a stale 'blocking' row, then a build that re-detects the same key as a
    'warning' (PNU is now enrichment) must de-escalate it, not leave it blocking."""
    conn = sqlite3.connect(aepl_db_path)
    conn.execute(
        "INSERT INTO article_epistemic_completion_queue("
        "  paper_id, component_type, reason, severity, next_action, status"
        ") VALUES ('TEST-SEV','belief_network_context','pnu_requires_repair',"
        "          'blocking','stale old action','open')")
    conn.commit()
    conn.close()
    _build_and_persist(aepl_db_path, "TEST-SEV", record_with_stale_pnu("TEST-SEV"))
    conn = sqlite3.connect(aepl_db_path)
    try:
        sev = conn.execute(
            "SELECT severity FROM article_epistemic_completion_queue "
            "WHERE paper_id='TEST-SEV' AND component_type='belief_network_context' "
            "AND reason='pnu_requires_repair' AND status='open'").fetchone()[0]
    finally:
        conn.close()
    assert sev == "warning"


def test_no_repair_items_for_clean_record():
    rec = complete_record("P1")
    out = builder.build_record_for_paper("P1", rec, "aepl-20260523-000001")
    # Complete record with fresh PNU and zero attack_count emits no repair items.
    assert out["repair_items"] == []


def test_blocking_failures_json_lists_blocking_repairs():
    rec = partial_record_missing_primary_claim("P1")
    out = builder.build_record_for_paper("P1", rec, "aepl-20260523-000001")
    import json as _json
    blocking = _json.loads(out["record"]["blocking_failures_json"])
    assert any(b.get("reason") == "primary_claim_not_extracted" for b in blocking)
