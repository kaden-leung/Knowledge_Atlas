"""Tests for overseer.article_finder_reconciler."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from overseer.article_finder_reconciler import (
    ReconcilerReport,
    _ka_paper_id_for,
    _lifecycle_payload_hash,
    tick,
)
from overseer.artefact_registry import register
from overseer.article_finder_connector import ArticleFinderPaper


@pytest.fixture
def fake_af(tmp_path) -> sqlite3.Connection:
    """Fake AF DB with a few papers in different statuses."""
    db = tmp_path / "af.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY,
            doi TEXT,
            title TEXT,
            canonical_paper_id TEXT,
            status TEXT
        );
        INSERT INTO papers (doi, title, canonical_paper_id, status) VALUES
            ('10.1/a', 'Paper A', 'PDF-A', 'processed_partial'),
            ('10.1/b', 'Paper B', 'PDF-B', 'processed_partial'),
            ('10.1/c', 'Paper C', NULL,    'processed_partial'),
            ('10.1/d', 'Paper D', 'PDF-D', 'candidate');
    """)
    conn.commit()
    conn.close()
    # Re-open with row factory + readonly URI (mirrors connect_readonly).
    uri_conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    uri_conn.row_factory = sqlite3.Row
    yield uri_conn
    uri_conn.close()


def test_tick_on_empty_af_returns_zero(overseer_db, tmp_path):
    db = tmp_path / "empty_af.db"
    sqlite3.connect(db).executescript(
        "CREATE TABLE papers (id INTEGER PRIMARY KEY, status TEXT);"
    )
    af = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    af.row_factory = sqlite3.Row
    try:
        r = tick(overseer_db, af_conn=af)
    finally:
        af.close()
    assert r.af_papers_seen == 0
    assert r.inserted_pending == 0


def test_tick_inserts_pending_for_each_accepted_af_paper(overseer_db, fake_af):
    r = tick(overseer_db, af_conn=fake_af)
    # 3 processed_partial papers, 1 candidate (filtered out).
    assert r.af_papers_seen == 3
    assert r.inserted_pending == 3
    assert r.flagged_unresolved == 0
    # cross_db_sync_events has 3 rows.
    n = overseer_db.execute(
        "SELECT COUNT(*) FROM cross_db_sync_events WHERE status = 'pending'"
    ).fetchone()[0]
    assert n == 3
    # artefact_registry has 3 article_finder_candidate rows.
    n2 = overseer_db.execute(
        "SELECT COUNT(*) FROM artefact_registry "
        "WHERE kind = 'article_finder_candidate' AND active = 1"
    ).fetchone()[0]
    assert n2 == 3


def test_tick_is_idempotent_under_unchanged_af(overseer_db, fake_af):
    r1 = tick(overseer_db, af_conn=fake_af)
    assert r1.inserted_pending == 3
    # Re-open the connection (we already consumed iter once via a generator).
    # The connection itself can be reused for a fresh query.
    r2 = tick(overseer_db, af_conn=fake_af)
    assert r2.inserted_pending == 0
    # AF papers seen again, but no new pending rows.
    assert r2.af_papers_seen == 3


def test_tick_upgrades_pending_to_matched_when_ka_record_exists(overseer_db, fake_af):
    tick(overseer_db, af_conn=fake_af)
    # Register a matching KA article_epistemic_record for one AF paper.
    register(
        overseer_db, kind="article_epistemic_record", entity_type="paper",
        entity_id="PDF-A", field_path=None,
        schema_version="article_epistemic_layer.v1",
    )
    r = tick(overseer_db, af_conn=fake_af)
    assert r.upgraded_to_matched == 1
    status = overseer_db.execute(
        "SELECT status FROM cross_db_sync_events WHERE lifecycle_payload_hash = ?",
        ("paper:PDF-A",),
    ).fetchone()[0]
    assert status == "matched"


def test_tick_flags_unresolved_on_signature_drift(overseer_db, fake_af, tmp_path):
    """If AF's signature for the same paper_id changes (e.g., title was edited),
    the event flips to 'unresolved' and a blocking completion_queue row is raised.
    """
    tick(overseer_db, af_conn=fake_af)
    fake_af.close()
    # Drift the title in a NEW fake AF DB simulating an AF rewrite.
    db2 = tmp_path / "af2.db"
    sqlite3.connect(db2).executescript("""
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY,
            doi TEXT, title TEXT, canonical_paper_id TEXT, status TEXT
        );
        INSERT INTO papers (doi, title, canonical_paper_id, status) VALUES
            ('10.1/a', 'Paper A REVISED TITLE', 'PDF-A', 'processed_partial');
    """)
    af2 = sqlite3.connect(f"file:{db2}?mode=ro", uri=True)
    af2.row_factory = sqlite3.Row
    try:
        r = tick(overseer_db, af_conn=af2)
    finally:
        af2.close()
    assert r.flagged_unresolved == 1
    status = overseer_db.execute(
        "SELECT status FROM cross_db_sync_events WHERE lifecycle_payload_hash = ?",
        ("paper:PDF-A",),
    ).fetchone()[0]
    assert status == "unresolved"
    # Blocking completion_queue row exists.
    cq = overseer_db.execute(
        "SELECT severity, reason FROM completion_queue "
        "WHERE paper_id = 'PDF-A' AND status IN ('open','in_review')"
    ).fetchone()
    assert cq is not None
    assert cq["severity"] == "blocking"
    assert "af_signature_drift" in cq["reason"]


def test_tick_uses_canonical_paper_id_when_present(overseer_db, fake_af):
    tick(overseer_db, af_conn=fake_af)
    payload_hashes = {
        r[0] for r in overseer_db.execute(
            "SELECT lifecycle_payload_hash FROM cross_db_sync_events"
        )
    }
    # PDF-A, PDF-B for the two with canonical_paper_id; AF:<rowid> for Paper C.
    assert "paper:PDF-A" in payload_hashes
    assert "paper:PDF-B" in payload_hashes
    # Paper C had no canonical_paper_id → falls back to AF:<paper_id>.
    af_fallbacks = [p for p in payload_hashes if p.startswith("paper:AF:")]
    assert len(af_fallbacks) == 1


def test_tick_respects_limit(overseer_db, fake_af):
    r = tick(overseer_db, af_conn=fake_af, limit=2)
    assert r.af_papers_seen == 2
    assert r.inserted_pending == 2


def test_tick_treats_none_filter_as_all(overseer_db, fake_af):
    r = tick(overseer_db, af_conn=fake_af, accepted_filter=None)
    # 3 processed_partial + 1 candidate = 4 total
    assert r.af_papers_seen == 4


def test_ka_paper_id_for_helper():
    p_with = ArticleFinderPaper(
        af_paper_id="42", doi="d", title="t",
        canonical_paper_id="PDF-X", af_status="s", signature="sha256:..",
    )
    assert _ka_paper_id_for(p_with) == "PDF-X"
    p_without = ArticleFinderPaper(
        af_paper_id="42", doi="d", title="t",
        canonical_paper_id=None, af_status="s", signature="sha256:..",
    )
    assert _ka_paper_id_for(p_without) == "AF:42"


def test_lifecycle_payload_hash_format():
    assert _lifecycle_payload_hash("PDF-9") == "paper:PDF-9"
