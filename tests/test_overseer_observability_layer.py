"""Tests for the observability layer (verifier_run_history + reconciler_event_log).

Source authority:
    docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md §5
    docs/DEPENDENCY_OVERSEER_POST_PANEL_PAUSE_PLAN_2026-05-24.md §3
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from overseer.artefact_registry import register
from overseer.article_finder_reconciler import tick as reconciler_tick
from overseer.verifier_data import verify_strict


# ----------------------------------------------------------------------------
# verifier_run_history
# ----------------------------------------------------------------------------

def test_verify_strict_writes_a_row_to_verifier_run_history(overseer_db):
    verify_strict(overseer_db, db_path="/tmp/test.db", triggered_by="test")
    rows = overseer_db.execute(
        "SELECT run_id, overall_passed, db_path, triggered_by, checks_json "
        "FROM verifier_run_history"
    ).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r["run_id"].startswith("vrh:")
    assert r["overall_passed"] == 1
    assert r["db_path"] == "/tmp/test.db"
    assert r["triggered_by"] == "test"
    # checks_json is a non-empty serialized list of checks.
    checks = json.loads(r["checks_json"])
    assert isinstance(checks, list) and len(checks) > 0


def test_verify_strict_does_not_record_when_record_to_history_false(overseer_db):
    verify_strict(overseer_db, record_to_history=False)
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM verifier_run_history"
    ).fetchone()[0]
    assert n == 0


def test_repeated_verify_strict_accumulates_rows(overseer_db):
    verify_strict(overseer_db, triggered_by="test")
    verify_strict(overseer_db, triggered_by="test")
    verify_strict(overseer_db, triggered_by="test")
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM verifier_run_history"
    ).fetchone()[0]
    assert n == 3


def test_failed_run_records_overall_passed_zero(overseer_db):
    # Register an artefact with an unregistered kind — fails kind_registration.
    register(overseer_db, kind="rogue_kind", entity_type="p", entity_id="P",
             field_path=None, schema_version="v1")
    verify_strict(overseer_db, triggered_by="test")
    r = overseer_db.execute(
        "SELECT overall_passed FROM verifier_run_history"
    ).fetchone()
    assert r["overall_passed"] == 0


def test_failed_check_failures_serialized_in_checks_json(overseer_db):
    register(overseer_db, kind="rogue_kind_x", entity_type="p", entity_id="PX",
             field_path=None, schema_version="v1")
    verify_strict(overseer_db)
    r = overseer_db.execute(
        "SELECT checks_json FROM verifier_run_history"
    ).fetchone()
    checks = json.loads(r["checks_json"])
    kind_check = next(c for c in checks if c["name"] == "kind_registration")
    assert kind_check["passed"] is False
    assert any(f.get("kind") == "rogue_kind_x" for f in kind_check["failures"])


def test_failed_index_finds_failing_run(overseer_db):
    register(overseer_db, kind="bad", entity_type="p", entity_id="P1",
             field_path=None, schema_version="v1")
    verify_strict(overseer_db)  # fail
    register(overseer_db, kind="article_finder_candidate", entity_type="p",
             entity_id="P2", field_path=None, schema_version="v1")
    verify_strict(overseer_db)  # still fails (the rogue kind is still there)
    failed_rows = overseer_db.execute(
        "SELECT COUNT(*) FROM verifier_run_history WHERE overall_passed = 0"
    ).fetchone()[0]
    assert failed_rows == 2


# ----------------------------------------------------------------------------
# reconciler_event_log
# ----------------------------------------------------------------------------

_fake_af_counter = [0]


def _make_fake_af(tmp_path, papers):
    """Build a fake AF DB with the given papers (list of dicts).

    Filenames use a monotonic counter so successive calls within the same
    test get distinct files even if Python recycles the list's id.
    """
    _fake_af_counter[0] += 1
    db = tmp_path / f"af_{_fake_af_counter[0]}.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY,
            doi TEXT, title TEXT, canonical_paper_id TEXT, status TEXT
        );
    """)
    for i, p in enumerate(papers, start=1):
        conn.execute(
            "INSERT OR IGNORE INTO papers (id, doi, title, canonical_paper_id, status) "
            "VALUES (?, ?, ?, ?, ?)",
            (i, p.get("doi"), p.get("title"), p.get("canonical_paper_id"),
             p.get("status", "processed_partial")),
        )
    conn.commit()
    conn.close()
    af = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    af.row_factory = sqlite3.Row
    return af


def test_reconciler_tick_logs_inserted_pending_events(overseer_db, tmp_path):
    af = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
        {"doi": "10.1/b", "title": "B", "canonical_paper_id": "PDF-B"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af)
    finally:
        af.close()
    rows = overseer_db.execute(
        "SELECT action, ka_paper_id, sync_event_id FROM reconciler_event_log "
        "ORDER BY ka_paper_id"
    ).fetchall()
    assert len(rows) == 2
    assert all(r["action"] == "inserted_pending" for r in rows)
    assert {r["ka_paper_id"] for r in rows} == {"PDF-A", "PDF-B"}
    # sync_event_id is populated
    assert all(r["sync_event_id"] is not None for r in rows)


def test_reconciler_tick_events_share_tick_run_id(overseer_db, tmp_path):
    af = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
        {"doi": "10.1/b", "title": "B", "canonical_paper_id": "PDF-B"},
        {"doi": "10.1/c", "title": "C", "canonical_paper_id": "PDF-C"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af)
    finally:
        af.close()
    tick_ids = {r[0] for r in overseer_db.execute(
        "SELECT DISTINCT tick_run_id FROM reconciler_event_log"
    )}
    assert len(tick_ids) == 1


def test_two_ticks_get_two_tick_run_ids(overseer_db, tmp_path):
    af1 = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af1)
    finally:
        af1.close()
    af2 = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},  # same paper
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af2)
    finally:
        af2.close()
    tick_ids = {r[0] for r in overseer_db.execute(
        "SELECT DISTINCT tick_run_id FROM reconciler_event_log"
    )}
    assert len(tick_ids) == 2


def test_reconciler_logs_upgraded_to_matched(overseer_db, tmp_path):
    af = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af)
    finally:
        af.close()
    register(
        overseer_db, kind="article_epistemic_record", entity_type="paper",
        entity_id="PDF-A", field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    af2 = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af2)
    finally:
        af2.close()
    actions = [r[0] for r in overseer_db.execute(
        "SELECT action FROM reconciler_event_log ORDER BY occurred_at"
    )]
    assert actions == ["inserted_pending", "upgraded_to_matched"]


def test_reconciler_logs_flagged_unresolved_on_drift(overseer_db, tmp_path):
    af1 = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af1)
    finally:
        af1.close()
    # Same paper_id, different title → drift
    af2 = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A REVISED", "canonical_paper_id": "PDF-A"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af2)
    finally:
        af2.close()
    actions = [r[0] for r in overseer_db.execute(
        "SELECT action FROM reconciler_event_log ORDER BY occurred_at"
    )]
    assert actions == ["inserted_pending", "flagged_unresolved"]
    reason = overseer_db.execute(
        "SELECT reason FROM reconciler_event_log WHERE action = 'flagged_unresolved'"
    ).fetchone()[0]
    assert reason == "af_signature_drift"


def test_reconciler_logs_skipped_already_matched(overseer_db, tmp_path):
    # First tick: insert_pending
    af1 = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af1)
    finally:
        af1.close()
    # Register KA record so the second tick upgrades to matched.
    register(
        overseer_db, kind="article_epistemic_record", entity_type="paper",
        entity_id="PDF-A", field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    af2 = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af2)
    finally:
        af2.close()
    # Third tick: skipped_already_matched
    af3 = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af3)
    finally:
        af3.close()
    actions = [r[0] for r in overseer_db.execute(
        "SELECT action FROM reconciler_event_log ORDER BY occurred_at"
    )]
    assert actions == [
        "inserted_pending", "upgraded_to_matched", "skipped_already_matched"
    ]


def test_event_log_records_af_status_and_signature(overseer_db, tmp_path):
    af = _make_fake_af(tmp_path, [
        {"doi": "10.1/a", "title": "A", "canonical_paper_id": "PDF-A",
         "status": "processed_partial"},
    ])
    try:
        reconciler_tick(overseer_db, af_conn=af)
    finally:
        af.close()
    r = overseer_db.execute(
        "SELECT af_status, af_signature, af_paper_id FROM reconciler_event_log"
    ).fetchone()
    assert r["af_status"] == "processed_partial"
    assert r["af_signature"].startswith("sha256:")
    assert r["af_paper_id"]  # non-empty
