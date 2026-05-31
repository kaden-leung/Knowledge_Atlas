"""Dedupe-layer tests for Phase 3 (SCHEMA_CONTRACT.md §8 decision tree)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from migrate import apply_migrations
from dedupe import (
    Candidate,
    CorpusEntry,
    CorpusSnapshot,
    insert_or_dedupe_reference,
    merge_discovered_via,
    title_jaccard,
)

_HERE = Path(__file__).resolve().parent
MIGRATIONS_DIR = _HERE / "migrations"

_FIXED_NOW = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path, MIGRATIONS_DIR)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()


def _insert(db, cand: Candidate, *, run_id="RUN-T", created_by="db_loader", corpus=None):
    """Helper that wraps insert_or_dedupe_reference in a commit boundary."""
    with db:
        outcome = insert_or_dedupe_reference(
            cand, db, run_id=run_id, created_by=created_by,
            corpus_snapshot=corpus, now=_FIXED_NOW,
        )
    return outcome


# ---------------------------------------------------------------------------
# BRANCH A — DOI exact match
# ---------------------------------------------------------------------------

def test_doi_exact_match_merges_via(db):
    """Same DOI inserted twice → 1 row; discovered_via has both source tokens."""
    c1 = Candidate(title_raw="Sensorimotor brain dynamics", doi="10.1073/pnas.1912264116",
                   discovered_via="serpapi_scholar")
    c2 = Candidate(title_raw="Sensorimotor brain dynamics", doi="10.1073/pnas.1912264116",
                   discovered_via="scholarly_search")
    o1 = _insert(db, c1)
    o2 = _insert(db, c2)

    assert o1.reference_id == o2.reference_id
    assert o2.action == "merged_doi"

    n = db.execute("SELECT COUNT(*) FROM article_references").fetchone()[0]
    assert n == 1

    via = db.execute("SELECT discovered_via FROM article_references").fetchone()[0]
    assert via == "scholarly_search, serpapi_scholar"


def test_doi_match_preserves_first_inserted_id(db):
    """Branch A returns the existing reference_id, not a new one."""
    c1 = Candidate(title_raw="Foo", doi="10.1000/x", discovered_via="serpapi_scholar")
    c2 = Candidate(title_raw="Foo (alt cap)", doi="10.1000/x", discovered_via="paperscraper_search")
    o1 = _insert(db, c1)
    o2 = _insert(db, c2)
    assert o2.reference_id == o1.reference_id


def test_doi_match_with_url_prefix_normalises(db):
    """`https://doi.org/10.x` and `10.x` collapse via normalize_doi."""
    c1 = Candidate(title_raw="Paper A", doi="10.1000/abc", discovered_via="serpapi_scholar")
    c2 = Candidate(title_raw="Paper A", doi="https://doi.org/10.1000/abc", discovered_via="scholarly_search")
    o1 = _insert(db, c1)
    o2 = _insert(db, c2)
    assert o1.reference_id == o2.reference_id
    assert db.execute("SELECT COUNT(*) FROM article_references").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# BRANCH D — Title fuzzy match within article_references
# ---------------------------------------------------------------------------

def test_title_jaccard_above_threshold_merges(db):
    """Two no-DOI candidates with high token overlap merge to one row."""
    # >= 4 significant words so the §7.6.1 safety check passes
    title_a = "Architectural affordances and predictive coding mechanisms in spatial cognition"
    title_b = "Architectural affordances and predictive coding mechanisms in spatial cognition"
    c1 = Candidate(title_raw=title_a, doi=None, discovered_via="serpapi_scholar")
    c2 = Candidate(title_raw=title_b, doi=None, discovered_via="paperscraper_search")
    o1 = _insert(db, c1)
    o2 = _insert(db, c2)
    assert o2.action == "merged_title"
    assert o1.reference_id == o2.reference_id
    assert db.execute("SELECT COUNT(*) FROM article_references").fetchone()[0] == 1


def test_title_jaccard_below_threshold_inserts(db):
    """Two candidates with low token overlap stay distinct."""
    c1 = Candidate(title_raw="Predictive coding in visual cortex experiments mechanisms",
                   doi=None, discovered_via="serpapi_scholar")
    c2 = Candidate(title_raw="Architectural emotion responses corridors threshold",
                   doi=None, discovered_via="serpapi_scholar")
    _insert(db, c1)
    _insert(db, c2)
    assert db.execute("SELECT COUNT(*) FROM article_references").fetchone()[0] == 2


# ---------------------------------------------------------------------------
# BRANCH B — Corpus snapshot match
# ---------------------------------------------------------------------------

def test_corpus_snapshot_match_inserts_as_duplicate(db):
    """Title hit in corpus → row inserted with triage_stage='duplicate'."""
    snap = CorpusSnapshot()
    title_norm = "sensorimotor brain dynamics reflect architectural affordances corridors"
    snap.by_title[title_norm] = CorpusEntry(
        paper_id="PDF-EXISTING-001", doi="", title_normalized=title_norm,
    )

    cand = Candidate(
        title_raw="Sensorimotor Brain Dynamics Reflect Architectural Affordances Corridors",
        doi=None,
        discovered_via="serpapi_scholar",
    )
    outcome = _insert(db, cand, corpus=snap)

    assert outcome.action == "corpus_duplicate"
    row = db.execute(
        "SELECT triage_stage, triage_decision, triage_reason FROM article_references WHERE reference_id = ?",
        (outcome.reference_id,),
    ).fetchone()
    assert row[0] == "duplicate"
    assert row[1] == "DUPLICATE"
    assert row[2] == "matches_existing_corpus:PDF-EXISTING-001"


# ---------------------------------------------------------------------------
# BRANCH E — Fresh insert
# ---------------------------------------------------------------------------

def test_no_doi_no_title_match_fresh_insert(db):
    """First-seen candidate with no DOI / no corpus match → new row, action='inserted'."""
    cand = Candidate(title_raw="Brand new paper title not seen before anywhere",
                     doi=None, discovered_via="serpapi_scholar")
    outcome = _insert(db, cand)
    assert outcome.action == "inserted"
    assert outcome.reference_id.startswith("REF-2026-05-28-")
    assert db.execute("SELECT COUNT(*) FROM article_references").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# BRANCH C — Late DOI arrival
# ---------------------------------------------------------------------------

def test_doi_enrichment_on_late_arrival(db):
    """DOI-null row + matching-title candidate with DOI → existing row's DOI populated."""
    title = "Late-arrival DOI enrichment test paper title here"
    c1 = Candidate(title_raw=title, doi=None, discovered_via="review_pdf_extract")
    c2 = Candidate(title_raw=title, doi="10.1234/late.arrival",
                   discovered_via="serpapi_scholar")
    o1 = _insert(db, c1, created_by="reference_harvester")
    o2 = _insert(db, c2)

    assert o2.action == "enriched_doi"
    assert o1.reference_id == o2.reference_id
    row = db.execute(
        "SELECT doi, discovered_via FROM article_references WHERE reference_id = ?",
        (o1.reference_id,),
    ).fetchone()
    assert row[0] == "10.1234/late.arrival"
    # Both sources retained
    assert "review_pdf_extract" in row[1]
    assert "serpapi_scholar" in row[1]


# ---------------------------------------------------------------------------
# Transition logging + idempotent merge helper
# ---------------------------------------------------------------------------

def test_provenance_merge_logs_transition(db):
    """A DOI-merge writes a lifecycle_transitions row with reason='provenance_merge:*'."""
    c1 = Candidate(title_raw="Foo bar baz qux", doi="10.1000/log", discovered_via="serpapi_scholar")
    c2 = Candidate(title_raw="Foo bar baz qux", doi="10.1000/log", discovered_via="scholarly_search")
    _insert(db, c1)
    _insert(db, c2)

    reasons = [
        row[0] for row in db.execute(
            "SELECT reason FROM lifecycle_transitions ORDER BY transition_id"
        ).fetchall()
    ]
    assert reasons[0] == "initial_insert:serpapi_scholar"
    assert reasons[1] == "provenance_merge:scholarly_search"


def test_provenance_merge_dedupes_same_via_twice():
    """merge_discovered_via with the same token twice → no duplication."""
    assert merge_discovered_via("serpapi_scholar", "serpapi_scholar") == "serpapi_scholar"
    assert merge_discovered_via("serpapi_scholar, scholarly_search", "serpapi_scholar") == "scholarly_search, serpapi_scholar"
    assert merge_discovered_via("", "serpapi_scholar") == "serpapi_scholar"


# ---------------------------------------------------------------------------
# Sanity check on the Jaccard helper used by branches B/C/D
# ---------------------------------------------------------------------------

def test_title_jaccard_arithmetic():
    """Sanity: identical → 1.0; disjoint → 0.0; empty → 0.0."""
    assert title_jaccard("foo bar baz", "foo bar baz") == 1.0
    assert title_jaccard("a b c", "x y z") == 0.0
    assert title_jaccard("", "anything") == 0.0
    # 3 shared of 4 union → 0.75
    assert title_jaccard("a b c", "a b c d") == pytest.approx(0.75)
