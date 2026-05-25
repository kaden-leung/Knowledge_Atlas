"""Tests for OVERSEER-AF-CRITERION-SWITCH (atlas_intake_decision criterion).

Source authority:
    docs/DEPENDENCY_OVERSEER_POST_PANEL_PAUSE_PLAN_2026-05-24.md §4.1
    docs/AF_PIPELINE_BOXOLOGY_AND_MONITORING_REQUIREMENTS_2026-05-24.md
"""

from __future__ import annotations

import sqlite3

import pytest

from overseer.article_finder_connector import (
    ArticleFinderPaper,
    iter_papers,
    paper_signature,
)
from overseer.article_finder_reconciler import tick as reconciler_tick


@pytest.fixture
def fake_af_with_intake(tmp_path) -> sqlite3.Connection:
    """Fake AF with both status and atlas_intake_decision columns."""
    db = tmp_path / "af_intake.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY,
            doi TEXT, title TEXT, canonical_paper_id TEXT,
            status TEXT, atlas_intake_decision TEXT,
            ae_corpus_match_status TEXT
        );
        INSERT INTO papers (doi, title, canonical_paper_id, status,
                            atlas_intake_decision, ae_corpus_match_status) VALUES
            ('10.1/a', 'A', 'PDF-A', 'candidate',         'accept_candidate', 'unmatched'),
            ('10.1/b', 'B', 'PDF-B', 'candidate',         'accept_candidate', 'matched'),
            ('10.1/c', 'C', 'PDF-C', 'candidate',         'edge_case',        'unmatched'),
            ('10.1/d', 'D', 'PDF-D', 'candidate',         'needs_pdf_text',   'unmatched'),
            ('10.1/e', 'E', 'PDF-E', 'processed_partial', 'accept_candidate', 'matched'),
            ('10.1/f', 'F', 'PDF-F', 'rejected',          'reject_clear_false_positive', NULL);
    """)
    conn.commit()
    conn.close()
    af = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    af.row_factory = sqlite3.Row
    yield af
    af.close()


# ----------------------------------------------------------------------------
# ArticleFinderPaper now carries intake / match
# ----------------------------------------------------------------------------

def test_article_finder_paper_exposes_intake_and_match_fields(fake_af_with_intake):
    papers = list(iter_papers(fake_af_with_intake, af_status_filter=None))
    by_canon = {p.canonical_paper_id: p for p in papers}
    assert by_canon["PDF-A"].atlas_intake_decision == "accept_candidate"
    assert by_canon["PDF-A"].ae_corpus_match_status == "unmatched"
    assert by_canon["PDF-B"].atlas_intake_decision == "accept_candidate"
    assert by_canon["PDF-B"].ae_corpus_match_status == "matched"
    assert by_canon["PDF-C"].atlas_intake_decision == "edge_case"
    assert by_canon["PDF-F"].ae_corpus_match_status is None


# ----------------------------------------------------------------------------
# iter_papers filters by atlas_intake_decision
# ----------------------------------------------------------------------------

def test_iter_papers_filters_by_intake_decision(fake_af_with_intake):
    papers = list(iter_papers(
        fake_af_with_intake,
        af_status_filter=None,
        atlas_intake_decision_filter="accept_candidate",
    ))
    # PDF-A, PDF-B, PDF-E all have accept_candidate
    assert {p.canonical_paper_id for p in papers} == {"PDF-A", "PDF-B", "PDF-E"}


def test_iter_papers_filters_combine_and(fake_af_with_intake):
    # status='processed_partial' AND atlas_intake_decision='accept_candidate'
    # → only PDF-E matches both
    papers = list(iter_papers(
        fake_af_with_intake,
        af_status_filter="processed_partial",
        atlas_intake_decision_filter="accept_candidate",
    ))
    assert {p.canonical_paper_id for p in papers} == {"PDF-E"}


def test_iter_papers_both_filters_none_returns_all(fake_af_with_intake):
    papers = list(iter_papers(
        fake_af_with_intake,
        af_status_filter=None,
        atlas_intake_decision_filter=None,
    ))
    assert len(papers) == 6


def test_iter_papers_with_filter_for_unused_column_safely_yields_none(tmp_path):
    """If AF.papers lacks atlas_intake_decision (older AF), filter is silently
    ignored and rows still yield with the column as None."""
    db = tmp_path / "old_af.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE papers (id INTEGER PRIMARY KEY, doi TEXT, title TEXT);
        INSERT INTO papers (doi, title) VALUES ('10.1/x', 'X');
    """)
    conn.commit()
    conn.close()
    af = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    af.row_factory = sqlite3.Row
    try:
        papers = list(iter_papers(
            af, af_status_filter=None,
            atlas_intake_decision_filter="accept_candidate",  # column doesn't exist
        ))
        # The filter clause is dropped because the column is absent.
        # All papers (just the one) are returned.
        assert len(papers) == 1
        assert papers[0].atlas_intake_decision is None
    finally:
        af.close()


# ----------------------------------------------------------------------------
# reconciler tick uses the new criterion
# ----------------------------------------------------------------------------

def test_tick_with_intake_filter_finds_accept_candidate_papers(overseer_db,
                                                                fake_af_with_intake):
    r = reconciler_tick(
        overseer_db,
        af_conn=fake_af_with_intake,
        accepted_filter=None,
        accepted_intake_decision="accept_candidate",
    )
    # 3 papers have accept_candidate; reconciler syncs all 3.
    assert r.af_papers_seen == 3
    assert r.inserted_pending == 3


def test_tick_both_criteria_combine(overseer_db, fake_af_with_intake):
    # Demand status='processed_partial' AND intake='accept_candidate' → 1 paper.
    r = reconciler_tick(
        overseer_db,
        af_conn=fake_af_with_intake,
        accepted_filter="processed_partial",
        accepted_intake_decision="accept_candidate",
    )
    assert r.af_papers_seen == 1
    assert r.inserted_pending == 1


def test_tick_event_log_records_status_for_intake_filtered_paper(overseer_db,
                                                                  fake_af_with_intake):
    reconciler_tick(
        overseer_db,
        af_conn=fake_af_with_intake,
        accepted_filter=None,
        accepted_intake_decision="accept_candidate",
    )
    # Each event_log row records the AF status (which may be 'candidate' even
    # if the intake_decision matched 'accept_candidate').
    statuses = [r[0] for r in overseer_db.execute(
        "SELECT DISTINCT af_status FROM reconciler_event_log"
    )]
    # Two distinct AF statuses among the 3 accepted: 'candidate', 'processed_partial'
    assert set(statuses) == {"candidate", "processed_partial"}
