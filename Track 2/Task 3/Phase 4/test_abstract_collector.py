"""Unit tests for abstract_collector.py — all mocked, no live HTTP."""
from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_HERE = Path(__file__).resolve().parent           # Phase 4/
_PHASE3 = _HERE.parent / "Phase 3"                 # Task 3/Phase 3/

# Wire up Phase 3 so we can apply migrations
if str(_PHASE3) not in sys.path:
    sys.path.insert(0, str(_PHASE3))

from migrate import apply_migrations  # noqa: E402

from abstract_collector import (  # noqa: E402
    AbstractResult,
    collect_abstract,
    run_collection,
    VALID_SOURCES,
)


# ---------------------------------------------------------------------------
# Mock client helpers
# ---------------------------------------------------------------------------

@dataclass
class _Meta:
    abstract: str | None = None


@dataclass
class _Hit:
    abstract: str | None = None


@dataclass
class _FetchResult:
    status: object
    metadata: object | None = None


def _ok_meta(abstract: str | None = None) -> _FetchResult:
    from paper_fetcher import FetchStatus
    return _FetchResult(FetchStatus.SUCCESS, _Meta(abstract))


def _none_meta() -> _FetchResult:
    from paper_fetcher import FetchStatus
    return _FetchResult(FetchStatus.SUCCESS, _Meta(None))


def _make_clients(**overrides):
    """Build a 4-client tuple with sensible defaults; pass overrides per source."""
    s2 = MagicMock()
    s2.fetch_by_doi = MagicMock(return_value=_none_meta())
    s2.search = MagicMock(return_value=[])

    crossref = MagicMock()
    crossref.fetch = MagicMock(return_value=_none_meta())

    pubmed = MagicMock()
    pubmed.fetch = MagicMock(return_value=_none_meta())
    pubmed.search = MagicMock(return_value=[])

    openalex = MagicMock()
    openalex.fetch_abstract_by_doi = MagicMock(return_value=None)
    openalex.fetch_abstract_by_title_year = MagicMock(return_value=None)

    for src_name, mock in {"s2": s2, "crossref": crossref, "pubmed": pubmed, "openalex": openalex}.items():
        if src_name in overrides:
            overrides[src_name](mock)
    return {"s2": s2, "crossref": crossref, "pubmed": pubmed, "openalex": openalex}


# ---------------------------------------------------------------------------
# Fallback chain — one test per rung
# ---------------------------------------------------------------------------

def test_short_circuit_on_first_hit_s2():
    """SC-SC: when S2 returns an abstract, no other source is called."""
    c = _make_clients(s2=lambda m: m.fetch_by_doi.__setattr__("return_value", _ok_meta("found it")))
    res = collect_abstract(doi="10.x/y", title="t", year=2020, **{k+"_client": v for k, v in c.items()})
    assert res.source == "semantic_scholar"
    assert res.abstract == "found it"
    c["crossref"].fetch.assert_not_called()
    c["pubmed"].fetch.assert_not_called()
    c["openalex"].fetch_abstract_by_doi.assert_not_called()


def test_fallback_chain_uses_crossref_when_s2_empty():
    """SC-FB: S2 empty → CrossRef tried and used."""
    c = _make_clients(crossref=lambda m: m.fetch.__setattr__("return_value", _ok_meta("crossref abs")))
    res = collect_abstract(doi="10.x/y", title="t", year=2020, **{k+"_client": v for k, v in c.items()})
    assert res.source == "crossref"
    assert res.abstract == "crossref abs"
    c["s2"].fetch_by_doi.assert_called_once()
    c["crossref"].fetch.assert_called_once()


def test_fallback_chain_uses_pubmed_when_crossref_empty():
    """SC-FB: S2 + CrossRef empty → PubMed tried."""
    c = _make_clients(pubmed=lambda m: m.fetch.__setattr__("return_value", _ok_meta("pubmed abs")))
    res = collect_abstract(doi="10.x/y", title="t", year=2020, **{k+"_client": v for k, v in c.items()})
    assert res.source == "pubmed"
    assert res.abstract == "pubmed abs"


def test_fallback_chain_uses_openalex_last():
    """SC-FB: All previous empty → OpenAlex tried and used."""
    c = _make_clients(openalex=lambda m: m.fetch_abstract_by_doi.__setattr__("return_value", "openalex abs"))
    res = collect_abstract(doi="10.x/y", title="t", year=2020, **{k+"_client": v for k, v in c.items()})
    assert res.source == "openalex"
    assert res.abstract == "openalex abs"


def test_all_sources_empty_returns_missing_abstract():
    """When every fallback rung is empty → MISSING_ABSTRACT."""
    c = _make_clients()
    res = collect_abstract(doi="10.x/y", title="t", year=2020, **{k+"_client": v for k, v in c.items()})
    assert res.source == "MISSING_ABSTRACT"
    assert res.abstract is None


def test_no_doi_falls_back_to_title_search():
    """No DOI → S2.search(title) by title; if hit, use it."""
    c = _make_clients(s2=lambda m: m.search.__setattr__("return_value", [_Hit("title-hit abs")]))
    res = collect_abstract(doi=None, title="some title", year=2024, **{k+"_client": v for k, v in c.items()})
    assert res.abstract == "title-hit abs"
    assert res.source == "semantic_scholar"
    assert res.title_used == "some title"
    c["s2"].fetch_by_doi.assert_not_called()  # No DOI → no DOI call
    c["s2"].search.assert_called_once()


def test_doi_normalized_before_lookup():
    """SC-NR: URL-prefixed DOI is stripped to bare form before passing to clients."""
    captured = {}

    def s2_setup(m):
        def _fetch(doi):
            captured["doi"] = doi
            return _ok_meta("a")
        m.fetch_by_doi.side_effect = _fetch

    c = _make_clients(s2=s2_setup)
    collect_abstract(doi="https://doi.org/10.1234/abc", title=None, year=None,
                     **{k+"_client": v for k, v in c.items()})
    assert captured["doi"] == "10.1234/abc"


# ---------------------------------------------------------------------------
# study_type + ambiguous title + mock-mode
# ---------------------------------------------------------------------------

def test_study_type_in_output():
    """SC-ST: study_type filled by estimate_study_type() when abstract contains markers."""
    c = _make_clients(s2=lambda m: m.fetch_by_doi.__setattr__(
        "return_value", _ok_meta("This is a randomized controlled trial of architecture.")))
    res = collect_abstract(doi="10.x/y", title="t", year=2020, **{k+"_client": v for k, v in c.items()})
    assert res.study_type == "rct"


def test_ambiguous_title_takes_first_hit():
    """SC-AT: title-search returns multiple → take first."""
    c = _make_clients(s2=lambda m: m.search.__setattr__(
        "return_value", [_Hit("first abs"), _Hit("second abs")]))
    res = collect_abstract(doi=None, title="ambig title", year=None, **{k+"_client": v for k, v in c.items()})
    assert res.abstract == "first abs"
    assert res.title_used == "ambig title"


def test_mock_mode_no_real_clients_instantiated():
    """SC-MK: mock=True bypasses all client instantiation; reads fixture file."""
    res = collect_abstract(
        doi="10.1073/pnas.1912264116",
        title="Sensorimotor brain dynamics reflect architectural affordances",
        year=2019,
        mock=True,
        mock_fixtures_dir=_HERE / "fixtures",
    )
    assert res.source == "semantic_scholar"
    assert "Predictive mechanisms" in res.abstract


def test_mock_mode_unknown_returns_missing_abstract():
    """Mock-mode with unmatched DOI → MISSING_ABSTRACT (safe fallback)."""
    res = collect_abstract(
        doi="10.0000/unmatched", title="unknown", year=2024,
        mock=True, mock_fixtures_dir=_HERE / "fixtures",
    )
    assert res.source == "MISSING_ABSTRACT"
    assert res.abstract is None


# ---------------------------------------------------------------------------
# DB-level integration: run_collection
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test.db"
    apply_migrations(db_path, _PHASE3 / "migrations")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    # Seed a few abstract_pending rows
    rows = [
        ("REF-2026-05-31-000001", "10.1073/pnas.1912264116",
         "Sensorimotor brain dynamics reflect architectural affordances",
         "sensorimotor brain dynamics reflect architectural affordances",
         "abstract_pending", 2019),
        ("REF-2026-05-31-000002", None,
         "Unknown paper title four words long",
         "unknown paper title four words long",
         "abstract_pending", 2024),
        ("REF-2026-05-31-000003", "10.0000/notfound",
         "Title that won't match any fixture",
         "title that wont match any fixture",
         "abstract_pending", 2024),
    ]
    for r in rows:
        conn.execute(
            "INSERT INTO article_references "
            "(reference_id, doi, title_raw, title_normalized, "
            " discovered_via, discovery_run_id, discovered_at, "
            " triage_stage, publication_year) "
            "VALUES (?, ?, ?, ?, 'serpapi_scholar', 'RUN-T', '2026-05-31T00:00:00Z', ?, ?)",
            r,
        )
    conn.commit()
    yield db_path, conn
    conn.close()


def test_one_transition_per_candidate_correct_writer(db):
    """SC-IT: every processed row gets one lifecycle_transitions row with created_by='abstract_collector'."""
    db_path, conn = db
    report = run_collection(
        db_path=db_path, run_id="RUN-AC", mock=True,
        mock_fixtures_dir=_HERE / "fixtures",
    )
    # 3 candidates seeded
    assert report.candidates_processed == 3

    c2 = sqlite3.connect(str(db_path))
    try:
        n_trans = c2.execute(
            "SELECT COUNT(*) FROM lifecycle_transitions WHERE run_id = 'RUN-AC'"
        ).fetchone()[0]
        n_correct_writer = c2.execute(
            "SELECT COUNT(*) FROM lifecycle_transitions "
            "WHERE run_id = 'RUN-AC' AND created_by = 'abstract_collector'"
        ).fetchone()[0]
    finally:
        c2.close()
    assert n_trans == 3
    assert n_correct_writer == 3


def test_abstract_source_field_set_on_every_row(db):
    """SC-AS: after processing, every row has a non-null abstract_source in VALID_SOURCES."""
    db_path, _ = db
    run_collection(db_path=db_path, run_id="RUN-AS", mock=True, mock_fixtures_dir=_HERE / "fixtures")
    c2 = sqlite3.connect(str(db_path))
    try:
        rows = c2.execute(
            "SELECT abstract_source FROM article_references "
            "WHERE triage_stage IN ('abstract_collected', 'abstract_missing')"
        ).fetchall()
    finally:
        c2.close()
    assert rows  # at least one
    for r in rows:
        assert r[0] in VALID_SOURCES, f"Bad abstract_source: {r[0]!r}"


def test_missing_abstract_count_tracked_and_reported(db):
    """SC-MA: report.missing_abstracts matches the DB row count after run."""
    db_path, _ = db
    report = run_collection(db_path=db_path, run_id="RUN-MA", mock=True,
                            mock_fixtures_dir=_HERE / "fixtures")
    c2 = sqlite3.connect(str(db_path))
    try:
        n_missing = c2.execute(
            "SELECT COUNT(*) FROM article_references WHERE abstract_source = 'MISSING_ABSTRACT'"
        ).fetchone()[0]
    finally:
        c2.close()
    assert report.missing_abstracts == n_missing


def test_dry_run_no_disk_writes(db):
    """SC-DR: dry_run=True doesn't mutate the on-disk DB."""
    db_path, _ = db
    # Snapshot DB content before
    c2 = sqlite3.connect(str(db_path))
    try:
        before = c2.execute(
            "SELECT reference_id, triage_stage, abstract_text FROM article_references ORDER BY reference_id"
        ).fetchall()
    finally:
        c2.close()

    run_collection(db_path=db_path, run_id="RUN-DRY", mock=True,
                   mock_fixtures_dir=_HERE / "fixtures", dry_run=True)

    c2 = sqlite3.connect(str(db_path))
    try:
        after = c2.execute(
            "SELECT reference_id, triage_stage, abstract_text FROM article_references ORDER BY reference_id"
        ).fetchall()
    finally:
        c2.close()
    assert before == after  # no rows changed
