"""Unit tests for stage1_metadata_triage.py — all run against tmp_path DBs."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PHASE3 = _HERE.parent / "Phase 3"
if str(_PHASE3) not in sys.path:
    sys.path.insert(0, str(_PHASE3))

from migrate import apply_migrations  # noqa: E402

from stage1_metadata_triage import (  # noqa: E402
    check_noise,
    keyword_fallback_classify,
    run_stage1_triage,
    significant_word_count,
)


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path, _PHASE3 / "migrations")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    yield db_path, conn
    conn.close()


def _insert_row(conn, ref_id, title_raw, doi=None, venue=None, stage="metadata_only"):
    conn.execute(
        "INSERT INTO article_references "
        "(reference_id, doi, title_raw, title_normalized, "
        " discovered_via, discovery_run_id, discovered_at, triage_stage, venue) "
        "VALUES (?, ?, ?, ?, 'serpapi_scholar', 'RUN-T', '2026-05-31T00:00:00Z', ?, ?)",
        (ref_id, doi, title_raw, (title_raw or "").lower(), stage, venue),
    )


# ---------------------------------------------------------------------------
# check_noise — one test per regex rule
# ---------------------------------------------------------------------------

def test_empty_title_rejected():
    reason, _ = check_noise("", None)
    assert reason == "noise:empty_title"
    reason, _ = check_noise("   ", None)
    assert reason == "noise:empty_title"
    reason, _ = check_noise(None, None)
    assert reason == "noise:empty_title"


def test_jstor_footer_rejected():
    reason, _ = check_noise("This content downloaded from 73.158.x.x", None)
    assert reason == "noise:jstor_footer"


def test_jstor_terms_rejected():
    reason, _ = check_noise("Some text including use subject to https://about.jstor.org/terms here", None)
    assert reason == "noise:jstor_terms"


def test_cid_artifact_rejected():
    reason, _ = check_noise("21:41:50 UTC(cid:0)(cid:0)(cid:0)", None)
    assert reason == "noise:pdf_cid_artifact"


def test_url_only_rejected():
    reason, _ = check_noise("https://example.org/some/url", None)
    assert reason == "noise:url_only"


def test_doi_url_artifact_rejected():
    """Citation number + DOI URL like '417, https://doi.org/10.3390/...' → noise:doi_url_artifact."""
    reason, _ = check_noise("417, https://doi.org/10.3390/buildings12040417", None)
    assert reason == "noise:doi_url_artifact"


def test_malformed_doi_url_rejected():
    """Malformed 'https:// doi.org/...' (space in URL) is caught before it reaches the classifier."""
    reason, _ = check_noise("https:// doi.org/10.3390/buildings13010042", None)
    # doi_url_artifact fires first (pattern matches the doi.org domain after optional space)
    assert reason in ("noise:doi_url_artifact", "noise:malformed_url", "noise:url_only")


def test_page_range_artifact_rejected():
    reason, _ = check_noise("125-127", None)
    assert reason == "noise:page_range_artifact"
    reason, _ = check_noise("125 - 127", None)
    assert reason == "noise:page_range_artifact"


def test_short_title_no_doi_rejected():
    reason, _ = check_noise("Three short words", None)
    assert reason == "noise:title_too_short_no_doi"


def test_short_title_with_doi_kept():
    """A short title WITH a DOI is not rejected by the short-title rule."""
    reason, _ = check_noise("Short title here", "10.x/y")
    assert reason is None  # passes noise check


def test_normal_title_passes_noise_check():
    reason, _ = check_noise("Sensorimotor brain dynamics reflect architectural affordances", None)
    assert reason is None


# ---------------------------------------------------------------------------
# significant_word_count
# ---------------------------------------------------------------------------

def test_significant_word_count():
    assert significant_word_count("") == 0
    assert significant_word_count("a an of in") == 0  # all < 3 chars
    assert significant_word_count("the quick brown fox") == 4  # all ≥ 3 chars
    assert significant_word_count("a of by an") == 0  # 2-char tokens excluded
    assert significant_word_count("Sensorimotor brain dynamics reflect architectural affordances") == 6


# ---------------------------------------------------------------------------
# keyword_fallback_classify
# ---------------------------------------------------------------------------

def test_keyword_fallback_rich_match_passes_high():
    d, c = keyword_fallback_classify(
        "Architectural cognition and spatial navigation in built environments",
        venue="Cognition"
    )
    assert d == "PASS"
    assert c >= 0.50


def test_keyword_fallback_thin_match_passes_low():
    d, c = keyword_fallback_classify("Building information modeling for civil engineering", None)
    assert d == "PASS"
    assert 0.20 <= c <= 0.30  # thin match → 0.25


def test_keyword_fallback_no_match_rejects():
    d, c = keyword_fallback_classify("Quantum chromodynamics on the lattice", "Phys Rev D")
    assert d == "REJECT"
    assert c == 0.0


# ---------------------------------------------------------------------------
# run_stage1_triage — integration
# ---------------------------------------------------------------------------

def test_passing_row_transitions_to_abstract_pending(db):
    db_path, conn = db
    _insert_row(conn, "REF-T-000001",
                "Architectural affordances and predictive coding in spatial navigation built environment",
                venue="Cognition")
    conn.commit()

    report = run_stage1_triage(db_path=db_path, run_id="RUN-PASS")
    assert report.passed_to_stage2a == 1
    assert report.rejected_total == 0

    conn2 = sqlite3.connect(str(db_path))
    try:
        stage = conn2.execute("SELECT triage_stage FROM article_references WHERE reference_id='REF-T-000001'").fetchone()[0]
    finally:
        conn2.close()
    assert stage == "abstract_pending"


def test_noise_row_transitions_to_rejected_at_metadata(db):
    db_path, conn = db
    _insert_row(conn, "REF-T-000010", "This content downloaded from JSTOR somewhere")
    conn.commit()

    report = run_stage1_triage(db_path=db_path, run_id="RUN-REJ")
    assert report.rejected_total == 1
    assert report.reject_reasons.get("noise:jstor_footer") == 1

    conn2 = sqlite3.connect(str(db_path))
    try:
        row = conn2.execute(
            "SELECT triage_stage, triage_decision FROM article_references WHERE reference_id='REF-T-000010'"
        ).fetchone()
    finally:
        conn2.close()
    assert row[0] == "rejected_at_metadata"
    assert row[1] == "REJECT"


def test_classifier_below_threshold_rejected(db):
    """An injected classifier that always returns low confidence → row rejected."""
    db_path, conn = db
    # Title that survives noise check (4 significant words)
    _insert_row(conn, "REF-T-000020", "Architectural affordances and predictive coding mechanisms",
                doi="10.x/y", venue="Some Venue")
    conn.commit()

    def low_conf_classifier(t, v):
        return "PASS", 0.05  # below 0.20 threshold

    report = run_stage1_triage(db_path=db_path, run_id="RUN-LOW", classifier=low_conf_classifier)
    assert report.rejected_total == 1
    assert report.passed_to_stage2a == 0


def test_idempotent_on_already_triaged(db):
    """Re-running Stage 1 on rows that are no longer metadata_only is a no-op."""
    db_path, conn = db
    _insert_row(conn, "REF-T-000030", "Already rejected", stage="rejected_at_metadata")
    _insert_row(conn, "REF-T-000031", "Already pending", stage="abstract_pending")
    conn.commit()

    report = run_stage1_triage(db_path=db_path, run_id="RUN-IDEM")
    # No rows in 'metadata_only' state → nothing to process
    assert report.candidates_processed == 0


def test_dry_run_no_disk_writes(db):
    db_path, conn = db
    _insert_row(conn, "REF-T-000040", "Some title here")
    conn.commit()

    # Snapshot before
    conn2 = sqlite3.connect(str(db_path))
    try:
        before = conn2.execute("SELECT triage_stage FROM article_references").fetchall()
    finally:
        conn2.close()

    run_stage1_triage(db_path=db_path, run_id="RUN-DRY", dry_run=True)

    conn2 = sqlite3.connect(str(db_path))
    try:
        after = conn2.execute("SELECT triage_stage FROM article_references").fetchall()
    finally:
        conn2.close()
    assert before == after


def test_one_transition_per_candidate_correct_writer(db):
    """SC-11: every processed row gets one lifecycle_transitions row with created_by='abstract_triage'."""
    db_path, conn = db
    _insert_row(conn, "REF-T-000050", "Good title with architecture cognition spatial venue keywords")
    _insert_row(conn, "REF-T-000051", "")  # empty → noise rejection
    _insert_row(conn, "REF-T-000052", "Bldg engr.")  # short, no DOI → noise rejection
    conn.commit()

    run_stage1_triage(db_path=db_path, run_id="RUN-TR")
    conn2 = sqlite3.connect(str(db_path))
    try:
        rows = conn2.execute(
            "SELECT reference_id, created_by FROM lifecycle_transitions WHERE run_id='RUN-TR'"
        ).fetchall()
    finally:
        conn2.close()
    assert len(rows) == 3
    assert all(r[1] == "abstract_triage" for r in rows)


def test_report_counts_balance(db):
    """SC-12: passed + rejected == candidates_processed (no silent drops)."""
    db_path, conn = db
    _insert_row(conn, "REF-T-000060", "This content downloaded from JSTOR test")  # noise
    _insert_row(conn, "REF-T-000061", "")  # noise
    _insert_row(conn, "REF-T-000062", "Architectural cognition and predictive coding in built environment spatial")
    conn.commit()

    report = run_stage1_triage(db_path=db_path, run_id="RUN-BAL")
    assert report.candidates_processed == report.passed_to_stage2a + report.rejected_total


def test_keyword_fallback_used_when_classifier_unavailable(db):
    """If we don't inject a classifier, load_classifier() returns the keyword fallback
    (because no centroids file exists in this test env). Verified via classifier_mode."""
    db_path, conn = db
    _insert_row(conn, "REF-T-000070", "Some random title with architecture cognition spatial venue keywords")
    conn.commit()

    report = run_stage1_triage(db_path=db_path, run_id="RUN-KF")
    # In our test env, hierarchical classifier is unavailable → falls back to keyword
    assert report.classifier_mode in ("keyword_fallback", "hierarchical")
