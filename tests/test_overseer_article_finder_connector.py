"""Tests for overseer.article_finder_connector."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from overseer.article_finder_connector import (
    ArticleFinderNotFound,
    connect_readonly,
    iter_papers,
    paper_signature,
    resolve_af_db_path,
    schema_version,
)


@pytest.fixture
def fake_af_db(tmp_path) -> Path:
    """Create a small fake AF DB with the expected papers schema."""
    db = tmp_path / "article_finder.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY,
            doi TEXT,
            title TEXT,
            canonical_paper_id TEXT,
            status TEXT
        );
        CREATE TABLE schema_version (version TEXT);
        INSERT INTO schema_version (version) VALUES ('test_v1');
        INSERT INTO papers (doi, title, canonical_paper_id, status) VALUES
            ('10.1234/foo', 'Foo Paper', 'PDF-0001', 'accepted'),
            ('10.1234/bar', 'Bar Paper', NULL, 'candidate'),
            ('10.1234/baz', 'Baz Paper', 'PDF-0003', 'accepted');
    """)
    conn.commit()
    conn.close()
    return db


def test_paper_signature_is_deterministic():
    s1 = paper_signature(doi="10.1/x", canonical_paper_id="PDF-1", title="A")
    s2 = paper_signature(doi="10.1/x", canonical_paper_id="PDF-1", title="A")
    assert s1 == s2 and s1.startswith("sha256:")


def test_paper_signature_normalizes_case_and_whitespace():
    s1 = paper_signature(doi=" 10.1/X ", canonical_paper_id="PDF-1", title=" A ")
    s2 = paper_signature(doi="10.1/x", canonical_paper_id="pdf-1", title="a")
    assert s1 == s2


def test_paper_signature_is_sensitive_to_meaningful_changes():
    s1 = paper_signature(doi="10.1/x", canonical_paper_id="PDF-1", title="A")
    s2 = paper_signature(doi="10.1/y", canonical_paper_id="PDF-1", title="A")
    assert s1 != s2


def test_resolve_af_db_path_raises_when_explicit_missing():
    with pytest.raises(ArticleFinderNotFound):
        resolve_af_db_path("/nonexistent/path/to/article_finder.db")


def test_resolve_af_db_path_accepts_explicit_path(fake_af_db):
    assert resolve_af_db_path(fake_af_db) == fake_af_db


def test_connect_readonly_returns_ro_connection(fake_af_db):
    conn = connect_readonly(fake_af_db)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM papers").fetchone()
        assert rows[0] == 3
        # Read-only: writing should fail.
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO papers (doi) VALUES ('10.1/new')")
    finally:
        conn.close()


def test_iter_papers_filters_by_status(fake_af_db):
    conn = connect_readonly(fake_af_db)
    try:
        accepted = list(iter_papers(conn, af_status_filter="accepted"))
        assert len(accepted) == 2
        assert all(p.af_status == "accepted" for p in accepted)
        all_papers = list(iter_papers(conn, af_status_filter=None))
        assert len(all_papers) == 3
    finally:
        conn.close()


def test_iter_papers_includes_signature(fake_af_db):
    conn = connect_readonly(fake_af_db)
    try:
        papers = list(iter_papers(conn, af_status_filter=None))
        for p in papers:
            assert p.signature.startswith("sha256:")
            # Recompute and verify.
            expected = paper_signature(
                doi=p.doi, canonical_paper_id=p.canonical_paper_id, title=p.title,
            )
            assert p.signature == expected
    finally:
        conn.close()


def test_schema_version_returns_value_when_present(fake_af_db):
    conn = connect_readonly(fake_af_db)
    try:
        assert schema_version(conn) == "test_v1"
    finally:
        conn.close()


def test_iter_papers_handles_missing_columns_gracefully(tmp_path):
    # AF DB with only `id` column in `papers` (no doi/title/...).
    db = tmp_path / "tiny_af.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE papers (id INTEGER PRIMARY KEY);
        INSERT INTO papers DEFAULT VALUES;
    """)
    conn.commit()
    conn.close()
    rc = connect_readonly(db)
    try:
        papers = list(iter_papers(rc, af_status_filter=None))
        assert len(papers) == 1
        assert papers[0].doi is None
        assert papers[0].title is None
        assert papers[0].signature.startswith("sha256:")
    finally:
        rc.close()
